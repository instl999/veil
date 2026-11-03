"""Interactive management menu: what `veil` shows when run without arguments."""
from __future__ import annotations

import os
import re
import secrets
import subprocess
import tempfile
from pathlib import Path

from . import __version__, net, render_client
from .core import P, VeilError, load_state

FINGERPRINT_CHOICES = [
    ("chrome", "Chrome on Windows/macOS/Linux, OpenClash router"),
    ("safari", "Safari on macOS"),
    ("ios", "iPhone / iPad"),
    ("android", "Android phone"),
    ("edge", "Microsoft Edge"),
    ("firefox", "Firefox"),
    ("random", "random each connection"),
]
CLIENT_CHOICES = ["clash-verge", "flclash", "openclash", "shadowrocket", "stash", "other"]


def _cli(*argv: str) -> int:
    from .cli import main
    return main(list(argv))


def _ask(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except EOFError:
        return ""


def _pause() -> None:
    _ask("\nPress Enter to continue / 按回车继续...")


def _confirm(prompt: str, default: bool = False) -> bool:
    hint = "Y/n" if default else "y/N"
    answer = _ask(f"{prompt} [{hint}]: ").lower()
    return default if not answer else answer in ("y", "yes", "是")


def _pick(title: str, options: list[str]) -> int | None:
    """Numbered choice; returns the 0-based index or None."""
    print(f"\n  {title}")
    for i, opt in enumerate(options, 1):
        print(f"    {i}. {opt}")
    raw = _ask("  Number / 编号: ")
    if raw.isdigit() and 1 <= int(raw) <= len(options):
        return int(raw) - 1
    return None


def _service_state() -> str:
    try:
        out = subprocess.run(["systemctl", "is-active", "veil-singbox"],
                             capture_output=True, text=True).stdout.strip()
    except FileNotFoundError:
        return "unknown"
    return "running / 运行中" if out == "active" else f"{out or 'stopped'} / 未运行"


def _devices() -> list[str]:
    return list(load_state()["profile"]["devices"])


# ---------------------------------------------------------------- actions

def show_qr() -> None:
    names = list(render_client.subscription_urls(load_state()))
    idx = _pick("QR code for which device? / 显示哪台设备的二维码？", names)
    if idx is not None:
        _cli("links", "--qr", names[idx])


def add_device() -> None:
    name = _ask("\n  New device name, e.g. ipad, work-laptop / 新设备名，如 ipad、work-laptop: ").lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,30}", name):
        print("  Use lowercase letters, digits and '-' / 只能使用小写字母、数字和 '-'")
        return
    if name in _devices():
        print(f"  '{name}' already exists / 已存在")
        return
    fp = _pick("Browser/OS of this device (TLS fingerprint) / 该设备的浏览器或系统（TLS 指纹）",
               [f"{f:<8} {d}" for f, d in FINGERPRINT_CHOICES])
    if fp is None:
        return
    client = _pick("Client app / 客户端应用", CLIENT_CHOICES)
    if client is None:
        return
    if _cli("device", "add", name, "--fingerprint", FINGERPRINT_CHOICES[fp][0],
            "--client", CLIENT_CHOICES[client]) == 0:
        state = load_state()
        url = render_client.subscription_urls(state)[name]
        print(f"\n  Subscription URL / 订阅链接:\n  {url}")
        if name in (imports := render_client.import_links(state)):
            print(f"\n  FlClash one-tap import / FlClash 一键导入:\n  {imports[name]}")
        if _confirm("  Show its QR code? / 显示二维码？", True):
            _cli("links", "--qr", name)


def remove_device() -> None:
    names = _devices()
    idx = _pick("Remove which device? / 删除哪台设备？", names)
    if idx is None:
        return
    if len(names) == 1:
        print("  Keep at least one device / 至少保留一台设备")
        return
    if _confirm(f"  Remove '{names[idx]}'? Its subscription URL stops working. / 删除 '{names[idx]}'？其订阅链接将失效。"):
        _cli("device", "rm", names[idx])


def reset_subscription() -> None:
    print("\n  This creates new subscription URLs for ALL devices. Use it if a URL leaked.")
    print("  所有设备都会获得新的订阅链接，旧链接立即失效。适用于链接泄露的情况。")
    if _ask("  Type 'yes' to continue / 输入 yes 继续: ").lower() == "yes":
        _cli("reset-sub")


def rotate_now() -> None:
    state = load_state()
    days = state["maint"]["grace_days"]
    print(f"\n  New proxy credentials; the old ones keep working for {days} days so clients")
    print(f"  switch over on their next subscription update. / 旧凭据继续有效 {days} 天，客户端更新订阅后自动切换。")
    if _confirm("  Rotate now? / 立即轮换？"):
        _cli("rotate", "creds", "short_id")


def apply_profile() -> None:
    print("\n  Paste the contents of profile.json (from veil_fit.py), then type END on its own line.")
    print("  粘贴 profile.json 的内容（由 veil_fit.py 生成），然后单独一行输入 END。\n")
    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip() == "END":
            break
        lines.append(line)
    if not lines:
        return
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    try:
        _cli("profile", "apply", fh.name)
    finally:
        os.unlink(fh.name)


