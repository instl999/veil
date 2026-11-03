"""Paths, persistent state, secret generation and credential rotation.

All server state lives in one JSON file (/etc/veil/state.json, root-only).
Every other file veil writes is rendered from it, so a backup of that file
plus the optional Cloudflare origin certificate is enough to rebuild a server.
"""
from __future__ import annotations

import base64
import copy
import json
import os
import re
import secrets
import shutil
import subprocess
import time
import uuid
from pathlib import Path

# VEIL_PREFIX lets the renderers run against a scratch directory (tests, dry runs).
PREFIX = Path(os.environ.get("VEIL_PREFIX", "/"))


def _p(path: str) -> Path:
    return PREFIX / path.lstrip("/")


class P:
    ETC = _p("/etc/veil")
    STATE = ETC / "state.json"
    SINGBOX = ETC / "sing-box.json"
    NFT = ETC / "veil.nft"
    TLS = ETC / "tls"
    SITE_CRT = TLS / "site.crt"
    SITE_KEY = TLS / "site.key"
    CADDYFILE = _p("/etc/caddy/Caddyfile")
    CDN_CRT = _p("/etc/caddy/veil-cdn.crt")
    CDN_KEY = _p("/etc/caddy/veil-cdn.key")
    # Cloudflare's client CA for Authenticated Origin Pulls (bundled, valid to 2029).
    PULL_CA = _p("/etc/caddy/cloudflare-origin-pull-ca.pem")
    LIB = _p("/var/lib/veil")
    WWW = LIB / "www"
    SUB = LIB / "sub"
    STATUS = LIB / "status.json"
    CADDY_CERTS = _p("/var/lib/caddy/.local/share/caddy/certificates")
    OPT = _p("/opt/veil")
    DECOY_SRC = OPT / "decoy"
    # How veil was installed: "git <repo path>" or "release" (read by `veil update`).
    SOURCE = OPT / "SOURCE"
    INSTALLER = OPT / "veil-install.sh"
    REBOOT_REQUIRED = _p("/var/run/reboot-required")


SCHEMA = 1
ROUTES = ("REALITY", "HY2", "CDN")
# uTLS presets understood by mihomo's client-fingerprint option.
FINGERPRINTS = ("chrome", "firefox", "safari", "ios", "android", "edge", "360", "qq", "random")
# Cloudflare reserves /cdn-cgi, so it is not in this list.
PATH_WORDS = ("assets", "static", "media", "api", "res", "files", "content", "img", "js", "v2")

DEFAULT_PROFILE = {
    "schema": "veil-profile/1",
    "devices": {
        "mac": {"fingerprint": "safari", "client": "clash-verge"},
        "windows": {"fingerprint": "chrome", "client": "clash-verge"},
        "iphone": {"fingerprint": "ios", "client": "shadowrocket"},
        "router": {"fingerprint": "chrome", "client": "openclash"},
    },
    # Fallback order per traffic class; the first reachable route wins.
    "routes": {
        "browse": ["REALITY", "CDN", "HY2"],
        "media": ["HY2", "REALITY", "CDN"],
    },
    # Seconds between Hysteria2 port hops ("min-max" picks randomly each time).
    "hop_interval": "20-40",
    # Seconds between client health checks of the fallback groups (lazy).
    "healthcheck_interval": 900,
    # Salamander turns HY2 into opaque UDP instead of HTTP/3-looking QUIC.
    "hy2_obfs": False,
}

DEFAULT_MAINT = {
    "auto_upgrade": True,
    "rotate_days": 30,
    "grace_days": 7,
    "notify_url": "",
    "last_rotate": 0,
}


class VeilError(Exception):
    pass


# ---------------------------------------------------------------- secrets

def new_uuid() -> str:
    return str(uuid.uuid4())


def new_short_id() -> str:
    return secrets.token_hex(8)


def new_password() -> str:
    return secrets.token_urlsafe(24)


