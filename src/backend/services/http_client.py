"""HTTP client utilities with retry/backoff semantics."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, Iterable, Optional

import logging

import httpx
from tenacity import AsyncRetrying, RetryError, retry_if_exception_type, stop_after_attempt, wait_random_exponential

logger = logging.getLogger(__name__)

RETRYABLE_STATUS_CODES: set[int] = {429, 500, 502, 503, 504}
DEFAULT_CONNECT_TIMEOUT = 3.0
DEFAULT_READ_TIMEOUT = 60.0
DEFAULT_TOTAL_ATTEMPTS = 5


class TransientHttpError(Exception):
    """Raised when an HTTP response indicates a transient failure."""

    def __init__(self, response: httpx.Response):
        self.response = response
        message = f"Transient HTTP error {response.status_code} for {response.request.method} {response.request.url}"
        super().__init__(message)


class AsyncHttpClient:
    """httpx.AsyncClient wrapper with consistent retry/backoff behaviour."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        default_headers: Optional[Dict[str, str]] = None,
        connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
        read_timeout: float = DEFAULT_READ_TIMEOUT,
        max_connections: int = 20,
    ) -> None:
        headers = default_headers or {}
        if "Accept" not in headers:
            headers["Accept"] = "application/json"

        timeout = httpx.Timeout(
            connect=connect_timeout,
            read=read_timeout,
            write=None,
            pool=None,
        )
        limits = httpx.Limits(max_connections=max_connections, max_keepalive_connections=max_connections // 2 or 1)

        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers=headers,
            timeout=timeout,
            limits=limits,
            http2=False,
        )

    @property
    def client(self) -> httpx.AsyncClient:
        return self._client

    async def close(self) -> None:
        await self._client.aclose()

    async def request(
        self,
        method: str,
        url: str,
        *,
        expected_status: Optional[Iterable[int]] = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """Send an HTTP request with retry logic."""

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(DEFAULT_TOTAL_ATTEMPTS),
            wait=wait_random_exponential(multiplier=1, max=30),
            retry=retry_if_exception_type((httpx.HTTPError, TransientHttpError)),
            reraise=True,
        ):
            with attempt:
                response = await self._client.request(method, url, **kwargs)
                if response.status_code in RETRYABLE_STATUS_CODES:
                    raise TransientHttpError(response)

                if expected_status and response.status_code not in expected_status:
                    try:
                        response.raise_for_status()
                    except httpx.HTTPStatusError as exc:
                        body = exc.response.text if exc.response is not None else "<no body>"
                        status = getattr(exc.response, "status_code", "?")
                        logger.error(
                            "HTTP %s %s failed with status %s: %s",
                            method,
                            response.request.url,
                            status,
                            body,
                        )
                        raise

                return response

        raise RuntimeError("Unexpected retry exhaustion")

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("PUT", url, **kwargs)

    async def delete(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("DELETE", url, **kwargs)


@asynccontextmanager
async def build_default_client(
    base_url: Optional[str] = None,
    default_headers: Optional[Dict[str, str]] = None,
    connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
    read_timeout: float = DEFAULT_READ_TIMEOUT,
    max_connections: int = 20,
) -> AsyncIterator[AsyncHttpClient]:
    """Convenience context manager for one-off clients."""

    client = AsyncHttpClient(
        base_url=base_url,
        default_headers=default_headers,
        connect_timeout=connect_timeout,
        read_timeout=read_timeout,
        max_connections=max_connections,
    )
    try:
        yield client
    finally:
        await client.close()
