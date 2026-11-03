"""Small network helpers shared by the health checks (stdlib only)."""
from __future__ import annotations

import json
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request

# Cloudflare's bot rules answer 403 to the default "Python-urllib" agent.
USER_AGENT = "Mozilla/5.0 (veil health check)"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def fetch(url: str, timeout: float = 15, redirects: bool = True, data: bytes | None = None,
          headers: dict | None = None) -> tuple[int | None, dict, bytes, str]:
    """GET (or POST with data) a URL. Returns (status, headers, first 64 KiB of
    the body, error). status is None when no HTTP answer came back at all."""
    req = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT,
                                                          **(headers or {})})
    opener = (urllib.request.build_opener() if redirects
              else urllib.request.build_opener(_NoRedirect))
    try:
        with opener.open(req, timeout=timeout) as res:
            return res.status, dict(res.headers), res.read(65536), ""
    except urllib.error.HTTPError as exc:
        body = exc.read(65536) if exc.fp else b""
        return exc.code, dict(exc.headers or {}), body, ""
    except (OSError, ValueError) as exc:
        return None, {}, b"", str(getattr(exc, "reason", exc))


def download(url: str, dest, timeout: float = 60) -> None:
    """Save a whole file (fetch() keeps only the first 64 KiB)."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as res, open(dest, "wb") as fh:
        while chunk := res.read(65536):
            fh.write(chunk)


def public_ipv4() -> str | None:
    status, _, body, _ = fetch("https://api.ipify.org", timeout=8)
    text = body.decode(errors="replace").strip()
    return text if status == 200 and text.count(".") == 3 else None


def resolve_a(host: str) -> list[str]:
    """A records as a public resolver sees them (not this server's cache)."""
    url = "https://cloudflare-dns.com/dns-query?" + urllib.parse.urlencode({"name": host, "type": "A"})
    status, _, body, _ = fetch(url, timeout=8, headers={"accept": "application/dns-json"})
    if status == 200:
        try:
            return [a["data"] for a in json.loads(body).get("Answer", []) if a.get("type") == 1]
        except ValueError:
            pass
    try:
        return sorted({ai[4][0] for ai in socket.getaddrinfo(host, None, socket.AF_INET)})
    except OSError:
        return []


def behind_cloudflare(host: str) -> bool:
    status, _, body, _ = fetch(f"http://{host}/cdn-cgi/trace", timeout=8)
    return status == 200 and b"fl=" in body


def websocket_upgrade(host: str, path: str, timeout: float = 10) -> str:
    """Open a WebSocket handshake to https://host/path; returns the status line
    (e.g. "HTTP/1.1 101 Switching Protocols") or an error description."""
    ctx = ssl.create_default_context()
    try:
        with socket.create_connection((host, 443), timeout=timeout) as raw:
            with ctx.wrap_socket(raw, server_hostname=host) as tls:
                tls.sendall((f"GET {path} HTTP/1.1\r\nHost: {host}\r\nUser-Agent: {USER_AGENT}\r\n"
                             "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                             "Sec-WebSocket-Key: dmVpbC1oZWFsdGgtY2hlY2s=\r\n"
                             "Sec-WebSocket-Version: 13\r\n\r\n").encode())
                head = tls.recv(256).decode(errors="replace")
                return head.split("\r\n", 1)[0] or "empty reply"
    except (OSError, ssl.SSLError) as exc:
        return f"error: {exc}"
