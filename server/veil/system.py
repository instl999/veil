"""Applying configs to the running system, certificates, health and maintenance."""
from __future__ import annotations

import json
import os
import shutil
import socket
import ssl
import subprocess
import tarfile
import time
from pathlib import Path

from . import REPO, __version__, net, render_client, render_server
from .core import P, PREFIX, VeilError, expire_retired, rotate, save_state, write_file

SINGBOX_UNIT = "veil-singbox.service"
NFT_UNIT = "veil-nft.service"
PULL_CA_SRC = Path(__file__).with_name("cloudflare-origin-pull-ca.pem")
# Debian's own apt-daily jobs can hold the package lock when maintenance runs;
# without a timeout apt-get gives up at once.
APT_WAIT = ("-o", "DPkg::Lock::Timeout=900")


def run(cmd: list[str], check: bool = True, capture: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=check, capture_output=capture, text=True)


def log(msg: str) -> None:
    print(f"[veil] {msg}", flush=True)


# ---------------------------------------------------------------- certificates

def find_caddy_cert(host: str) -> tuple[Path, Path] | None:
    """Newest certificate Caddy holds for `host`, whatever ACME issuer it used."""
    if not P.CADDY_CERTS.exists():
        return None
    found = sorted(P.CADDY_CERTS.glob(f"*/{host}/{host}.crt"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    for crt in found:
        key = crt.with_suffix(".key")
        if key.exists():
            return crt, key
    return None


def sync_cert(state: dict) -> bool:
    """Copy Caddy's certificate for the site host where sing-box can read it.
    sing-box reloads certificate files automatically when they change."""
    pair = find_caddy_cert(state["site_host"])
    if not pair:
        return False
    crt, key = pair
    new_crt, new_key = crt.read_bytes(), key.read_bytes()
    if (P.SITE_CRT.exists() and P.SITE_CRT.read_bytes() == new_crt
            and P.SITE_KEY.exists() and P.SITE_KEY.read_bytes() == new_key):
        return False
    write_file(P.SITE_KEY, new_key, mode=0o640, owner="root", group="veil")
    write_file(P.SITE_CRT, new_crt, mode=0o640, owner="root", group="veil")
    log("site certificate updated")
    return True


def cert_days_left(path: Path) -> float | None:
    if not path.exists():
        return None
    out = run(["openssl", "x509", "-enddate", "-noout", "-in", str(path)], check=False).stdout
    if "notAfter=" not in out:
        return None
    end = ssl.cert_time_to_seconds(out.strip().split("=", 1)[1])
    return (end - time.time()) / 86400


def check_origin_cert(crt: Path, key: Path, host: str) -> list[str]:
    """Problems with a Cloudflare origin certificate/key pair for `host` (empty = fine)."""
    ssl_ = lambda *args: run(["openssl", *args], check=False)
    if ssl_("x509", "-noout", "-in", str(crt)).returncode:
        return ["not a valid PEM certificate"]
    if ssl_("pkey", "-noout", "-in", str(key)).returncode:
        return ["not a valid PEM private key"]
    pub_crt = ssl_("x509", "-noout", "-pubkey", "-in", str(crt)).stdout
    pub_key = ssl_("pkey", "-pubout", "-in", str(key)).stdout
    if pub_crt.strip() != pub_key.strip():
        return ["the private key does not belong to this certificate"]
    sans = ssl_("x509", "-noout", "-ext", "subjectAltName", "-in", str(crt)).stdout
    names = {n.strip()[4:] for n in sans.replace("\n", ",").split(",") if n.strip().startswith("DNS:")}
    parent = host.split(".", 1)[1] if host.count(".") > 1 else None
    if host not in names and not (parent and f"*.{parent}" in names):
        return [f"the certificate does not cover {host} (it lists {', '.join(sorted(names))})"]
    return []


# ---------------------------------------------------------------- Authenticated Origin Pulls

def origin_pull_seen(state: dict) -> bool | None:
    """Ask the CDN host, through Cloudflare, whether Cloudflare presented its
    origin-pull client certificate. None means the check itself failed."""
    c = state["cdn"]
    status, _, body, _ = net.fetch(f"https://{c['host']}/{state['sub_token']}-origin-pull",
                                   timeout=20)
    return bool(body[:512].strip()) if status == 200 else None


def origin_pull(state: dict) -> str | None:
    """Require Cloudflare's client certificate once Cloudflare sends it.
    Returns a problem string, or None when all is well."""
    c = state["cdn"]
    if not c["enabled"]:
        return None
    seen = origin_pull_seen(state)
    if c["origin_pull"]:
        if seen is not None:
            return None
        # Unreachable while the certificate is required. If Cloudflare switched
        # to a client certificate the bundled CA does not cover (or the switch
        # was turned off), requiring it is what breaks the route: stop requiring
        # it while that keeps the route alive.
        c["origin_pull"] = False
        save_state(state)
        apply(state)
        time.sleep(3)
        if origin_pull_seen(state) is not None:
            return ("The CDN route failed while Cloudflare's client certificate was required, "
                    "so veil stopped requiring it. Check Authenticated Origin Pulls is on "
                    "(SSL/TLS > Origin Server) and update veil (`veil update`), which carries "
                    "Cloudflare's current certificate authority.")
        c["origin_pull"] = True  # not the cause; keep the protection
        save_state(state)
        apply(state)
        return f"CDN host {c['host']} is not reachable through Cloudflare"
    if seen is None:
        return (f"could not reach CDN host {c['host']} through Cloudflare to check "
                "Authenticated Origin Pulls")
    if not seen:
        return None  # dashboard switch still off; reported by health()
    c["origin_pull"] = True
    save_state(state)
    apply(state)
    time.sleep(3)
    if origin_pull_seen(state):
        log("Authenticated Origin Pulls is on: the CDN host now only answers Cloudflare")
        return None
    c["origin_pull"] = False  # something is off; never leave the CDN route broken
    save_state(state)
    apply(state)
    return "Cloudflare sent its origin-pull certificate, but requiring it broke the CDN route; reverted"


def set_cdn_host(state: dict, host: str, crt: Path | None, key: Path | None) -> None:
    """Move the CDN route to another (ideally unrelated) domain."""
    state["cdn"].update({"enabled": True, "host": host, "origin_pull": False})
    if crt and key:
        problems = check_origin_cert(crt, key, host)
        if problems:
            raise VeilError("origin certificate: " + "; ".join(problems))
        write_file(P.CDN_KEY, key.read_text(), mode=0o640, owner="root", group="caddy")
        write_file(P.CDN_CRT, crt.read_text(), mode=0o644, owner="root", group="caddy")
    else:
        # The old certificate is for the old name; Caddy falls back to a
        # self-signed one, which needs SSL/TLS mode "Full" in Cloudflare.
        P.CDN_CRT.unlink(missing_ok=True)
        P.CDN_KEY.unlink(missing_ok=True)
    save_state(state)
    apply(state)


# ---------------------------------------------------------------- render + apply

def render_all(state: dict) -> dict[Path, tuple[str, int, str | None, str | None]]:
    """Every generated file: path -> (content, mode, owner, group)."""
    files = {
        P.SINGBOX: (render_server.render_singbox(state), 0o640, "root", "veil"),
        P.CADDYFILE: (render_server.render_caddyfile(state, P.CDN_CRT.exists()), 0o644,
                      "root", "root"),
        P.NFT: (render_server.render_nft(state), 0o644, "root", "root"),
    }
    for dev in state["profile"]["devices"]:
        files[P.SUB / f"mihomo-{dev}.yaml"] = (render_client.render_mihomo(state, dev), 0o640,
                                               "root", "caddy")
    files[P.SUB / "shadowrocket.txt"] = (render_client.shadowrocket_subscription(state), 0o640,
                                         "root", "caddy")
    if state["cdn"]["enabled"]:
        files[P.PULL_CA] = (PULL_CA_SRC.read_text(encoding="utf-8"), 0o644, "root", "root")
    return files


def _validate(path: Path, tmp: Path) -> None:
    if path == P.SINGBOX:
        cmd = ["sing-box", "check", "-c", str(tmp)]
    elif path == P.CADDYFILE:
        cmd = ["caddy", "validate", "--adapter", "caddyfile", "--config", str(tmp)]
    elif path == P.NFT:
        cmd = ["nft", "-c", "-f", str(tmp)]
    else:
        return
    res = run(cmd, check=False)
    if res.returncode != 0:
        raise VeilError(f"generated {path.name} failed validation:\n{res.stdout}{res.stderr}")


def write_configs(state: dict, validate: bool = True) -> set[Path]:
    """Validate everything first, then swap files in. Returns the paths that changed."""
    files = render_all(state)
    changed = {p for p, (content, *_ ) in files.items()
               if not p.exists() or p.read_text(encoding="utf-8") != content}
    posix = os.name == "posix" and os.geteuid() == 0 and PREFIX == Path("/")
    # Files the configs refer to must exist before the configs are validated.
    for path in changed & {P.PULL_CA}:
        content, mode, owner, group = files[path]
        write_file(path, content, mode, owner if posix else None, group if posix else None)
    if validate:
        for path in changed & {P.SINGBOX, P.CADDYFILE, P.NFT}:
            tmp = path.with_name(f".{path.name}.check")
            write_file(tmp, files[path][0], mode=0o600)
            try:
                _validate(path, tmp)
            finally:
                tmp.unlink(missing_ok=True)
    for path in changed - {P.PULL_CA}:
        content, mode, owner, group = files[path]
        # Ownership only matters on the real system; a VEIL_PREFIX dry run has no caddy group.
        write_file(path, content, mode, owner if posix else None, group if posix else None)
    # Drop subscription files of devices that were removed from the profile.
    if P.SUB.exists():
        for stale in P.SUB.iterdir():
            if stale not in files:
                stale.unlink()
    return changed


def systemctl(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return run(["systemctl", *args], check=check)


def apply(state: dict, restart_all: bool = False) -> set[Path]:
    changed = write_configs(state)
    if restart_all or P.NFT in changed:
        systemctl("restart", NFT_UNIT)
    if restart_all or P.CADDYFILE in changed:
        # A reload goes through the admin endpoint named in the new config; when
        # that endpoint itself changed, only a restart picks the config up.
        if systemctl("reload-or-restart", "caddy", check=False).returncode:
            systemctl("restart", "caddy")
    if restart_all or P.SINGBOX in changed:
        systemctl("restart", SINGBOX_UNIT)
    return changed


def first_run(state: dict, wait: int = 180) -> None:
    """Bring a fresh install up: Caddy first (it needs to obtain the certificate),
    then sing-box; re-render once the certificate exists so Hysteria2 is enabled."""
    write_configs(state)
    systemctl("enable", "--now", NFT_UNIT)
    systemctl("enable", "caddy")
    systemctl("restart", "caddy")
    systemctl("enable", SINGBOX_UNIT)
    systemctl("restart", SINGBOX_UNIT)
    log(f"waiting up to {wait}s for Caddy to obtain the certificate for {state['site_host']} ...")
    deadline = time.time() + wait
    while time.time() < deadline:
        if sync_cert(state) or P.SITE_CRT.exists():
            break
        time.sleep(5)
    else:
        log("certificate not issued yet - check DNS (site host must be 'DNS only') and that "
            "TCP 80 is open. veil-maint retries daily, or run `veil sync-cert && veil apply`.")
        return
    apply(state)


# ---------------------------------------------------------------- health

def probe_site(host: str, port: int = 443, timeout: float = 8) -> str | None:
    """TLS handshake through REALITY's fallback; returns an error string or None."""
    ctx = ssl.create_default_context()
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout) as raw:
            with ctx.wrap_socket(raw, server_hostname=host) as tls:
                tls.sendall(f"HEAD / HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n".encode())
                first = tls.recv(64).decode(errors="replace")
                if not first.startswith("HTTP/"):
                    return f"unexpected reply {first!r}"
    except (OSError, ssl.SSLError) as exc:
        return str(exc)
    return None


def health(state: dict) -> dict:
    report = {"time": int(time.time()), "problems": [],
              "open_ports": "TCP 80, TCP 443, UDP 443"
                            + (f", UDP {state['hy2']['hop']}" if state["hy2"]["enabled"] else "")}
    for unit in (SINGBOX_UNIT, "caddy", NFT_UNIT):
        active = systemctl("is-active", unit, check=False).stdout.strip()
        report[unit] = active
        if active != "active":
            report["problems"].append(f"{unit} is {active}")
    err = probe_site(state["site_host"])
    report["site_probe"] = err or "ok"
    if err:
        report["problems"].append(f"TLS probe of {state['site_host']} via :443 failed: {err}")
    days = cert_days_left(P.SITE_CRT)
    report["site_cert_days"] = None if days is None else round(days, 1)
    if days is None and state["hy2"]["enabled"]:
        report["problems"].append("no site certificate yet (Hysteria2 disabled until issued)")
    elif days is not None and days < 14:
        report["problems"].append(f"site certificate expires in {days:.0f} days")
    if state["cdn"]["enabled"]:
        if state["cdn"]["origin_pull"]:
            report["cdn_origin_pull"] = "on"
        else:
            report["cdn_origin_pull"] = (
                "off - turn on Authenticated Origin Pulls in Cloudflare (SSL/TLS > Origin Server); "
                "veil enables it on its side automatically")
    if state["cdn"]["enabled"] and P.CDN_CRT.exists():
        cdn_days = cert_days_left(P.CDN_CRT)
        report["cdn_cert_days"] = None if cdn_days is None else round(cdn_days, 1)
        if cdn_days is not None and cdn_days < 30:
            report["problems"].append(f"Cloudflare origin certificate expires in {cdn_days:.0f} days")
    report["alerts"] = ("on" if state["maint"]["notify_url"] else
                        "off - problems found by the nightly check reach nobody; set a "
                        "notification URL (veil > Settings, or: veil set notify_url URL)")
    try:
        report["tcp_congestion"] = Path("/proc/sys/net/ipv4/tcp_congestion_control").read_text().strip()
    except OSError:
        report["tcp_congestion"] = "unknown"
    report["versions"] = {
        "sing-box": run(["sing-box", "version"], check=False).stdout.split("\n")[0],
        "caddy": run(["caddy", "version"], check=False).stdout.strip(),
    }
    return report


def notify(state: dict, message: str, url: str | None = None) -> bool:
    """Send a message to the configured alert URL: an ntfy topic
    (https://ntfy.sh/<topic>, or a self-hosted ntfy) or a Bark device URL
    (https://api.day.app/<key>, an iOS push app that works inside China).
    Returns True when the service accepted it."""
    url = url if url is not None else state["maint"].get("notify_url")
    if not url:
        return False
    title = f"veil @ {state['site_host']}"
    if is_bark(url):
        body = json.dumps({"title": title, "body": message, "group": "veil"}).encode()
        status, _, _, err = net.fetch(url.rstrip("/"), data=body, timeout=15,
                                      headers={"Content-Type": "application/json"})
    else:
        status, _, _, err = net.fetch(url, data=message.encode(), timeout=15,
                                      headers={"Title": title, "Tags": "shield"})
    if status is not None and 200 <= status < 300:
        return True
    log(f"notification failed: {err or f'HTTP {status}'}")
    return False


def is_bark(url: str) -> bool:
    return "api.day.app" in url


# ---------------------------------------------------------------- backups

# Everything needed to rebuild the server: keys and settings, the Cloudflare
# origin certificate and the cover site (which may have been edited).
BACKUP_ITEMS = (P.STATE, P.CDN_CRT, P.CDN_KEY, P.WWW)
AUTO_BACKUPS = P.LIB / "backups"
AUTO_BACKUP_KEEP = 14


def make_backup(out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(f".{out.name}.tmp")
    with open(tmp, "wb") as raw:
        if os.name == "posix":
            os.chmod(tmp, 0o600)  # private keys inside: never readable by others
        with tarfile.open(fileobj=raw, mode="w:gz") as tar:
            for item in BACKUP_ITEMS:
                if item.exists():
                    tar.add(item, arcname=item.relative_to(PREFIX).as_posix())
    os.replace(tmp, out)
    return out


def list_backups(directory: Path = AUTO_BACKUPS) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(directory.glob("veil-*.tar.gz"))


def auto_backup(now: float | None = None) -> Path:
    """Nightly snapshot kept on the server (root-only), for undoing a bad change.
    It does not replace a copy on your own computer: see `veil backup`."""
    AUTO_BACKUPS.mkdir(mode=0o700, parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d", time.gmtime(now))
    path = make_backup(AUTO_BACKUPS / f"veil-{stamp}.tar.gz")
    for old in list_backups()[:-AUTO_BACKUP_KEEP]:
        old.unlink()
    return path


# ---------------------------------------------------------------- veil releases

def _vtuple(version: str) -> tuple[int, ...]:
    parts = []
    for piece in version.lstrip("v").split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits or 0))
    return tuple(parts)


def latest_release() -> str | None:
    """Newest published veil version on GitHub, or None if unknown."""
    status, _, body, _ = net.fetch(f"https://api.github.com/repos/{REPO}/releases/latest",
                                   timeout=15, headers={"Accept": "application/vnd.github+json"})
    if status != 200:
        return None
    try:
        return json.loads(body).get("tag_name", "").lstrip("v") or None
    except ValueError:
        return None


def update_available() -> str | None:
    latest = latest_release()
    return latest if latest and _vtuple(latest) > _vtuple(__version__) else None


# ---------------------------------------------------------------- upgrades

def _pkg_version(pkg: str) -> str:
    return run(["dpkg-query", "-W", "-f=${Version}", pkg], check=False).stdout.strip()


def _candidate(pkg: str) -> str:
    out = run(["apt-cache", "policy", pkg], check=False).stdout
    for line in out.splitlines():
        if line.strip().startswith("Candidate:"):
            return line.split(":", 1)[1].strip()
    return ""


def safe_upgrade(state: dict, pkg: str, binary: str, unit: str) -> str | None:
    """Upgrade one package; on a failed config check or service start, put the
    previous binary back and hold the package. Returns a problem string or None."""
    installed, candidate = _pkg_version(pkg), _candidate(pkg)
    if not candidate or candidate in ("(none)", installed):
        return None
    held = run(["apt-mark", "showhold"], check=False).stdout.split()
    if pkg in held:
        return None
    path = shutil.which(binary)
    if not path:
        return f"{binary} not found"
    backup = P.LIB / f"{binary}.prev"
    shutil.copy2(path, backup)
    log(f"upgrading {pkg} {installed} -> {candidate}")
    res = run(["apt-get", *APT_WAIT, "install", "-y", "--only-upgrade", pkg], check=False)
    if res.returncode != 0 and _pkg_version(pkg) == installed:
        # Nothing was installed (apt busy, mirror down): no reason to hold the
        # package, just try again tomorrow.
        log(f"could not install {pkg} {candidate}: {res.stderr.strip()[-300:]}")
        return f"{pkg} {candidate} could not be installed; will retry at the next maintenance"
    ok = res.returncode == 0
    if ok:
        try:
            write_configs(state)  # validates with the new binary
            systemctl("restart", unit)
            time.sleep(5)
            ok = systemctl("is-active", unit, check=False).stdout.strip() == "active"
        except VeilError as exc:
            log(str(exc))
            ok = False
    if ok:
        return None
    shutil.copy2(backup, path)
    run(["apt-mark", "hold", pkg], check=False)
    systemctl("restart", unit, check=False)
    return (f"{pkg} {candidate} failed checks; rolled back to {installed} and held the package. "
            f"After fixing, run: apt-mark unhold {pkg}")


# ---------------------------------------------------------------- daily maintenance

def maint(state: dict) -> dict:
    problems = []
    dirty = False

    if sync_cert(state):
        dirty = True
    if expire_retired(state):
        dirty = True
    m = state["maint"]
    # Count from installation until the first rotation, not from 1970.
    last = m["last_rotate"] or state.get("created", time.time())
    if m["rotate_days"] and time.time() - last > m["rotate_days"] * 86400:
        rotate(state, ["creds", "short_id"])
        log("rotated credentials (old ones stay valid for the grace period)")
        notify(state, "Proxy credentials were rotated. Devices pick up the new ones on their next "
                      f"subscription update; the old ones stop working in {m['grace_days']} days. "
                      "Shadowrocket: open the app and update the subscription.")
        dirty = True
    if dirty:
        save_state(state)
        try:
            apply(state)
        except VeilError as exc:
            problems.append(str(exc))

    if m["auto_upgrade"]:
        run(["apt-get", *APT_WAIT, "update", "-q"], check=False)
        for pkg, binary, unit in (("sing-box", "sing-box", SINGBOX_UNIT),
                                  ("caddy", "caddy", "caddy")):
            err = safe_upgrade(state, pkg, binary, unit)
            if err:
                problems.append(err)

    try:
        err = origin_pull(state)
    except VeilError as exc:
        err = str(exc)
    if err:
        problems.append(err)

    try:
        auto_backup()
    except OSError as exc:
        problems.append(f"automatic backup failed: {exc}")

    # veil itself is never upgraded unattended (that would let anyone who takes
    # over the GitHub repository run code on this server); you are told instead.
    newer = update_available()
    if newer and m.get("notified_version") != newer:
        if notify(state, f"veil {newer} is available (installed: {__version__}). "
                         "Log in and run: veil update"):
            m["notified_version"] = newer
            save_state(state)

    run(["journalctl", "--vacuum-time=14d"], check=False)

    report = health(state)
    report["problems"] = problems + report["problems"]
    write_file(P.STATUS, json.dumps(report, indent=2) + "\n")
    if report["problems"]:
        notify(state, "\n".join(report["problems"]))
    return report
