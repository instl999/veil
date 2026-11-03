"""Server-side configs: sing-box, Caddy and the nftables port-hopping table.

Layout on the wire (one IP, one domain, everything on port 443):

  TCP 443  sing-box VLESS+REALITY+Vision.  Unauthenticated connections (probes,
           browsers, Cloudflare) are relayed byte-for-byte to Caddy on
           127.0.0.1:8443, which serves a real site with a real certificate
           for the same name ("steal from yourself").
  UDP 443  sing-box Hysteria2 with the same certificate.  Failed auth is
           answered by the same site over HTTP/3 (masquerade).
  UDP hop  nftables redirects a port range to UDP 443 for port hopping.
  CDN      Cloudflare -> TCP 443 -> REALITY relays to Caddy (SNI = cdn host)
           -> WebSocket path -> sing-box VLESS on loopback.
"""
from __future__ import annotations

import json

from .core import P, active_retired

CADDY_TLS_PORT = 8443
MASQUERADE_PORT = 8080
CADDY_ADMIN_SOCKET = "/var/lib/caddy/admin.sock"


def hy2_ready(state: dict) -> bool:
    return state["hy2"]["enabled"] and P.SITE_CRT.exists() and P.SITE_KEY.exists()


def render_singbox(state: dict) -> str:
    site = state["site_host"]
    r = state["reality"]
    reality_users = [{"name": "main", "uuid": r["uuid"], "flow": "xtls-rprx-vision"}]
    reality_users += [{"name": f"retired-{i}", "uuid": u, "flow": "xtls-rprx-vision"}
                      for i, u in enumerate(active_retired(state, "reality_uuid"))]
    inbounds = [{
        "type": "vless",
        "tag": "reality-in",
        "listen": "::",
        "listen_port": 443,
        "users": reality_users,
        "tls": {
            "enabled": True,
            "server_name": site,
            "reality": {
                "enabled": True,
                "handshake": {"server": "127.0.0.1", "server_port": CADDY_TLS_PORT},
                "private_key": r["private_key"],
                "short_id": r["short_ids"],
                "max_time_difference": "2m",
            },
        },
    }]

    if hy2_ready(state):
        h = state["hy2"]
        users = [{"name": "main", "password": h["password"]}]
        users += [{"name": f"retired-{i}", "password": p}
                  for i, p in enumerate(active_retired(state, "hy2_password"))]
        hy2 = {
            "type": "hysteria2",
            "tag": "hy2-in",
            "listen": "::",
            "listen_port": 443,
            "users": users,
            # Tell clients to use BBR rather than Hysteria's fixed-rate "Brutal"
            # sender: slower to ramp up, but far less conspicuous.
            "ignore_client_bandwidth": True,
            "masquerade": {"type": "proxy", "url": f"http://127.0.0.1:{MASQUERADE_PORT}",
                           "rewrite_host": False},
            "tls": {
                "enabled": True,
                "server_name": site,
                "alpn": ["h3"],
                "certificate_path": P.SITE_CRT.as_posix(),
                "key_path": P.SITE_KEY.as_posix(),
            },
        }
        if state["profile"]["hy2_obfs"]:
            hy2["obfs"] = {"type": "salamander", "password": h["obfs_password"]}
        inbounds.append(hy2)

    c = state["cdn"]
    if c["enabled"]:
        users = [{"name": "main", "uuid": c["uuid"]}]
        users += [{"name": f"retired-{i}", "uuid": u}
                  for i, u in enumerate(active_retired(state, "cdn_uuid"))]
        inbounds.append({
            "type": "vless",
            "tag": "cdn-in",
            "listen": "127.0.0.1",
            "listen_port": c["port"],
            "users": users,
            "transport": {"type": "ws", "path": c["path"]},
        })

    config = {
        "log": {"level": "warn", "timestamp": True},
        "dns": {"servers": [{"type": "local", "tag": "local"}]},
        "inbounds": inbounds,
        "outbounds": [{"type": "direct", "tag": "direct"}],
        "route": {
            "rules": [
                {"action": "sniff"},
                # Never let a client reach the server's own loopback/LAN services.
                # Resolve names first: the IP check alone misses "localhost" and
                # public names that point at 127.0.0.1 (localtest.me, nip.io).
                {"domain_suffix": ["localhost"], "action": "reject"},
                {"action": "resolve"},
                {"ip_is_private": True, "action": "reject"},
                # Abuse protection, so a leaked credential cannot get the VPS
                # suspended: no BitTorrent (copyright complaints) and no direct
                # mail delivery on port 25 (spam). Mail apps use 465/587.
                {"protocol": "bittorrent", "action": "reject"},
                {"port": [25], "action": "reject"},
            ],
            "final": "direct",
            "default_domain_resolver": "local",
        },
    }
    return json.dumps(config, indent=2) + "\n"


