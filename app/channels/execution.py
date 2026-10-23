"""Bounded processes and HTTPS reads. External content is data, not executable policy."""
from __future__ import annotations

import http.client
import ipaddress
import json
import os
import queue
import shutil
import socket
import ssl
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from app.channels.models import ChannelError


def public_url(url: str, *, resolve: bool = False) -> tuple[str, list[str]]:
    try:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443):
            raise ValueError("invalid URL")
        host = parsed.hostname.lower()
        if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
            raise ValueError("private URL")
        try:
            literal = ipaddress.ip_address(host)
        except ValueError:
            literal = None
        if literal and not literal.is_global:
            raise ValueError("private address")
        addresses = [a[4][0] for a in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)] if resolve else []
        if resolve and (not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses)):
            raise ValueError("private DNS target")
        return host, addresses
    except (ValueError, OSError):
        raise ChannelError("domain_blocked") from None


class _PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, address, timeout):
        super().__init__(host, timeout=timeout, context=ssl.create_default_context())
        self.address = address
    def connect(self):
        sock = socket.create_connection((self.address, 443), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


@dataclass(frozen=True)
class PublicResponse:
    url: str
    status: int
    headers: dict[str, str]
    body: bytes


class HttpReader:
    def __init__(self, *, url_validator=None):
        self.url_validator = url_validator

    def get(self, url: str, *, timeout: float = 20, max_bytes: int = 1024 * 1024,on_request=None) -> str:
        response = self.read(url, timeout=timeout, max_bytes=max_bytes,on_request=on_request)
        if response.status >= 400:
            raise ChannelError({401: "auth_required", 403: "access_denied", 404: "not_found", 412: "account_risk", 429: "rate_limited"}.get(response.status, "upstream_error"))
        return response.body.decode("utf-8", errors="replace")

    def read(self, url: str, *, method: str = "GET", timeout: float = 20, max_bytes: int = 1024 * 1024,on_request=None) -> PublicResponse:
        if method not in {"GET", "HEAD"}:
            raise ChannelError("read_only")
        deadline = time.monotonic() + timeout
        for _ in range(4):
            if self.url_validator is not None:
                self.url_validator(url)
            host, addresses = public_url(url, resolve=True)
            remaining = deadline - time.monotonic()
            if on_request is not None:remaining=min(remaining,on_request())
            if remaining <= 0:
                raise ChannelError("timeout")
            parsed = urlsplit(url)
            connection = _PinnedHTTPS(host, addresses[0], remaining)
            try:
                connection.request(method, (parsed.path or "/") + ("?" + parsed.query if parsed.query else ""),
                                   headers={"User-Agent": "DeepIntel/1.0", "Accept": "application/json,text/plain,text/html,*/*", "Accept-Encoding": "identity"})
                response = connection.getresponse()
                if response.status in (301, 302, 303, 307, 308):
                    url = urljoin(url, response.getheader("Location", ""))
                    continue
                data = bytearray()
                while True:
                    if time.monotonic() >= deadline:
                        raise ChannelError("timeout")
                    if connection.sock:
                        connection.sock.settimeout(max(0.001, deadline - time.monotonic()))
                    chunk = response.read(min(8192, max_bytes - len(data) + 1))
                    if not chunk:
                        break
                    data.extend(chunk)
                    if len(data) > max_bytes:
                        raise ChannelError("output_limit")
                # Do not relay credentials, cookies, connection framing or a
                # redirect already followed by this pinned transport.
                allowed_headers = {"content-type", "content-language", "cache-control", "etag", "last-modified", "date", "expires", "content-security-policy", "x-frame-options", "access-control-allow-origin", "access-control-allow-methods", "access-control-allow-headers"}
                headers = {k.lower(): v for k, v in response.getheaders() if k.lower() in allowed_headers}
                return PublicResponse(url, response.status, headers, bytes(data))
            except (OSError, http.client.HTTPException):
                raise ChannelError("network") from None
            finally:
                connection.close()
        raise ChannelError("redirect_limit")


class CommandRunner:
    """Call fixed upstream tools; a configured prefix is trusted operator configuration."""
    def run(self, argv: list[str], *, timeout: float = 20, max_bytes: int = 1024 * 1024, secrets: tuple[str, ...] = ()) -> str:
        base_names = ("PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP", "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "LANG")
        env = {key: os.environ[key] for key in (*base_names, *secrets) if key in os.environ}
        env["PYTHONIOENCODING"] = "utf-8"
        env["NO_COLOR"] = "1"
        try:
            raw = os.environ.get("CHANNELS_TOOL_PREFIXES")
            if raw is None:
                path = Path(os.environ.get("CHANNELS_TOOL_PREFIXES_FILE", str(Path(__file__).resolve().parents[2] / "config/channel-tools.local.json")))
                try:
                    raw = path.read_text(encoding="utf-8-sig")
                except FileNotFoundError:
                    raw = "{}"
            prefixes = json.loads(raw)
            prefix = prefixes.get(argv[0], [argv[0]])
            if not isinstance(prefix, list) or not prefix or not all(isinstance(v, str) and v for v in prefix):
                raise ValueError
            argv = [*prefix, *argv[1:]]
        except (ValueError, AttributeError, TypeError, OSError):
            raise ChannelError("configuration_error") from None
        if not argv or not all(isinstance(v, str) for v in argv):
            raise ChannelError("configuration_error")
        executable = shutil.which(argv[0]) or argv[0]
        # Windows batch launch may interpolate user data through cmd.exe.
        if executable.lower().endswith((".cmd", ".bat")):
            raise ChannelError("native_launcher_required")
        argv = [executable, *argv[1:]]
        flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
        try:
            process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       stdin=subprocess.DEVNULL, shell=False, env=env, **flags)
        except FileNotFoundError:
            raise ChannelError("dependency_missing") from None
        except OSError:
            raise ChannelError("dependency_unavailable") from None
        job = None
        if os.name == "nt" and hasattr(process, "_handle"):
            try:
                job = _WindowsJob(process)
            except OSError:
                process.kill()
                process.wait(timeout=3)
                process.stdout.close()
                raise ChannelError("resource_control_unavailable") from None
        chunks = queue.Queue()
        overflow = threading.Event()
        done = threading.Event()
        def read():
            size = 0
            try:
                while True:
                    chunk = process.stdout.read(8192)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > max_bytes:
                        overflow.set()
                        break
                    chunks.put(chunk)
            finally:
                done.set()
        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        deadline = time.monotonic() + timeout
        try:
            while not done.wait(0.02) or process.poll() is None:
                if overflow.is_set():
                    raise ChannelError("output_limit")
                if time.monotonic() >= deadline:
                    raise ChannelError("timeout")
            if overflow.is_set():
                raise ChannelError("output_limit")
            output = b"".join(chunks.get_nowait() for _ in range(chunks.qsize())).decode("utf-8", errors="replace")
            if process.wait():
                raise ChannelError(classify_failure(output) or "upstream_error")
            return output
        finally:
            if job:
                job.close()
            elif os.name != "nt":
                import signal
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            if process.poll() is None:
                process.kill()
                process.wait(timeout=3)
            reader.join(timeout=1)
            process.stdout.close()


class _WindowsJob:
    """The OS retains descendants after the root exits and kills them on close."""
    def __init__(self, process):
        import ctypes
        from ctypes import wintypes
        size = ctypes.c_size_t
        class BasicLimits(ctypes.Structure):
            _fields_ = [("process_time", ctypes.c_longlong), ("job_time", ctypes.c_longlong),
                        ("flags", wintypes.DWORD), ("min_working_set", size), ("max_working_set", size),
                        ("active_limit", wintypes.DWORD), ("affinity", size), ("priority", wintypes.DWORD), ("scheduling", wintypes.DWORD)]
        class IOCounters(ctypes.Structure):
            _fields_ = [(name, ctypes.c_ulonglong) for name in ("read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes")]
        class ExtendedLimits(ctypes.Structure):
            _fields_ = [("basic", BasicLimits), ("io", IOCounters), ("process_memory", size), ("job_memory", size), ("peak_process", size), ("peak_job", size)]
        api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.CreateJobObjectW.argtypes = (wintypes.LPVOID, wintypes.LPCWSTR)
        api.CreateJobObjectW.restype = wintypes.HANDLE
        api.SetInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD)
        api.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
        api.CloseHandle.argtypes = (wintypes.HANDLE,)
        self.api, self.handle = api, api.CreateJobObjectW(None, None)
        limits = ExtendedLimits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        if not api.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)) or not api.AssignProcessToJobObject(self.handle, int(process._handle)):
            error = ctypes.get_last_error()
            self.close()
            raise ctypes.WinError(error)

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None


def classify_failure(output: str) -> str | None:
    text = output.lower()
    if "browser_session_not_found" in text:
        return "auth_required"
    if any(s in text for s in ("auth_expired", "auth_required", "not_authenticated", "authrequired", "authentication required", "login required", "need login", "requires login", "not logged in", "请登录", '"logged_in": false')):
        return "auth_required"
    if any(s in text for s in ("environment_risk", "account_risk", "security_block", "captcha required", "验证码", "风控")):
        return "account_risk"
    if any(s in text for s in ("rate_limit", "free mcp rate limit", "too many requests", "http 429", "频率限制")):
        return "rate_limited"
    if "browser_connect" in text or "unknown mcp server" in text:
        return "configuration_required"
    if "failed to fetch" in text or "econnrefused" in text:
        return "network"
    return None


class ExecutionBudget:
    def __init__(self, deadline: float, max_calls: int):
        self.deadline, self.max_calls, self.used = deadline, max_calls, 0

    def remaining(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise ChannelError("budget_exceeded")
        return remaining

    def take(self):
        remaining = self.remaining()
        if self.used >= self.max_calls:
            raise ChannelError("budget_exceeded")
        self.used += 1
        return remaining
