"""Streamable HTTP entrypoint for the Borsdata MCP server."""
import contextlib
import logging
import os

import uvicorn
from starlette.applications import Starlette
from starlette.routing import Mount, Route
from starlette.responses import PlainTextResponse
from starlette.types import Receive, Scope, Send

from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings

from .server import BorsdataMCPServer

logger = logging.getLogger("borsdata-mcp-http")


def _bool_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _csv_env(name: str) -> list[str]:
    raw = os.environ.get(name, "").strip()
    return [item.strip() for item in raw.split(",") if item.strip()]


def build_app() -> Starlette:
    borsdata = BorsdataMCPServer()  # raises if BORSDATA_API_KEY is missing

    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=not _bool_env(
            "MCP_DISABLE_DNS_REBINDING_PROTECTION"
        ),
        allowed_hosts=_csv_env("MCP_ALLOWED_HOSTS"),
        allowed_origins=_csv_env("MCP_ALLOWED_ORIGINS"),
    )

    session_manager = StreamableHTTPSessionManager(
        app=borsdata.server,
        json_response=_bool_env("MCP_JSON_RESPONSE"),
        stateless=_bool_env("MCP_STATELESS"),
        security_settings=security,
    )

    auth_token = os.environ.get("MCP_AUTH_TOKEN", "").strip()

    async def handle_mcp(scope: Scope, receive: Receive, send: Send) -> None:
        if auth_token:
            headers = dict(scope.get("headers") or [])
            provided = headers.get(b"authorization", b"").decode()
            if provided != f"Bearer {auth_token}":
                await send({"type": "http.response.start", "status": 401,
                            "headers": [(b"content-type", b"text/plain")]})
                await send({"type": "http.response.body", "body": b"Unauthorized"})
                return
        await session_manager.handle_request(scope, receive, send)

    async def health(_request) -> PlainTextResponse:
        return PlainTextResponse("ok")

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        async with session_manager.run():
            logger.info("Borsdata MCP streamable-HTTP session manager started")
            yield

    return Starlette(
        debug=False,
        routes=[Route("/health", endpoint=health), Mount("/mcp", app=handle_mcp)],
        lifespan=lifespan,
    )


app = build_app()


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    uvicorn.run(
        app,
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "8000")),
        proxy_headers=True,
        # Behind Coolify/Traefik/etc., the proxy IP isn't 127.0.0.1, so uvicorn
        # ignores X-Forwarded-Proto by default and builds http:// redirects for
        # https:// requests. Trust the headers from any proxy hop.
        forwarded_allow_ips=os.environ.get("FORWARDED_ALLOW_IPS", "*"),
    )


if __name__ == "__main__":
    main()