def new_token() -> str:
    return secrets.token_hex(16)


def new_path() -> str:
    tail = "".join(secrets.choice("abcdefghijklmnopqrstuvwxyz0123456789") for _ in range(10))
    return f"/{secrets.choice(PATH_WORDS)}/{tail}"


def new_hop_range() -> str:
    start = 20000 + secrets.randbelow(20000)
    return f"{start}-{start + 4000 + secrets.randbelow(8000)}"


def new_loopback_port() -> int:
    return 20000 + secrets.randbelow(40000)


def reality_keypair() -> tuple[str, str]:
    """Return (private, public) X25519 keys in REALITY's base64url format."""
    fake = os.environ.get("VEIL_FAKE_KEYPAIR")
    if fake:  # tests only
        priv, pub = fake.split(":")
        return priv, pub
    try:
        from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
        from cryptography.hazmat.primitives import serialization as s

        key = X25519PrivateKey.generate()
        raw_priv = key.private_bytes(s.Encoding.Raw, s.PrivateFormat.Raw, s.NoEncryption())
        raw_pub = key.public_key().public_bytes(s.Encoding.Raw, s.PublicFormat.Raw)
        enc = lambda b: base64.urlsafe_b64encode(b).decode().rstrip("=")
        return enc(raw_priv), enc(raw_pub)
    except ImportError:
        pass
    out = subprocess.run(["sing-box", "generate", "reality-keypair"],
                         check=True, capture_output=True, text=True).stdout
    fields = dict(line.split(": ", 1) for line in out.strip().splitlines() if ": " in line)
    return fields["PrivateKey"].strip(), fields["PublicKey"].strip()


# ---------------------------------------------------------------- state

def new_state(site_host: str, cdn_host: str | None, email: str,
              hy2: bool = True) -> dict:
    priv, pub = reality_keypair()
    return {
        "schema": SCHEMA,
        "created": int(time.time()),
        "site_host": site_host,
        "email": email,
        "sub_token": new_token(),
        "reality": {"uuid": new_uuid(), "private_key": priv, "public_key": pub,
                    "short_ids": [new_short_id()]},
        "hy2": {"enabled": hy2, "password": new_password(), "hop": new_hop_range(),
                "obfs_password": new_password()},
        "cdn": {"enabled": bool(cdn_host), "host": cdn_host or "", "uuid": new_uuid(),
                "path": new_path(), "port": new_loopback_port(),
                # Set once Cloudflare is seen presenting its origin-pull certificate.
                "origin_pull": False},
        "retired": [],
        "profile": copy.deepcopy(DEFAULT_PROFILE),
        "maint": copy.deepcopy(DEFAULT_MAINT),
    }


def load_state() -> dict:
    if not P.STATE.exists():
        raise VeilError(f"{P.STATE} not found; run the installer or `veil init` first")
    state = json.loads(P.STATE.read_text(encoding="utf-8"))
    if state.get("schema") != SCHEMA:
        raise VeilError(f"unsupported state schema {state.get('schema')}")
    state.setdefault("maint", {})
    for k, v in DEFAULT_MAINT.items():
        state["maint"].setdefault(k, v)
    state["cdn"].setdefault("origin_pull", False)
    return state


def save_state(state: dict) -> None:
    write_file(P.STATE, json.dumps(state, indent=2) + "\n", mode=0o600)


