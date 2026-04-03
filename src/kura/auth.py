"""OAuth support for MCP server connections.

Provides token storage, a local callback server, and helpers
to build an OAuthClientProvider for the MCP SDK.

Requires: pip install kura-mcp[dump]
"""

import asyncio
import json
import os
import re
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from mcp.client.auth import OAuthClientProvider
from mcp.shared.auth import (
    OAuthClientInformationFull,
    OAuthClientMetadata,
    OAuthToken,
)

OAUTH_DIR = Path.home() / ".kura" / "oauth"
OAUTH_CALLBACK_PORTS = [19876, 19877, 19878]
CALLBACK_PATH = "/callback"


# ---------------------------------------------------------------------------
# Token storage
# ---------------------------------------------------------------------------

class FileTokenStorage:
    """Persist OAuth tokens and client info to ~/.kura/oauth/<server>/."""

    def __init__(self, server_name: str):
        safe = re.sub(r"[^\w\-.]", "_", server_name)
        self._dir = OAUTH_DIR / safe

    @property
    def path(self) -> Path:
        return self._dir

    # --- TokenStorage protocol ---

    async def get_tokens(self) -> OAuthToken | None:
        return self._read_model(
            self._dir / "tokens.json", OAuthToken,
        )

    async def set_tokens(self, tokens: OAuthToken) -> None:
        self._write(
            self._dir / "tokens.json",
            tokens.model_dump_json(indent=2),
        )

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        return self._read_model(
            self._dir / "client_info.json",
            OAuthClientInformationFull,
        )

    async def set_client_info(
        self, client_info: OAuthClientInformationFull,
    ) -> None:
        self._write(
            self._dir / "client_info.json",
            client_info.model_dump_json(indent=2),
        )

    # --- Utilities ---

    def clear_tokens(self) -> None:
        p = self._dir / "tokens.json"
        if p.exists():
            p.unlink()

    def clear_all(self) -> None:
        if self._dir.exists():
            for f in self._dir.iterdir():
                f.unlink()
            self._dir.rmdir()

    def _read_model(self, path: Path, model_cls):
        if not path.exists():
            return None
        try:
            return model_cls.model_validate_json(path.read_text())
        except Exception:
            return None

    def _write(self, path: Path, data: str) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        path.write_text(data)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass  # Windows doesn't support Unix permissions


# ---------------------------------------------------------------------------
# OAuth callback server
# ---------------------------------------------------------------------------

