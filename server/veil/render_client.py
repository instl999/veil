"""Client configs: one mihomo (Clash Meta) profile per device, plus share links.

mihomo profiles work in Clash Verge Rev (Windows/macOS), FlClash (Android/
Windows/macOS/Linux), OpenClash (OpenWrt) and Stash (iOS).  Share links / the
base64 subscription are for Shadowrocket.
"""
from __future__ import annotations

import base64
from urllib.parse import quote, urlencode

from . import yamlout
from .render_server import hy2_ready

GEO_MIRROR = "https://testingcf.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@release"
HEALTH_URL = "https://www.gstatic.com/generate_204"

# Steam picks content servers inside China; keep those downloads off the proxy.
GAME_DOWNLOAD_SUFFIXES = ("steamcontent.com", "steamserver.net", "steamchina.com")


def available_routes(state: dict) -> list[str]:
    routes = ["REALITY"]
    if hy2_ready(state):
        routes.append("HY2")
    if state["cdn"]["enabled"]:
        routes.append("CDN")
    return routes


def _proxies(state: dict, fingerprint: str) -> list[dict]:
    site = state["site_host"]
    r = state["reality"]
    proxies = [{
        "name": "REALITY",
        "type": "vless",
        "server": site,
        "port": 443,
        "uuid": r["uuid"],
        "network": "tcp",
        "tls": True,
        "udp": True,
        "flow": "xtls-rprx-vision",
        "servername": site,
        "client-fingerprint": fingerprint,
        "reality-opts": {"public-key": r["public_key"], "short-id": r["short_ids"][0]},
    }]
    if hy2_ready(state):
        h = state["hy2"]
        hy2 = {
            "name": "HY2",
            "type": "hysteria2",
            "server": site,
            "port": 443,
            "ports": h["hop"],
            "hop-interval": state["profile"]["hop_interval"],
            "password": h["password"],
            "sni": site,
            "alpn": ["h3"],
            "skip-cert-verify": False,
        }
        if state["profile"]["hy2_obfs"]:
            hy2["obfs"] = "salamander"
            hy2["obfs-password"] = h["obfs_password"]
        proxies.append(hy2)
    c = state["cdn"]
    if c["enabled"]:
        proxies.append({
            "name": "CDN",
            "type": "vless",
            "server": c["host"],
            "port": 443,
            "uuid": c["uuid"],
            "udp": True,
            "tls": True,
            "servername": c["host"],
            "client-fingerprint": fingerprint,
            "network": "ws",
            "ws-opts": {"path": c["path"], "headers": {"Host": c["host"]}},
        })
    return proxies