def write_file(path: Path, content: str | bytes, mode: int = 0o644,
               owner: str | None = None, group: str | None = None) -> None:
    """Atomic write with permissions applied before the file appears."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    data = content.encode() if isinstance(content, str) else content
    with open(tmp, "wb") as fh:
        fh.write(data)
    if os.name == "posix":
        os.chmod(tmp, mode)
        if owner or group:
            shutil.chown(tmp, user=owner, group=group)
    os.replace(tmp, path)


# ---------------------------------------------------------------- retired credentials

def active_retired(state: dict, kind: str, now: float | None = None) -> list[str]:
    now = time.time() if now is None else now
    return [r["value"] for r in state["retired"] if r["kind"] == kind and r["expires"] > now]


def expire_retired(state: dict, now: float | None = None) -> int:
    now = time.time() if now is None else now
    before = len(state["retired"])
    state["retired"] = [r for r in state["retired"] if r["expires"] > now]
    # Short IDs live in reality.short_ids; drop the ones whose grace ended.
    keep = {state["reality"]["short_ids"][0], *active_retired(state, "short_id", now)}
    state["reality"]["short_ids"] = [s for s in state["reality"]["short_ids"] if s in keep]
    return before - len(state["retired"])


ROTATABLE = ("creds", "path", "short_id", "hop")


def rotate(state: dict, what: list[str], grace_days: float | None = None) -> list[str]:
    """Replace secrets; old values stay valid for the grace period so clients can
    pick up the new subscription without an outage."""
    grace = state["maint"]["grace_days"] if grace_days is None else grace_days
    expires = int(time.time() + grace * 86400)
    retire = lambda kind, value: state["retired"].append(
        {"kind": kind, "value": value, "expires": expires})
    done = []
    if "creds" in what:
        retire("reality_uuid", state["reality"]["uuid"])
        state["reality"]["uuid"] = new_uuid()
        retire("hy2_password", state["hy2"]["password"])
        state["hy2"]["password"] = new_password()
        retire("cdn_uuid", state["cdn"]["uuid"])
        state["cdn"]["uuid"] = new_uuid()
        done.append("creds")
    if "path" in what:
        retire("cdn_path", state["cdn"]["path"])
        state["cdn"]["path"] = new_path()
        done.append("path")
    if "short_id" in what:
        old = state["reality"]["short_ids"][0]
        retire("short_id", old)
        state["reality"]["short_ids"].insert(0, new_short_id())
        done.append("short_id")
    if "hop" in what:
        retire("hop", state["hy2"]["hop"])
        state["hy2"]["hop"] = new_hop_range()
        done.append("hop")
    state["maint"]["last_rotate"] = int(time.time())
    return done


# ---------------------------------------------------------------- profile

_INTERVAL = re.compile(r"^\d{1,4}(-\d{1,4})?$")


def validate_profile(profile: dict) -> dict:
    """Merge a (possibly partial) profile onto the defaults and validate it."""
    merged = copy.deepcopy(DEFAULT_PROFILE)
    for key in ("routes", "hop_interval", "healthcheck_interval", "hy2_obfs"):
        if key in profile:
            merged[key] = profile[key]
    if "devices" in profile:
        merged["devices"] = profile["devices"]

    if not merged["devices"]:
        raise VeilError("profile must define at least one device")
    for name, dev in merged["devices"].items():
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,30}", name):
            raise VeilError(f"device name {name!r}: use lowercase letters, digits, '-'")
        if dev.get("fingerprint") not in FINGERPRINTS:
            raise VeilError(f"device {name}: fingerprint must be one of {', '.join(FINGERPRINTS)}")
        dev.setdefault("client", "clash-verge")
    for cls in ("browse", "media"):
        order = merged["routes"].get(cls)
        if not order or any(r not in ROUTES for r in order) or len(set(order)) != len(order):
            raise VeilError(f"routes.{cls} must be an ordered subset of {ROUTES}")
    if not _INTERVAL.match(str(merged["hop_interval"])):
        raise VeilError("hop_interval must look like '30' or '20-40'")
    hc = merged["healthcheck_interval"]
    if not isinstance(hc, int) or not 60 <= hc <= 86400:
        raise VeilError("healthcheck_interval must be an integer between 60 and 86400")
    if not isinstance(merged["hy2_obfs"], bool):
        raise VeilError("hy2_obfs must be true or false")
    merged["schema"] = DEFAULT_PROFILE["schema"]
    return merged
