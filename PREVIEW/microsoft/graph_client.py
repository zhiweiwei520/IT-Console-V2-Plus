"""Async Microsoft Graph client with strict endpoint allowlist。"""
from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Protocol
from urllib.parse import urlparse

import httpx

from app.microsoft.token_broker import TokenBroker

GRAPH_ORIGIN = "https://graph.microsoft.com"
GRAPH_V1_BASE = GRAPH_ORIGIN + "/v1.0"


class GraphRetryableError(RuntimeError):
    def __init__(self, code: str, *, retry_after: int, status_code: int | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.retry_after = retry_after
        self.status_code = status_code


class GraphTerminalError(RuntimeError):
    def __init__(self, code: str, *, status_code: int | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


class GraphClient(Protocol):
    async def get(self, resource: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]: ...
    async def paged_get(
        self, resource: str, *, params: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]: ...


class HttpGraphClient:
    def __init__(self, token_broker: TokenBroker, tenant, connection, http_client: httpx.AsyncClient) -> None:
        self.token_broker = token_broker
        self.tenant = tenant
        self.connection = connection
        self.http_client = http_client

    async def get(self, resource: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = self._allowed_url(resource)
        try:
            token = await asyncio.to_thread(
                self.token_broker.acquire_token, self.tenant, self.connection,
            )
            response = await self.http_client.get(
                url,
                params=params,
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            )
        except GraphTerminalError:
            raise
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise GraphRetryableError("graph_transport_error", retry_after=30) from exc

        if response.status_code in (408, 429) or response.status_code >= 500:
            raise GraphRetryableError(
                "graph_throttled" if response.status_code == 429 else "graph_service_unavailable",
                retry_after=self._retry_after(response),
                status_code=response.status_code,
            )
        if response.status_code in (401, 403):
            raise GraphTerminalError("graph_authorization_failed", status_code=response.status_code)
        if response.status_code >= 400:
            raise GraphTerminalError("graph_request_rejected", status_code=response.status_code)
        try:
            payload = response.json()
        except ValueError as exc:
            raise GraphTerminalError("graph_response_not_json", status_code=response.status_code) from exc
        if not isinstance(payload, dict):
            raise GraphTerminalError("graph_response_invalid", status_code=response.status_code)
        return payload

    async def paged_get(
        self, resource: str, *, params: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        next_resource = resource
        next_params = params
        while next_resource:
            page = await self.get(next_resource, params=next_params)
            yield page
            next_resource = page.get("@odata.nextLink")
            if next_resource is not None and not isinstance(next_resource, str):
                raise GraphTerminalError("graph_next_link_invalid")
            next_params = None

    @staticmethod
    def _allowed_url(resource: str) -> str:
        if resource.startswith("/"):
            if resource.startswith("/v1.0/"):
                return GRAPH_ORIGIN + resource
            if resource.startswith("/beta/"):
                raise GraphTerminalError("graph_beta_not_allowed")
            return GRAPH_V1_BASE + resource
        parsed = urlparse(resource)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "graph.microsoft.com"
            or parsed.port not in (None, 443)
            or not parsed.path.startswith("/v1.0/")
            or parsed.username is not None
        ):
            raise GraphTerminalError("graph_endpoint_not_allowed")
        return resource

    @staticmethod
    def _retry_after(response: httpx.Response) -> int:
        try:
            value = int(response.headers.get("Retry-After", "30"))
        except ValueError:
            value = 30
        return max(1, min(value, 3600))
