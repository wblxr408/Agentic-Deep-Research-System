"""HTTP boundary protections applied once for every request."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.gzip import GZipMiddleware


from starlette.responses import JSONResponse

from app.config import get_settings


class InMemoryRateLimiter:
    """Conservative local limiter; failed shared caches never grant access."""
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allowed(self, key: str, limit: int, period: int = 60) -> bool:
        now = time.monotonic()
        bucket = self._hits[key]
        while bucket and now - bucket[0] >= period:
            bucket.popleft()
        if len(bucket) >= limit:
            return False
        bucket.append(now)
        return True


rate_limiter = InMemoryRateLimiter()
PUBLIC_PATHS = {"/", "/api/v1/health", "/api/v1/ready", "/api/v1/auth/status", "/api/v1/auth/initialize", "/api/v1/auth/login", "/api/v1/auth/register"}


class LayoutUploadLimitMiddleware:
    """Bound multipart intake before Starlette can spool an unbounded upload."""
    def __init__(self,app):
        self.app=app
        self._slots=asyncio.Semaphore(8)

    async def __call__(self,scope,receive,send):
        path=scope.get('path','')
        if scope.get('type')!='http' or scope.get('method')!='POST' or path not in {
                '/api/v1/research/layout-samples','/api/v1/research/layout-samples/operations'}:
            await self.app(scope,receive,send)
            return
        try:
            await asyncio.wait_for(self._slots.acquire(),timeout=2)
        except TimeoutError:
            await JSONResponse({'detail':'layout_upload_busy'},status_code=429)(scope,receive,send)
            return
        try:
            await self._accept(scope,receive,send)
        finally:
            self._slots.release()

    async def _accept(self,scope,receive,send):
        maximum=2*1024*1024+32768
        chunks=[];size=0
        try:
            async with asyncio.timeout(45):
                while True:
                    message=await receive()
                    if message['type']=='http.disconnect':
                        return
                    if message['type']!='http.request':
                        continue
                    body=message.get('body',b'');size+=len(body)
                    if size>maximum:
                        await JSONResponse({'detail':'layout_sample_size_limit'},status_code=413)(scope,receive,send)
                        return
                    chunks.append(body)
                    if not message.get('more_body',False):
                        break
        except TimeoutError:
            await JSONResponse({'detail':'layout_upload_timeout'},status_code=408)(scope,receive,send)
            return
        complete=b''.join(chunks);sent=False
        async def replay():
            nonlocal sent
            if not sent:
                sent=True
                return {'type':'http.request','body':complete,'more_body':False}
            return await receive()
        await self.app(scope,replay,send)


class StreamingGZipMiddleware(GZipMiddleware):
    """Keep event boundaries flushable on the installed Starlette runtime."""
    async def __call__(self, scope, receive, send):
        path=scope.get('path','')
        if scope['type']=='http' and (path.startswith('/api/v1/research/stream/') or
                path.startswith('/api/v1/research/layout-samples/operations/') and path.endswith('/events')):
            await self.app(scope,receive,send)
        else:
            await super().__call__(scope,receive,send)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        settings = get_settings()
        path = request.url.path
        client = request.client.host if request.client else "unknown"
        if path == "/api/v1/auth/login" and not rate_limiter.allowed(f"login:{client}", settings.security.login_rate_limit):
            return JSONResponse({"detail": "rate_limited"}, status_code=429)
        if path in {"/api/v1/auth/register", "/api/v1/auth/initialize"} and request.method == 'POST' and not rate_limiter.allowed(f"register:{client}", settings.security.registration_rate_limit):
            return JSONResponse({"detail": "rate_limited"}, status_code=429)
        if path == "/api/v1/documents/upload" and not rate_limiter.allowed(f"upload:{client}", settings.security.upload_rate_limit):
            return JSONResponse({"detail": "rate_limited"}, status_code=429)
        if settings.security.auth_enabled and path.startswith("/api/") and path not in PUBLIC_PATHS:
            authorization = request.headers.get("authorization")
            if not authorization and not request.cookies.get(settings.security.cookie_name):
                return JSONResponse({"detail": "authentication_required"}, status_code=401)
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = "default-src 'self'; base-uri 'self'; frame-ancestors 'none'; object-src 'none'"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        return response
