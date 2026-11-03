"""`veil` command line."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

from . import REPO, __version__, doctor, net, render_client, system
from .core import (FINGERPRINTS, P, PREFIX, ROTATABLE, VeilError, load_state, new_state,
                   new_token, rotate, save_state, validate_profile, write_file)


def _seed_decoy(site_host: str) -> None:
    """Copy the bundled decoy site once; later edits to /var/lib/veil/www are kept."""
    if P.WWW.exists() and any(P.WWW.iterdir()):
        return
    if not P.DECOY_SRC.exists():
        raise VeilError(f"decoy template missing at {P.DECOY_SRC}")
    shutil.copytree(P.DECOY_SRC, P.WWW, dirs_exist_ok=True)
    for page in P.WWW.rglob("*.html"):
        text = page.read_text(encoding="utf-8")
        page.write_text(text.replace("{{HOST}}", site_host)
                        .replace("{{YEAR}}", time.strftime("%Y")), encoding="utf-8")


def cmd_init(a) -> int:
    if P.STATE.exists() and not a.force:
        raise VeilError(f"{P.STATE} already exists (use --force to replace ALL keys)")
    state = new_state(a.site_host, a.cdn_host, a.email, hy2=not a.no_hy2)
    save_state(state)
    _seed_decoy(a.site_host)
    print(f"initialised {P.STATE}")
    return 0


def cmd_apply(a) -> int:
    state = load_state()
    if a.no_system:
        changed = system.write_configs(state, validate=False)
    elif a.first_run:
        system.first_run(state)
        changed = set()
    else:
        system.sync_cert(state)
        changed = system.apply(state, restart_all=a.restart)
    for path in sorted(changed):
        print(f"updated {path}")
    return 0


def _qr(text: str) -> None:
    if shutil.which("qrencode"):
        subprocess.run(["qrencode", "-t", "ANSIUTF8", "-m", "1", text], check=False)
    else:
        print("(install qrencode to show QR codes)")


def cmd_links(a) -> int:
    state = load_state()
    urls = render_client.subscription_urls(state)
    imports = render_client.import_links(state)
    if a.json:
        print(json.dumps({"site_host": state["site_host"], "subscriptions": urls,
                          "imports": imports, "links": render_client.share_links(state)}))
        return 0
    print("Subscription URLs (keep these private) / 订阅链接（请勿外泄）:")
    for name, url in urls.items():
        print(f"  {name:<13} {url}")
    print("\n  Clash Verge Rev: Profiles > New > Remote, paste the URL of that device.")
    print("  Clash Verge Rev：订阅 > 新建 > 远程，粘贴对应设备的链接。")
    print("  FlClash: Profiles > + > URL, paste the URL (or scan the device's QR code).")
    print("  FlClash：配置 > + > URL，粘贴链接（或扫描该设备的二维码）。")
    print("  OpenClash: use 'router'. Shadowrocket: use 'shadowrocket' (or scan its QR code).")
    if imports:
        print("\nFlClash one-tap import / FlClash 一键导入:")
        for name, link in imports.items():
            print(f"  {name:<13} {link}")
    print("\nShare links:")
    for name, link in render_client.share_links(state).items():
        print(f"  {name:<8} {link}")
    if a.qr:
        target = a.qr
        # A FlClash device's QR opens the app and imports the profile in one step.
        text = (imports.get(target) or urls.get(target)
                or render_client.share_links(state).get(target.upper()))
        if not text:
            raise VeilError(f"unknown QR target {target!r}; choose from "
                            f"{', '.join([*urls, *render_client.share_links(state)])}")
        print(f"\nQR for {target}:")
        _qr(text)
    return 0


def cmd_status(a) -> int:
    state = load_state()
    err = system.origin_pull(state)
    report = system.health(state)
    if err:
        report["problems"].insert(0, err)
    print(json.dumps(report, indent=2))
    return 1 if report["problems"] else 0


def cmd_rotate(a) -> int:
    state = load_state()
    what = list(ROTATABLE) if "all" in a.what else a.what
    done = rotate(state, what, a.grace)
    save_state(state)
    system.apply(state)
    print(f"rotated: {', '.join(done)}; old values valid for "
          f"{state['maint']['grace_days'] if a.grace is None else a.grace} days. "
          "Clients pick up the change on their next subscription update.")
    return 0


def cmd_reset_sub(a) -> int:
    """New subscription token: every old subscription URL stops working at once."""
    state = load_state()
    state["sub_token"] = new_token()
    save_state(state)
    system.apply(state)
    print("Subscription URLs reset. Re-import the new URLs on every device:\n")
    for name, url in render_client.subscription_urls(state).items():
        print(f"  {name:<13} {url}")
    return 0


def cmd_maint(a) -> int:
    report = system.maint(load_state())
    print(json.dumps(report, indent=2))
    return 1 if report["problems"] else 0


def cmd_sync_cert(a) -> int:
    print("updated" if system.sync_cert(load_state()) else "unchanged")
    return 0


def cmd_profile(a) -> int:
    state = load_state()
    if a.action == "show":
        print(json.dumps(state["profile"], indent=2))
        return 0
    text = sys.stdin.read() if a.file == "-" else Path(a.file).read_text(encoding="utf-8")
    try:
        incoming = json.loads(text)
    except json.JSONDecodeError as exc:
        raise VeilError(f"profile is not valid JSON: {exc}") from None
    state["profile"] = validate_profile(incoming)
    save_state(state)
    system.apply(state)
    print("profile applied; clients pick it up on their next subscription update")
    return 0


def cmd_device(a) -> int:
    state = load_state()
    devices = state["profile"]["devices"]
    if a.action == "list":
        for name, dev in devices.items():
            print(f"{name:<12} fingerprint={dev['fingerprint']:<8} client={dev.get('client', '')}")
        return 0
    if a.action == "add":
        devices[a.name] = {"fingerprint": a.fingerprint, "client": a.client}
    elif a.action == "rm":
        if a.name not in devices:
            raise VeilError(f"no device {a.name!r}")
        del devices[a.name]
    state["profile"] = validate_profile(state["profile"])
    save_state(state)
    system.apply(state)
    return cmd_device(argparse.Namespace(action="list"))


def cmd_set(a) -> int:
    state = load_state()
    m = state["maint"]
    if a.key in ("auto_upgrade",):
        m[a.key] = a.value.lower() in ("1", "true", "yes", "on")
    elif a.key in ("rotate_days", "grace_days"):
        m[a.key] = int(a.value)
    elif a.key == "notify_url":
        if a.value and not a.value.startswith("https://"):
            raise VeilError("notify_url must start with https:// (or be empty to turn alerts off)")
        m[a.key] = a.value
    save_state(state)
    print(f"{a.key} = {m[a.key]}")
    return 0


def cmd_cdn_cert(a) -> int:
    state = load_state()
    problems = system.check_origin_cert(Path(a.cert), Path(a.key), state["cdn"]["host"])
    if problems:
        raise VeilError("origin certificate: " + "; ".join(problems))
    crt, key = Path(a.cert).read_text(), Path(a.key).read_text()
    write_file(P.CDN_KEY, key, mode=0o640, owner="root", group="caddy")
    write_file(P.CDN_CRT, crt, mode=0o644, owner="root", group="caddy")
    if not a.no_apply:
        system.apply(state)
    print("Cloudflare origin certificate installed")
    return 0


def cmd_cdn_host(a) -> int:
    if bool(a.cert) != bool(a.key):
        raise VeilError("--cert and --key go together")
    state = load_state()
    system.set_cdn_host(state, a.host, Path(a.cert) if a.cert else None,
                        Path(a.key) if a.key else None)
    print(f"CDN route moved to {a.host}. Re-import the new subscription URLs on every device:")
    for name, url in render_client.subscription_urls(state).items():
        print(f"  {name:<13} {url}")
    return 0


def cmd_origin_pull(a) -> int:
    state = load_state()
    err = system.origin_pull(state)
    if err:
        print(err)
        return 1
    print("on: the CDN host only answers Cloudflare" if state["cdn"]["origin_pull"] else
          "off: turn on Authenticated Origin Pulls in Cloudflare (SSL/TLS > Origin Server), "
          "then run this again")
    return 0


def cmd_backup(a) -> int:
    if a.list:
        found = system.list_backups()
        print("Automatic backups (one per night, last 14 kept) / 自动备份（每晚一份，保留 14 份）:")
        for path in found:
            print(f"  {path}  {path.stat().st_size // 1024} KiB")
        if not found:
            print("  (none yet / 暂无)")
        return 0
    out = system.make_backup(Path(a.out or f"/root/veil-backup-{time.strftime('%Y%m%d-%H%M%S')}.tar.gz"))
    print(f"Backup written to {out} (contains private keys - store it safely)")
    print(f"备份已写入 {out}（包含私钥，请妥善保管）")
    ip = net.public_ipv4() or "SERVER_IP"
    print("\nCopy it to your computer: open PowerShell (Windows) or Terminal (Mac) there and run:")
    print("在你的电脑上打开 PowerShell（Windows）或终端（Mac），运行：")
    print(f"\n    scp root@{ip}:{out} .\n")
    return 0


def cmd_restore(a) -> int:
    allowed = {i.relative_to(PREFIX).as_posix() for i in system.BACKUP_ITEMS}
    with tarfile.open(a.file, "r:gz") as tar:
        members = [m for m in tar.getmembers()
                   if any(m.name == x or m.name.startswith(x + "/") for x in allowed)
                   and ".." not in m.name.split("/") and not m.issym() and not m.islnk()]
        tar.extractall(path=str(PREFIX), members=members)
    P.STATE.chmod(0o600)
    state = load_state()
    print(f"restored state for {state['site_host']}")
    return 0


def cmd_doctor(a) -> int:
    results = doctor.run(load_state(), a.only)
    print(doctor.render(results))
    return 1 if doctor.failed(results) else 0


LOG_UNITS = {"proxy": ["veil-singbox"], "web": ["caddy"], "maint": ["veil-maint"],
             "fail2ban": ["fail2ban"], "all": ["veil-singbox", "caddy", "veil-maint", "fail2ban"]}


def cmd_logs(a) -> int:
    cmd = ["journalctl", "--no-pager", "-n", str(a.lines), "-o", "short-iso"]
    for unit in LOG_UNITS[a.which]:
        cmd += ["-u", unit]
    if a.follow:
        cmd.append("-f")
    return subprocess.run(cmd, check=False).returncode


def cmd_alert_test(a) -> int:
    state = load_state()
    url = a.url or state["maint"]["notify_url"]
    if not url:
        raise VeilError("no alert URL set; see: veil set notify_url URL")
    if system.notify(state, "Test alert from veil: alerts work. / veil 测试提醒：提醒功能正常。", url):
        print("Sent. Check your phone. / 已发送，请查看手机。")
        return 0
    print("Not delivered - check the URL. / 发送失败，请检查地址。")
    return 1


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cmd_update(a) -> int:
    """Update veil itself. Keys, settings and subscription links are kept."""
    source = P.SOURCE.read_text().strip() if P.SOURCE.exists() else "release"
    latest = system.latest_release()
    print(f"installed / 当前: {__version__}    latest release / 最新发布: {latest or 'unknown / 未知'}")
    if a.check:
        return 0
    if source.startswith("git "):
        repo = Path(source[4:])
        print(f"Updating from the git checkout {repo} / 从 git 仓库更新")
        if subprocess.run(["git", "-C", str(repo), "pull", "--ff-only"], check=False).returncode:
            raise VeilError(f"git pull failed in {repo}; resolve it there, then run: "
                            f"bash {repo}/install.sh --update")
        installer = repo / "install.sh"
    else:
        if not latest and not a.force:
            raise VeilError(f"cannot reach GitHub ({REPO}); try again later")
        if latest and system._vtuple(latest) <= system._vtuple(__version__) and not a.force:
            print("Already up to date. / 已是最新版本。 (--force reinstalls / 强制重装)")
            return 0
        base = f"https://github.com/{REPO}/releases/latest/download"
        tmp = Path(tempfile.mkdtemp(prefix="veil-update-"))
        installer = tmp / "veil-install.sh"
        print(f"Downloading / 正在下载 {base}/veil-install.sh")
        net.download(f"{base}/veil-install.sh", installer)
        net.download(f"{base}/veil-install.sh.sha256", tmp / "sum")
        expected = (tmp / "sum").read_text().split()[0].lower()
        if _sha256(installer) != expected:
            raise VeilError("downloaded installer does not match its checksum; not running it")
        print("Checksum OK / 校验通过")
    os.execvp("bash", ["bash", str(installer), "--update"])
    return 0  # not reached


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="veil", description="Personal stealth proxy manager.")
    ap.add_argument("--version", action="version", version=f"veil {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="create keys and state (installer runs this)")
    s.add_argument("--site-host", required=True)
    s.add_argument("--cdn-host")
    s.add_argument("--email", required=True)
    s.add_argument("--no-hy2", action="store_true")
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_init)

    s = sub.add_parser("apply", help="render configs and restart what changed")
    s.add_argument("--restart", action="store_true", help="restart every service")
    s.add_argument("--first-run", action="store_true", help=argparse.SUPPRESS)
    s.add_argument("--no-system", action="store_true", help="only write files (dry run)")
    s.set_defaults(fn=cmd_apply)

    s = sub.add_parser("links", help="show subscription URLs and share links")
    s.add_argument("--qr", metavar="NAME", help="device name, 'shadowrocket' or a route name")
    s.add_argument("--json", action="store_true", help="machine-readable output")
    s.set_defaults(fn=cmd_links)

    s = sub.add_parser("status", help="health summary as JSON (for scripts)")
    s.set_defaults(fn=cmd_status)

    s = sub.add_parser("doctor", help="check everything and explain how to fix problems")
    s.add_argument("--only", nargs="+", choices=list(doctor.SECTIONS))
    s.set_defaults(fn=cmd_doctor)

    s = sub.add_parser("logs", help="recent log lines of the services")
    s.add_argument("which", nargs="?", default="all", choices=list(LOG_UNITS))
    s.add_argument("-n", "--lines", type=int, default=100)
    s.add_argument("-f", "--follow", action="store_true")
    s.set_defaults(fn=cmd_logs)

    s = sub.add_parser("alert-test", help="send a test alert to your phone")
    s.add_argument("url", nargs="?", help="try this URL instead of the saved one")
    s.set_defaults(fn=cmd_alert_test)

    s = sub.add_parser("update", help="update veil itself (keys and links are kept)")
    s.add_argument("--check", action="store_true", help="only show the versions")
    s.add_argument("--force", action="store_true", help="reinstall even if up to date")
    s.set_defaults(fn=cmd_update)

    s = sub.add_parser("rotate", help="replace secrets with a grace period")
    s.add_argument("what", nargs="+", choices=[*ROTATABLE, "all"])
    s.add_argument("--grace", type=float, help="days old values stay valid")
    s.set_defaults(fn=cmd_rotate)

    s = sub.add_parser("reset-sub", help="new subscription URLs (old ones stop working)")
    s.set_defaults(fn=cmd_reset_sub)

    s = sub.add_parser("maint", help="daily maintenance (run by veil-maint.timer)")
    s.set_defaults(fn=cmd_maint)

    s = sub.add_parser("sync-cert", help="copy Caddy's certificate for sing-box")
    s.set_defaults(fn=cmd_sync_cert)

    s = sub.add_parser("profile", help="show or apply a personalization profile")
    s.add_argument("action", choices=["show", "apply"])
    s.add_argument("file", nargs="?", help="profile.json, or - to read from stdin")
    s.set_defaults(fn=cmd_profile)

    s = sub.add_parser("device", help="manage per-device client profiles")
    s.add_argument("action", choices=["list", "add", "rm"])
    s.add_argument("name", nargs="?")
    s.add_argument("--fingerprint", default="chrome", choices=FINGERPRINTS)
    s.add_argument("--client", default="clash-verge",
                   help="clash-verge, flclash, openclash, shadowrocket, stash or other")
    s.set_defaults(fn=cmd_device)

    s = sub.add_parser("set", help="change a maintenance setting")
    s.add_argument("key", choices=["auto_upgrade", "rotate_days", "grace_days", "notify_url"])
    s.add_argument("value")
    s.set_defaults(fn=cmd_set)

    s = sub.add_parser("cdn-cert", help="install a Cloudflare origin certificate")
    s.add_argument("--cert", required=True)
    s.add_argument("--key", required=True)
    s.add_argument("--no-apply", action="store_true")
    s.set_defaults(fn=cmd_cdn_cert)

    s = sub.add_parser("cdn-host", help="move the CDN route to another domain")
    s.add_argument("host")
    s.add_argument("--cert", help="Cloudflare origin certificate for the new host")
    s.add_argument("--key", help="its private key")
    s.set_defaults(fn=cmd_cdn_host)

    s = sub.add_parser("origin-pull", help="check and enforce Cloudflare Authenticated Origin Pulls")
    s.set_defaults(fn=cmd_origin_pull)

    s = sub.add_parser("backup", help="archive keys, certificates and site (to copy off the server)")
    s.add_argument("--out")
    s.add_argument("--list", action="store_true", help="list the automatic nightly backups")
    s.set_defaults(fn=cmd_backup)

    s = sub.add_parser("restore", help="restore a backup archive (then run `veil apply`)")
    s.add_argument("file")
    s.set_defaults(fn=cmd_restore)
    return ap


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        # Never crash the menu over a terminal that cannot show Chinese text.
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(errors="replace")
        from .menu import run
        return run()
    args = build_parser().parse_args(argv)
    if args.cmd == "profile" and args.action == "apply" and not args.file:
        print("veil: profile apply needs a file", file=sys.stderr)
        return 2
    if args.cmd == "device" and args.action in ("add", "rm") and not args.name:
        print("veil: device add/rm needs a name", file=sys.stderr)
        return 2
    try:
        return args.fn(args)
    except (VeilError, subprocess.CalledProcessError, OSError) as exc:
        detail = getattr(exc, "stderr", None)
        print(f"veil: {exc}" + (f"\n{detail}" if detail else ""), file=sys.stderr)
        return 1