def render_mihomo(state: dict, device: str) -> str:
    prof = state["profile"]
    fp = prof["devices"][device]["fingerprint"]
    avail = available_routes(state)
    order = lambda cls: [r for r in prof["routes"][cls] if r in avail] or avail
    check = {"url": HEALTH_URL, "interval": prof["healthcheck_interval"], "lazy": True,
             "timeout": 5000}

    config = {
        "mixed-port": 7890,
        "allow-lan": False,
        "mode": "rule",
        "log-level": "warning",
        "ipv6": False,
        "unified-delay": True,
        "tcp-concurrent": True,
        "find-process-mode": "off",
        "profile": {"store-selected": True},
        "geo-auto-update": True,
        "geo-update-interval": 168,
        "geox-url": {
            "geoip": f"{GEO_MIRROR}/geoip.dat",
            "geosite": f"{GEO_MIRROR}/geosite.dat",
            "mmdb": f"{GEO_MIRROR}/country.mmdb",
        },
        "dns": {
            "enable": True,
            "ipv6": False,
            "enhanced-mode": "fake-ip",
            "fake-ip-range": "198.18.0.1/16",
            "fake-ip-filter": ["*.lan", "+.local", "+.msftconnecttest.com", "+.msftncsi.com",
                               "time.*.com", "ntp.*.com", "+.market.xiaomi.com"],
            # Foreign lookups travel through the proxy (respect-rules), so the
            # domestic resolvers only ever see domestic names.
            "respect-rules": True,
            "default-nameserver": ["223.5.5.5", "119.29.29.29"],
            "proxy-server-nameserver": ["https://223.5.5.5/dns-query", "https://doh.pub/dns-query"],
            "nameserver": ["https://1.1.1.1/dns-query", "https://8.8.8.8/dns-query"],
            "nameserver-policy": {
                "geosite:cn,private": ["https://223.5.5.5/dns-query", "https://doh.pub/dns-query"],
            },
        },
        "proxies": _proxies(state, fp),
        "proxy-groups": [
            {"name": "PROXY", "type": "select", "proxies": ["AUTO", *avail]},
            {"name": "AUTO", "type": "fallback", "proxies": order("browse"), **check},
            {"name": "MEDIA", "type": "fallback", "proxies": order("media"), **check},
            {"name": "GAMES", "type": "select", "proxies": ["DIRECT", "MEDIA"]},
        ],
        "rules": [
            "GEOSITE,private,DIRECT",
            "GEOIP,private,DIRECT,no-resolve",
            *[f"DOMAIN-SUFFIX,{d},GAMES" for d in GAME_DOWNLOAD_SUFFIXES],
            "GEOSITE,youtube,MEDIA",
            "GEOSITE,geolocation-!cn,PROXY",
            "GEOSITE,cn,DIRECT",
            "GEOIP,CN,DIRECT",
            "MATCH,PROXY",
        ],
    }
    header = (f"# veil profile for device '{device}' (TLS fingerprint: {fp}).\n"
              "# Generated on the server; local edits are lost on the next subscription update.\n")
    return header + yamlout.dump(config)


def share_links(state: dict, fingerprint: str = "ios") -> dict[str, str]:
    site = state["site_host"]
    r = state["reality"]
    links = {}
    q = urlencode({"encryption": "none", "flow": "xtls-rprx-vision", "security": "reality",
                   "sni": site, "fp": fingerprint, "pbk": r["public_key"],
                   "sid": r["short_ids"][0], "type": "tcp", "headerType": "none"})
    links["REALITY"] = f"vless://{r['uuid']}@{site}:443?{q}#veil-REALITY"
    if hy2_ready(state):
        h = state["hy2"]
        params = {"sni": site, "alpn": "h3", "insecure": "0", "mport": h["hop"]}
        if state["profile"]["hy2_obfs"]:
            params.update({"obfs": "salamander", "obfs-password": h["obfs_password"]})
        links["HY2"] = (f"hysteria2://{quote(h['password'], safe='')}@{site}:443/"
                        f"?{urlencode(params)}#veil-HY2")
    c = state["cdn"]
    if c["enabled"]:
        q = urlencode({"encryption": "none", "security": "tls", "sni": c["host"],
                       "fp": fingerprint, "type": "ws", "host": c["host"], "path": c["path"]})
        links["CDN"] = f"vless://{c['uuid']}@{c['host']}:443?{q}#veil-CDN"
    return links


def shadowrocket_subscription(state: dict) -> str:
    devices = state["profile"]["devices"]
    fp = next((d["fingerprint"] for d in devices.values() if d.get("client") == "shadowrocket"),
              "ios")
    body = "\n".join(share_links(state, fp).values()) + "\n"
    return base64.b64encode(body.encode()).decode() + "\n"


def subscription_urls(state: dict) -> dict[str, str]:
    # Through Cloudflare when available, so updates still arrive if the
    # server's IP is blocked. The site host serves the same files as well.
    host = state["cdn"]["host"] if state["cdn"]["enabled"] else state["site_host"]
    base = f"https://{host}/{state['sub_token']}"
    urls = {dev: f"{base}/mihomo-{dev}.yaml" for dev in state["profile"]["devices"]}
    urls["shadowrocket"] = f"{base}/shadowrocket.txt"
    return urls


def import_links(state: dict) -> dict[str, str]:
    """One-tap import links for devices using FlClash: opening one (or scanning
    its QR code with the phone camera) adds the subscription in the app."""
    urls = subscription_urls(state)
    return {dev: f"flclash://install-config?url={quote(urls[dev], safe='')}"
            for dev, d in state["profile"]["devices"].items() if d.get("client") == "flclash"}