class OAuthCallbackServer:
    """Minimal HTTP server to receive the OAuth redirect."""

    def __init__(self, port: int):
        self.port = port
        loop = asyncio.get_running_loop()
        self._result: asyncio.Future[tuple[str, str | None]] = (
            loop.create_future()
        )
        self._server: asyncio.Server | None = None

    async def start(self) -> None:
        self._server = await asyncio.start_server(
            self._handle, "127.0.0.1", self.port,
        )

    async def wait_for_callback(
        self, timeout: float = 300.0,
    ) -> tuple[str, str | None]:
        return await asyncio.wait_for(self._result, timeout)

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    async def _handle(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            data = await reader.read(8192)
            request_line = data.decode("utf-8", errors="replace")
            request_line = request_line.split("\r\n")[0]
            # "GET /callback?code=X&state=Y HTTP/1.1"
            path = request_line.split(" ")[1] if " " in request_line else ""
            parsed = urlparse(path)
            params = parse_qs(parsed.query)

            code = params.get("code", [None])[0]
            state = params.get("state", [None])[0]
            error = params.get("error", [None])[0]

            if error:
                body = (
                    "<html><body>"
                    f"<h2>Authentication failed: {error}</h2>"
                    "<p>You can close this tab.</p>"
                    "</body></html>"
                )
                status = "400 Bad Request"
            elif code:
                body = (
                    "<html><body>"
                    "<h2>Authentication successful!</h2>"
                    "<p>You can close this tab and return to "
                    "the terminal.</p>"
                    "</body></html>"
                )
                status = "200 OK"
            else:
                body = (
                    "<html><body>"
                    "<h2>Missing authorization code</h2>"
                    "</body></html>"
                )
                status = "400 Bad Request"

            response = (
                f"HTTP/1.1 {status}\r\n"
                f"Content-Type: text/html; charset=utf-8\r\n"
                f"Content-Length: {len(body)}\r\n"
                f"Connection: close\r\n"
                f"\r\n"
                f"{body}"
            )
            writer.write(response.encode())
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

        if not self._result.done():
            if error:
                self._result.set_exception(
                    RuntimeError(f"OAuth error: {error}")
                )
            elif code:
                self._result.set_result((code, state))
            else:
                self._result.set_exception(
                    RuntimeError("No authorization code received")
                )


# ---------------------------------------------------------------------------
# Build OAuth auth
# ---------------------------------------------------------------------------

async def _find_available_port(
    ports: list[int],
) -> int:
    """Try binding to each port, return the first available."""
    for port in ports:
        try:
            server = await asyncio.start_server(
                lambda r, w: None, "127.0.0.1", port,
            )
            server.close()
            await server.wait_closed()
            return port
        except OSError:
            continue
    raise RuntimeError(
        f"Cannot start OAuth callback server. "
        f"Ports {ports} are all in use."
    )


async def build_oauth_auth(
    server_name: str,
    server_url: str,
    on_progress=None,
) -> tuple[OAuthClientProvider, object]:
    """Create an OAuthClientProvider for an MCP server.

    Returns (auth_provider, cleanup_fn). Call cleanup_fn() when done.
    """
    storage = FileTokenStorage(server_name)

    # Determine port: reuse from stored registration if possible
    existing_client = await storage.get_client_info()
    if existing_client and existing_client.redirect_uris:
        uri = str(existing_client.redirect_uris[0])
        stored_port = urlparse(uri).port
        # Verify port is available
        try:
            test = await asyncio.start_server(
                lambda r, w: None, "127.0.0.1", stored_port,
            )
            test.close()
            await test.wait_closed()
            port = stored_port
        except OSError:
            raise RuntimeError(
                f"Port {stored_port} is needed for OAuth with "
                f"'{server_name}' but is in use. Free the port or "
                f"run: kura auth logout --full {server_name}"
            )
    else:
        port = await _find_available_port(OAUTH_CALLBACK_PORTS)

    redirect_uri = f"http://localhost:{port}{CALLBACK_PATH}"

    callback_server = OAuthCallbackServer(port)
    await callback_server.start()

    async def redirect_handler(authorization_url: str) -> None:
        if on_progress:
            on_progress("Opening browser for authentication...")
        webbrowser.open(authorization_url)
        if on_progress:
            # Always print URL — webbrowser.open() is unreliable
            # on WSL, headless, and SSH sessions.
            on_progress(
                "  If the browser didn't open, visit this URL:"
            )
            on_progress(f"  {authorization_url}")

    async def callback_handler() -> tuple[str, str | None]:
        try:
            return await callback_server.wait_for_callback()
        finally:
            await callback_server.stop()

    client_metadata = OAuthClientMetadata(
        redirect_uris=[redirect_uri],
        token_endpoint_auth_method="none",
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        client_name="kura",
    )

    provider = OAuthClientProvider(
        server_url=server_url,
        client_metadata=client_metadata,
        storage=storage,
        redirect_handler=redirect_handler,
        callback_handler=callback_handler,
        timeout=300.0,
    )

    async def cleanup():
        await callback_server.stop()

    return provider, cleanup


# ---------------------------------------------------------------------------
# CLI utilities
# ---------------------------------------------------------------------------

def get_stored_servers() -> list[tuple[str, Path]]:
    """List all servers with stored OAuth data."""
    if not OAUTH_DIR.exists():
        return []
    return [
        (d.name, d)
        for d in sorted(OAUTH_DIR.iterdir())
        if d.is_dir()
    ]


def get_token_status(server_dir: Path) -> dict:
    """Get token status info for display."""
    tokens_path = server_dir / "tokens.json"
    client_path = server_dir / "client_info.json"
    status = {
        "has_tokens": tokens_path.exists(),
        "has_client": client_path.exists(),
        "client_id": None,
    }
    if client_path.exists():
        try:
            data = json.loads(client_path.read_text())
            status["client_id"] = data.get("client_id", "")
        except Exception:
            pass
    return status
