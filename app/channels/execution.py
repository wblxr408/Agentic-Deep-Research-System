"""Bounded processes and HTTPS reads. External content is data, not executable policy."""
from __future__ import annotations

import http.client
import ipaddress
import json
import os
import queue
import re
import shutil
import socket
import ssl
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote,urljoin,urlsplit

from app.channels.models import ChannelError
from app.execution_control import check_execution,current_control


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
        addresses = list(dict.fromkeys(a[4][0] for a in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM))) if resolve else []
        if resolve and (not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses)):
            raise ValueError("private DNS target")
        return host, addresses
    except socket.gaierror:
        raise ChannelError('network',diagnostics={'stage':'dns','kind':'dns_resolution_failed'}) from None
    except ValueError:
        raise ChannelError('domain_blocked',diagnostics={'stage':'validation','kind':'non_public_or_invalid_target'}) from None
    except OSError:
        raise ChannelError('network',diagnostics={'stage':'dns','kind':'dns_transport_failed'}) from None


class _PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, address, timeout):
        super().__init__(host, timeout=timeout, context=ssl.create_default_context())
        self.address = address
    def connect(self):
        check_execution()
        sock = socket.create_connection((self.address, 443), self.timeout)
        try:
            self.sock=self._context.wrap_socket(sock,server_hostname=self.host,do_handshake_on_connect=False)
            self.sock.do_handshake()
        except BaseException:
            self.close();sock.close();raise
        check_execution()


@dataclass(frozen=True)
class PublicResponse:
    url: str
    status: int
    headers: dict[str, str]
    body: bytes


def response_error(response):
    """Preserve status and retry timing, never provider text or response headers."""
    from email.utils import parsedate_to_datetime
    from datetime import UTC,datetime
    status=response.status
    category={401:'auth_required',403:'access_denied',404:'not_found',408:'timeout',410:'not_found',
        412:'account_risk',429:'rate_limited'}.get(status,'upstream_error')
    if status==403 and response.headers.get('x-ratelimit-remaining')=='0':category='rate_limited'
    detail={'stage':'http','http_status':status,'kind':'http_response_error'}
    raw=response.headers.get('retry-after')
    if isinstance(raw,str) and len(raw)<=128:
        try:delay=float(raw)
        except ValueError:
            try:delay=(parsedate_to_datetime(raw)-datetime.now(UTC)).total_seconds()
            except (TypeError,ValueError,OverflowError):delay=None
        if delay is not None and 0<=delay<=86400:detail['retry_after_seconds']=delay
    return ChannelError(category,diagnostics=detail)


def decode_public_text(response):
    """Honor declared public text encodings without running a charset plugin."""
    hint=response.headers.get('content-type','')[:512]
    declared=re.search(r'charset\s*=\s*[\"\x27]?([A-Za-z0-9_-]{1,32})',hint,re.I)
    if declared is None:
        head=response.body[:4096].decode('ascii',errors='ignore')
        declared=re.search(r'<meta\b[^>]{0,512}?charset\s*=\s*[\"\x27]?([A-Za-z0-9_-]{1,32})',head,re.I)
    choices={'utf-8':'utf-8-sig','utf8':'utf-8-sig','gb2312':'gb18030','gbk':'gb18030','gb18030':'gb18030',
        'big5':'big5','iso-8859-1':'iso-8859-1','windows-1252':'cp1252','utf-16':'utf-16','utf-16le':'utf-16-le','utf-16be':'utf-16-be'}
    encoding=choices.get(declared[1].lower(),'utf-8-sig') if declared else 'utf-8-sig'
    return response.body.decode(encoding,errors='replace'),encoding