def alerts() -> None:
    """Problem alerts on the phone: ntfy (any phone) or Bark (iPhone, works in China)."""
    m = load_state()["maint"]
    print(f"\n  Alerts / 故障提醒: {m['notify_url'] or 'off / 未开启'}")
    print("  The server checks itself every night and sends a message here when something is wrong.")
    print("  服务器每晚自检，发现问题时会把消息发到这里。")
    idx = _pick("Choose / 请选择  (Enter = back / 回车返回)", [
        "ntfy - free app for iPhone and Android / 免费应用，支持 iPhone 和安卓",
        "Bark - free iPhone app that also works inside China / 免费 iPhone 应用，国内可用",
        "Send a test alert / 发送测试提醒",
        "Turn alerts off / 关闭提醒",
    ])
    if idx == 0:
        topic = f"veil-{secrets.token_hex(6)}"
        print("\n  1. Install the free app ntfy on your phone (App Store / Google Play).")
        print("     在手机上安装免费应用 ntfy（App Store / Google Play）。")
        print(f"  2. In the app tap + and subscribe to the topic / 在应用中点 +，订阅主题:  {topic}")
        print("     (a random name, so nobody else can read your alerts / 随机名字，别人无法读取你的提醒)")
        if _confirm("  3. Done? Send a test alert now / 完成了吗？现在发送测试提醒", True):
            url = f"https://ntfy.sh/{topic}"
            _cli("set", "notify_url", url)
            _cli("alert-test")
    elif idx == 1:
        print("\n  1. Install Bark from the App Store and open it. / 从 App Store 安装 Bark 并打开。")
        print("  2. Copy the URL it shows, like https://api.day.app/AbCdEf123/ (only up to the key).")
        print("     复制它显示的地址，如 https://api.day.app/AbCdEf123/（只到密钥为止）。")
        url = _ask("  Paste it here / 粘贴到这里: ")
        if re.fullmatch(r"https://api\.day\.app/[A-Za-z0-9]+/?", url):
            _cli("set", "notify_url", url.rstrip("/"))
            _cli("alert-test")
        elif url:
            print("  That does not look like a Bark URL / 这不像 Bark 地址")
    elif idx == 2:
        _cli("alert-test")
    elif idx == 3:
        _cli("set", "notify_url", "")


def settings() -> None:
    while True:
        m = load_state()["maint"]
        options = [
            f"Alerts on your phone / 手机故障提醒: {'on / 开' if m['notify_url'] else 'off / 关'}",
            f"Automatic sing-box/Caddy upgrades / 自动升级: {'on / 开' if m['auto_upgrade'] else 'off / 关'}",
            f"Rotate credentials every N days (0 = off) / 凭据轮换周期（天）: {m['rotate_days']}",
            f"Grace period for old credentials (days) / 旧凭据宽限期（天）: {m['grace_days']}",
        ]
        idx = _pick("Settings / 设置  (Enter = back / 回车返回)", options)
        if idx is None:
            return
        if idx == 0:
            alerts()
        elif idx == 1:
            _cli("set", "auto_upgrade", "false" if m["auto_upgrade"] else "true")
        elif idx in (2, 3):
            value = _ask("  Days / 天数: ")
            if value.isdigit():
                _cli("set", "rotate_days" if idx == 2 else "grace_days", value)


def _read_pem(end: str) -> str:
    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        lines.append(line.rstrip("\r"))
        if re.search(end, line):
            break
    return "\n".join(lines) + "\n"


def change_cdn_host() -> None:
    state = load_state()
    print("\n  Move the CDN route to another domain (best: one unrelated to "
          f"{state['site_host'].split('.', 1)[-1]}).")
    print("  把 CDN 线路换到另一个域名（最好与主域名无关）。\n")
    print("  In Cloudflare, for that domain / 在 Cloudflare 中为该域名：")
    print("    1. DNS: A record -> this server's IP, Proxied (orange) / A 记录指向本服务器，已代理（橙色）")
    print("    2. SSL/TLS > Overview: Full (strict) / 完全（严格）")
    print("    3. SSL/TLS > Origin Server > Create Certificate (keep this page open) / 创建源服务器证书")
    print("    4. SSL/TLS > Origin Server > Authenticated Origin Pulls: On / 开启")
    host = _ask("\n  New CDN host, e.g. cdn.example.net / 新 CDN 主机名: ").lower()
    if not re.fullmatch(r"([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", host):
        print("  Not a valid host name / 主机名无效")
        return
    if not net.behind_cloudflare(host) and not _confirm(
            f"  {host} does not answer through Cloudflare yet (orange cloud?). Continue anyway? / "
            "尚未通过 Cloudflare 访问（橙色云朵？），仍然继续？"):
        return
    with tempfile.TemporaryDirectory() as tmp:
        crt, key = os.path.join(tmp, "origin.pem"), os.path.join(tmp, "origin.key")
        if _confirm("  Paste a Cloudflare origin certificate now? (No = self-signed, SSL mode Full) / "
                    "现在粘贴源服务器证书？（否 = 自签名，SSL 模式设为完全）", True):
            print("\n  Paste the Origin Certificate / 粘贴源服务器证书:")
            Path(crt).write_text(_read_pem(r"END CERTIFICATE"))
            print("  Paste the Private Key / 粘贴私钥:")
            Path(key).write_text(_read_pem(r"END .*PRIVATE KEY"))
            os.chmod(key, 0o600)
            args = ["--cert", crt, "--key", key]
        else:
            args = []
        if _cli("cdn-host", host, *args) == 0:
            print("\n  Then remove the old CDN record from Cloudflare. / 然后在 Cloudflare 删除旧的 CDN 记录。")
            _cli("origin-pull")