def render_caddyfile(state: dict, cdn_cert_present: bool) -> str:
    site = state["site_host"]
    c = state["cdn"]
    alt_svc = hy2_ready(state) and not state["profile"]["hy2_obfs"]

    lines = [
        "# Generated by veil from /etc/veil/state.json - edit the state, not this file.",
        "{",
        f"\temail {state['email']}",
        # A Unix socket instead of TCP 127.0.0.1:2019, so nothing reaching the
        # loopback interface (a proxy client, say) can rewrite Caddy's config.
        f"\tadmin unix/{CADDY_ADMIN_SOCKET}",
        "\thttp_port 80",
        f"\thttps_port {CADDY_TLS_PORT}",
        # A Cloudflare origin certificate is often a wildcard (*.domain). Without
        # this, Caddy sees it also matches the site host and never requests the
        # publicly trusted certificate that REALITY's self-steal depends on.
        "\tauto_https ignore_loaded_certs",
        # The self-signed fallback for the CDN host must not try (and fail, via
        # sudo) to add Caddy's local CA to the system trust store.
        "\tskip_install_trust",
        "\tservers {",
        # Caddy's HTTPS listener is only reachable through REALITY on TCP 443;
        # HTTP/3 is served by Hysteria2's masquerade on UDP 443 instead.
        "\t\tprotocols h1 h2",
        "\t}",
        "}",
        "",
        "(decoy) {",
        f"\troot * {P.WWW.as_posix()}",
        "\tencode zstd gzip",
        "\ttry_files {path} {path}/ {path}.html",
        "\tfile_server",
        "}",
        "",
        # Served on the site host and, when enabled, the CDN host: subscriptions
        # must stay reachable through Cloudflare when the server's IP is blocked,
        # or rotated credentials never reach the clients.
        "(subscription) {",
        f"\thandle_path /{state['sub_token']}/* {{",
        f"\t\troot * {P.SUB.as_posix()}",
        "\t\theader Cache-Control \"no-store\"",
        "\t\theader profile-update-interval \"12\"",
        "\t\tfile_server",
        "\t}",
        "}",
        "",
        "(errors) {",
        "\thandle_errors {",
        f"\t\troot * {P.WWW.as_posix()}",
        "\t\trewrite * /404.html",
        "\t\tfile_server",
        "\t}",
        "}",
        "",
        # Only the site host: Cloudflare reaches the CDN host on 443 alone, and
        # answering its name here would confirm to anyone who asks that this
        # server is behind it.
        f"http://{site} {{",
        "\tredir https://{host}{uri} permanent",
        "}",
        "",
        f"https://{site} {{",
        "\tbind 127.0.0.1",
        "\theader Strict-Transport-Security \"max-age=31536000\"",
    ]
    if alt_svc:
        lines.append("\theader Alt-Svc `h3=\":443\"; ma=86400`")
    lines += [
        "\timport subscription",
        "\thandle {",
        "\t\timport decoy",
        "\t}",
        "\timport errors",
        "}",
        "",
    ]

    if c["enabled"]:
        tls = (f"\ttls {P.CDN_CRT.as_posix()} {P.CDN_KEY.as_posix()} {{" if cdn_cert_present
               else "\ttls internal {")
        # Authenticated Origin Pulls: Cloudflare proves itself with a client
        # certificate. It is only required once veil has seen Cloudflare send
        # it (see system.origin_pull), so the CDN route never breaks while the
        # dashboard switch is still off.
        mode = "require_and_verify" if c.get("origin_pull") else "verify_if_given"
        old_paths = active_retired(state, "cdn_path")
        lines += [
            f"https://{c['host']} {{",
            "\tbind 127.0.0.1",
            tls,
            "\t\tclient_auth {",
            f"\t\t\tmode {mode}",
            f"\t\t\ttrust_pool file {P.PULL_CA.as_posix()}",
            "\t\t}",
            "\t}",
            # Tells veil whether Cloudflare sent its certificate (empty if not).
            f"\thandle /{state['sub_token']}-origin-pull {{",
            "\t\trespond \"{http.request.tls.client.fingerprint}\" 200",
            "\t}",
            f"\t@tunnel path {c['path']}",
            "\thandle @tunnel {",
            f"\t\treverse_proxy 127.0.0.1:{c['port']}",
            "\t}",
        ]
        if old_paths:
            # Old clients still use the previous path during the grace period.
            lines += [
                f"\t@retired path {' '.join(old_paths)}",
                "\thandle @retired {",
                f"\t\trewrite * {c['path']}",
                f"\t\treverse_proxy 127.0.0.1:{c['port']}",
                "\t}",
            ]
        lines += ["\timport subscription", "\thandle {", "\t\timport decoy", "\t}",
                  "\timport errors", "}", ""]

    lines += [
        "# Plain-HTTP copy of the site for the Hysteria2 masquerade (loopback only).",
        f"http://:{MASQUERADE_PORT} {{",
        "\tbind 127.0.0.1",
        "\timport decoy",
        "\timport errors",
        "}",
        "",
    ]
    return "\n".join(lines)


def render_nft(state: dict) -> str:
    ranges = []
    if state["hy2"]["enabled"]:
        ranges = [state["hy2"]["hop"], *active_retired(state, "hop")]
    lines = [
        "#!/usr/sbin/nft -f",
        "# Generated by veil: Hysteria2 port hopping.",
        "table inet veil",
        "delete table inet veil",
        "table inet veil {",
        "\tchain prerouting {",
        "\t\ttype nat hook prerouting priority dstnat; policy accept;",
    ]
    lines += [f"\t\tudp dport {r} redirect to :443" for r in ranges]
    lines += ["\t}", "}", ""]
    return "\n".join(lines)