class HttpReader:
    def __init__(self, *, url_validator=None):
        self.url_validator = url_validator

    def get(self, url: str, *, timeout: float = 20, max_bytes: int = 1024 * 1024,on_request=None) -> str:
        response = self.read(url, timeout=timeout, max_bytes=max_bytes,on_request=on_request)
        if response.status >= 400:
            raise response_error(response)
        return decode_public_text(response)[0]

    def get_github(self, url: str, *, credential=None, timeout: float = 20,
                   max_bytes: int = 1024 * 1024,on_request=None) -> str:
        response = self.read(url,timeout=timeout,max_bytes=max_bytes,on_request=on_request,
                             _github_api=True,_github_credential=credential)
        if response.status >= 400:
            raise response_error(response)
        return decode_public_text(response)[0]

    def read(self, url: str, *, method: str = "GET", timeout: float = 20, max_bytes: int = 1024 * 1024,on_request=None,
             _github_api: bool = False,_github_credential=None,conditional: dict | None = None) -> PublicResponse:
        if method not in {"GET", "HEAD"}:
            raise ChannelError("read_only")
        deadline = time.monotonic() + timeout
        for _ in range(4):
            check_execution()
            if self.url_validator is not None:
                self.url_validator(url)
            try: parsed = urlsplit(url)
            except ValueError: raise ChannelError('domain_blocked') from None
            if _github_api:
                # Only the fixed API endpoints are used, even for anonymous requests.
                from app.data_governance import sensitive_url
                allowed_path = re.fullmatch(r'/search/repositories|/repos/[^/]+/[^/]+(?:/readme)?|/repositories/[0-9]+(?:/readme)?',parsed.path)
                if parsed.scheme != 'https' or parsed.hostname != 'api.github.com' or not allowed_path or method != 'GET' or sensitive_url(url):
                    raise ChannelError('personal_connection_redirect_blocked')
            host, addresses = public_url(url, resolve=True)
            # Try both address families before spending the entire deadline on
            # one unusable route. All answers were checked above; no DNS rebind.
            other=next((value for value in addresses if (':' in value)!=(':' in addresses[0])),None)
            ordered=list(dict.fromkeys([addresses[0],*([other] if other else []),*addresses]))[:3]
            redirected=False
            for index,address in enumerate(ordered):
                check_execution()
                remaining=deadline-time.monotonic()
                if on_request is not None:remaining=min(remaining,on_request())
                if remaining<=0:raise ChannelError('timeout',diagnostics={'stage':'admission','kind':'read_deadline'})
                connection=_PinnedHTTPS(host,address,min(10,max(.1,remaining/(len(ordered)-index))))
                control=current_control();close_key='http:'+str(id(connection));stage='connect'
                def abort(connection=connection):
                    if connection.sock:
                        try:connection.sock.shutdown(socket.SHUT_RDWR)
                        except OSError:pass
                    connection.close()
                if control:control.add_closer(close_key,abort)
                try:
                    headers={'User-Agent':'DeepIntel/1.0','Accept':'application/json,text/plain,text/html,*/*','Accept-Encoding':'identity'}
                    for key,header in (('etag','If-None-Match'),('last_modified','If-Modified-Since')):
                        value=(conditional or {}).get(key)
                        if isinstance(value,str) and 0<len(value)<=512 and all(32<=ord(char)<=126 for char in value):headers[header]=value
                    if _github_api:headers.update({'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2026-03-10'})
                    if _github_credential is not None:
                        credential=_github_credential()
                        if not isinstance(credential,str) or not 20<=len(credential)<=512 or not re.fullmatch(r'[A-Za-z0-9_.-]+',credential):
                            raise ChannelError('personal_connection_unavailable')
                        headers['Authorization']='Bearer '+credential
                    connection.connect();stage='request'
                    if time.monotonic()>=deadline:raise ChannelError('timeout',diagnostics={'stage':stage,'kind':'read_deadline'})
                    connection.sock.settimeout(max(.001,deadline-time.monotonic()))
                    target=quote(parsed.path or '/',safe="/%:@-._~!$&'()*+,;=")
                    if parsed.query:target+='?'+quote(parsed.query,safe="/%?:@-._~!$&'()*+,;=")
                    connection.request(method,target,headers=headers)
                    stage='headers';response=connection.getresponse()
                    if response.status in (301,302,303,307,308):
                        if _github_api:raise ChannelError('github_redirect_blocked')
                        url=urljoin(url,response.getheader('Location',''));redirected=True;break
                    allowed_headers={'content-type','content-language','cache-control','etag','last-modified','date','expires',
                        'content-security-policy','x-frame-options','access-control-allow-origin','access-control-allow-methods',
                        'access-control-allow-headers','x-ratelimit-remaining','retry-after'}
                    headers={key.lower():value for key,value in response.getheaders() if key.lower() in allowed_headers}
                    if response.status>=400:return PublicResponse(url,response.status,headers,b'')
                    stage='body';data=bytearray()
                    while method!='HEAD':
                        check_execution()
                        if time.monotonic()>=deadline:raise ChannelError('timeout',diagnostics={'stage':stage,'kind':'read_deadline'})
                        if connection.sock:connection.sock.settimeout(max(.001,deadline-time.monotonic()))
                        chunk=response.read(min(8192,max_bytes-len(data)+1))
                        if not chunk:break
                        data.extend(chunk)
                        if len(data)>max_bytes:raise ChannelError('output_limit',diagnostics={'stage':stage,'kind':'response_byte_limit'})
                    return PublicResponse(url,response.status,headers,bytes(data))
                except ssl.SSLCertVerificationError:
                    raise ChannelError('tls_validation_failed',diagnostics={'stage':'tls','kind':'certificate_verification_failed'}) from None
                except (OSError,http.client.HTTPException) as error:
                    category='timeout' if isinstance(error,(TimeoutError,socket.timeout)) else 'network'
                    kind='socket_timeout' if category=='timeout' else 'tls_handshake_failed' if isinstance(error,ssl.SSLError) else 'connection_or_http_transport_failed'
                    failure=ChannelError(category,diagnostics={'stage':stage,'kind':kind,'address_attempt':index+1})
                    if index+1==len(ordered) or time.monotonic()>=deadline:raise failure from None
                finally:
                    if control:control.remove_closer(close_key)
                    connection.close()
            if not redirected:raise ChannelError('network',diagnostics={'stage':'connect','kind':'all_public_addresses_failed'})
        raise ChannelError("redirect_limit")


class CommandRunner:
    """Call fixed upstream tools; a configured prefix is trusted operator configuration."""
    def run(self, argv: list[str], *, timeout: float = 20, max_bytes: int = 1024 * 1024, secrets: tuple[str, ...] = ()) -> str:
        check_execution()
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
            check_execution()
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
                check_execution()
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
        self.attempt_deadline=None
        self.attempt_max_calls=None

    def remaining(self):
        check_execution()
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise ChannelError("budget_exceeded")
        if self.attempt_deadline is not None:
            remaining=min(remaining,self.attempt_deadline-time.monotonic())
            if remaining<=0:raise ChannelError('timeout')
        return remaining

    def take(self):
        remaining = self.remaining()
        if self.used >= self.max_calls:
            raise ChannelError("budget_exceeded")
        if self.attempt_max_calls is not None and self.used>=self.attempt_max_calls:
            raise ChannelError('backend_share_exhausted')
        self.used += 1
        return remaining