def backups() -> None:
    idx = _pick("Backups / 备份  (Enter = back / 回车返回)", [
        "Make a backup to copy to your computer / 生成备份并复制到你的电脑",
        "List the automatic nightly backups / 查看每晚自动备份",
        "How to restore / 如何恢复",
    ])
    if idx == 0:
        _cli("backup")
    elif idx == 1:
        _cli("backup", "--list")
    elif idx == 2:
        print("\n  New server (same domains): copy the backup there, point the DNS records at the")
        print("  new IP, then run:  bash veil-install.sh --restore veil-backup-XXXX.tar.gz")
        print("  Devices need no changes. / 新服务器（同样的域名）：把备份复制过去，把 DNS 记录指向新 IP，")
        print("  然后运行：bash veil-install.sh --restore veil-backup-XXXX.tar.gz。设备无需任何改动。")
        print("\n  Undo a change on this server / 在本服务器上撤销修改:")
        print("    veil restore /var/lib/veil/backups/veil-YYYYMMDD.tar.gz && veil apply --restart")


def logs() -> None:
    names = ["proxy", "web", "maint", "fail2ban", "all"]
    idx = _pick("Which log? (last 100 lines) / 查看哪个日志？（最近 100 行）", [
        "proxy - sing-box / 代理", "web - Caddy / 网站", "maint - nightly maintenance / 每晚维护",
        "fail2ban - SSH bans / SSH 封禁", "all / 全部"])
    if idx is not None:
        _cli("logs", names[idx])


def update() -> None:
    _cli("update", "--check")
    if _confirm("\n  Update veil now? Keys, settings and links stay the same. / "
                "现在更新 veil？密钥、设置和链接都保持不变。", True):
        _cli("update")


def uninstall() -> None:
    if not P.INSTALLER.exists():
        print(f"  ({P.INSTALLER} not found / 未找到)")
        return
    if _confirm("\n  Uninstall veil from this server? / 从本服务器卸载 veil？"):
        os.execvp("bash", ["bash", str(P.INSTALLER), "--uninstall"])


MENU = [
    ("Devices and subscriptions / 设备与订阅", None),
    ("Show subscription links / 显示订阅链接", lambda: _cli("links")),
    ("Show QR code / 显示二维码", show_qr),
    ("Add a device / 添加设备", add_device),
    ("Remove a device / 删除设备", remove_device),
    ("Reset subscription URLs (if leaked) / 重置订阅链接（泄露时）", reset_subscription),
    ("Health / 健康", None),
    ("Check everything (doctor) / 全面检查", lambda: _cli("doctor")),
    ("View logs / 查看日志", logs),
    ("Maintenance / 维护", None),
    ("Settings: alerts, rotation, upgrades / 设置：提醒、轮换、升级", settings),
    ("Rotate proxy credentials now / 立即轮换代理凭据", rotate_now),
    ("Run nightly maintenance now / 立即执行每晚维护", lambda: _cli("maint")),
    ("Backups / 备份", backups),
    ("Restart services / 重启服务", lambda: _cli("apply", "--restart")),
    ("Advanced / 高级", None),
    ("Change CDN domain / 更换 CDN 域名", change_cdn_host),
    ("Apply personalization profile / 应用个性化画像", apply_profile),
    ("Update veil / 更新 veil", update),
    ("Uninstall veil / 卸载 veil", uninstall),
]


def run() -> int:
    while True:
        try:
            site = load_state()["site_host"]
        except VeilError:
            print("veil is not installed yet - run veil-install.sh / 尚未安装，请运行 veil-install.sh")
            return 1
        print(f"\n  veil {__version__}  ·  {site}  ·  proxy / 代理: {_service_state()}")
        actions = []
        for label, fn in MENU:
            if fn is None:
                print(f"\n  ── {label} ──")
                continue
            actions.append(fn)
            print(f"  {len(actions):>2}. {label}")
        print("   0. Exit / 退出\n")
        try:
            choice = input("Choose / 请选择: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if choice in ("0", "q", ""):
            return 0
        if choice.isdigit() and 1 <= int(choice) <= len(actions):
            try:
                actions[int(choice) - 1]()
            except KeyboardInterrupt:
                print()
            _pause()
