"""`veil doctor`: every check, explained in plain words, with how to fix it.

`veil status` is the machine-readable summary; this is the one for people.
"""
from __future__ import annotations

import json
import shutil
import sys
import time
from dataclasses import dataclass, field

from . import __version__, net, system
from .core import P
from .render_server import hy2_ready

OK, INFO, WARN, FAIL = "ok", "info", "warn", "fail"
_MARK = {OK: ("\033[32m", "OK "), INFO: ("\033[36m", " i "), WARN: ("\033[33m", " ! "),
         FAIL: ("\033[31m", "XX ")}


@dataclass
class Check:
    level: str
    en: str
    zh: str
    fix: list[str] = field(default_factory=list)  # alternating English / Chinese lines


def _c(level: str, en: str, zh: str, *fix: str) -> Check:
    return Check(level, en, zh, list(fix))


# ---------------------------------------------------------------- system

def check_system(state: dict) -> list[Check]:
    out = []
    names = {system.SINGBOX_UNIT: ("proxy (sing-box)", "代理（sing-box）"),
             "caddy": ("web server (Caddy)", "网站服务（Caddy）"),
             system.NFT_UNIT: ("port-hopping rules", "端口跳跃规则"),
             "fail2ban": ("SSH brute-force protection (Fail2ban)", "SSH 防爆破（Fail2ban）"),
             "veil-maint.timer": ("nightly maintenance timer", "每晚维护定时器")}
    for unit, (en, zh) in names.items():
        state_ = system.systemctl("is-active", unit, check=False).stdout.strip()
        if state_ == "active":
            out.append(_c(OK, f"{en}: running", f"{zh}：运行中"))
        else:
            out.append(_c(FAIL, f"{en}: {state_ or 'not running'}", f"{zh}：未运行（{state_}）",
                          f"See why: journalctl -u {unit} -n 50 --no-pager, then: veil apply --restart",
                          f"查看原因：journalctl -u {unit} -n 50 --no-pager，然后运行：veil apply --restart"))

    synced = system.run(["timedatectl", "show", "-p", "NTPSynchronized", "--value"],
                        check=False).stdout.strip()
    if synced == "yes":
        out.append(_c(OK, "clock is synchronized (REALITY needs it within 2 minutes)",
                      "时钟已同步（REALITY 要求误差在 2 分钟以内）"))
    else:
        out.append(_c(WARN, "clock is not synchronized yet", "时钟尚未同步",
                      "Run: timedatectl set-ntp true   (wait a minute, then check again)",
                      "运行：timedatectl set-ntp true（等一分钟后再检查）"))

    try:
        cc = open("/proc/sys/net/ipv4/tcp_congestion_control").read().strip()
    except OSError:
        cc = "unknown"
    out.append(_c(OK if cc == "bbr" else INFO, f"TCP congestion control: {cc}",
                  f"TCP 拥塞控制：{cc}",
                  *([] if cc == "bbr" else
                    ["BBR is unavailable on this kernel (common in containers); veil still works.",
                     "该内核不支持 BBR（容器中常见），veil 仍可正常使用。"])))

    free = shutil.disk_usage("/").free / 2**30
    level = FAIL if free < 1 else WARN if free < 3 else OK
    out.append(_c(level, f"free disk space: {free:.1f} GiB", f"剩余磁盘空间：{free:.1f} GiB",
                  *([] if level == OK else
                    ["Free space: apt-get clean; journalctl --vacuum-size=100M",
                     "清理空间：apt-get clean；journalctl --vacuum-size=100M"])))

    if P.REBOOT_REQUIRED.exists():
        out.append(_c(INFO, "an update is waiting for a restart; the server restarts by itself "
                            "at 22:00 UTC (06:00 China time)",
                      "有更新等待重启；服务器会在 UTC 22:00（北京时间 06:00）自动重启",
                      "To restart now: reboot   (veil starts again by itself)",
                      "如需立即重启：reboot（veil 会自动重新启动）"))

    held = system.run(["apt-mark", "showhold"], check=False).stdout.split()
    for pkg in ("sing-box", "caddy"):
        if pkg in held:
            out.append(_c(WARN, f"{pkg} upgrades are on hold (a past upgrade failed its checks)",
                          f"{pkg} 已暂停升级（之前的升级未通过检查）",
                          f"After a newer version is out, run: apt-mark unhold {pkg} && veil maint",
                          f"有新版本后运行：apt-mark unhold {pkg} && veil maint"))
    return out


# ---------------------------------------------------------------- site host

def check_site(state: dict, public_ip: str | None) -> list[Check]:
    site = state["site_host"]
    out = []
    addrs = net.resolve_a(site)
    if public_ip and public_ip in addrs:
        out.append(_c(OK, f"{site} points to this server ({public_ip})",
                      f"{site} 已指向本服务器（{public_ip}）"))
    elif not addrs:
        out.append(_c(FAIL, f"{site} has no DNS record", f"{site} 没有 DNS 记录",
                      f"Cloudflare > DNS > Add record: A, name {site.split('.')[0]}, "
                      f"IPv4 {public_ip or 'this server'}, Proxy status DNS only (grey cloud).",
                      f"Cloudflare > DNS > 添加记录：A，名称 {site.split('.')[0]}，"
                      f"IPv4 {public_ip or '本服务器 IP'}，代理状态：仅 DNS（灰色云朵）。"))
    elif net.behind_cloudflare(site):
        out.append(_c(FAIL, f"{site} is proxied by Cloudflare (orange cloud)",
                      f"{site} 正被 Cloudflare 代理（橙色云朵）",
                      "Cloudflare > DNS: click the orange cloud of this record so it turns grey "
                      "(DNS only). REALITY only works when the name points straight here.",
                      "Cloudflare > DNS：点击该记录的橙色云朵，使其变为灰色（仅 DNS）。"
                      "REALITY 要求域名直接指向本服务器。"))
    else:
        out.append(_c(FAIL, f"{site} points to {', '.join(addrs)}, not to this server "
                            f"({public_ip or 'unknown'})",
                      f"{site} 指向 {', '.join(addrs)}，而不是本服务器（{public_ip or '未知'}）",
                      "Cloudflare > DNS: edit the A record so its IPv4 address is this server's IP.",
                      "Cloudflare > DNS：把该 A 记录的 IPv4 地址改为本服务器 IP。"))

    days = system.cert_days_left(P.SITE_CRT)
    if days is None:
        out.append(_c(FAIL, "no Let's Encrypt certificate for the site yet", "站点还没有 Let's Encrypt 证书",
                      "It needs the DNS record above and TCP port 80 open (provider firewall). "
                      "Then run: veil sync-cert && veil apply",
                      "需要上面的 DNS 记录正确，且 TCP 80 端口已放行（服务商防火墙）。然后运行：veil sync-cert && veil apply"))
    else:
        level = OK if days >= 14 else WARN
        out.append(_c(level, f"site certificate valid for {days:.0f} more days (renews by itself)",
                      f"站点证书还剩 {days:.0f} 天（会自动续期）",
                      *([] if level == OK else
                        ["Renewal needs TCP 80 reachable; check the provider firewall, then: veil maint",
                         "续期需要 TCP 80 可访问；检查服务商防火墙，然后运行：veil maint"])))

    err = system.probe_site(site)
    out.append(_c(OK, "the cover website answers on port 443", "伪装网站在 443 端口正常响应")
               if not err else
               _c(FAIL, f"the cover website does not answer on port 443: {err}",
                  f"伪装网站在 443 端口无响应：{err}",
                  "Run: veil apply --restart, then veil doctor again.",
                  "运行：veil apply --restart，然后再次运行 veil doctor。"))

    if state["hy2"]["enabled"]:
        if hy2_ready(state):
            out.append(_c(OK, f"Hysteria2 is on (UDP 443, port hopping {state['hy2']['hop']})",
                          f"Hysteria2 已开启（UDP 443，端口跳跃 {state['hy2']['hop']}）",
                          f"If your provider has a firewall, allow UDP 443 and UDP {state['hy2']['hop']}.",
                          f"如果服务商有防火墙，请放行 UDP 443 和 UDP {state['hy2']['hop']}。"))
        else:
            out.append(_c(WARN, "Hysteria2 waits for the site certificate", "Hysteria2 正在等待站点证书"))
    return out


# ---------------------------------------------------------------- CDN host

# What Cloudflare's own error pages mean for this setup.
CF_ERRORS = {
    520: ("Cloudflare got an unexpected answer from the server; usually its client certificate "
          "was refused.",
          "Cloudflare 收到了服务器的异常响应；通常是它的客户端证书被拒绝。",
          "Run: veil origin-pull   (veil stops requiring the certificate if that is the cause)",
          "运行：veil origin-pull（如果是这个原因，veil 会停止强制要求证书）"),
    521: ("the server refused Cloudflare's connection.",
          "服务器拒绝了 Cloudflare 的连接。",
          "Make sure TCP 443 is open in the provider firewall, then: veil apply --restart",
          "确认服务商防火墙已放行 TCP 443，然后运行：veil apply --restart"),
    522: ("Cloudflare timed out connecting to the server.", "Cloudflare 连接服务器超时。",
          "Check the A record's IP and that TCP 443 is open in the provider firewall.",
          "检查 A 记录的 IP，以及服务商防火墙是否放行 TCP 443。"),
    523: ("Cloudflare cannot reach the server's IP.", "Cloudflare 无法访问服务器 IP。",
          "Check the A record's IPv4 address.", "检查 A 记录的 IPv4 地址。"),
    524: ("the server took too long to answer Cloudflare.", "服务器响应 Cloudflare 太慢。",
          "Run: veil apply --restart", "运行：veil apply --restart"),
    525: ("the TLS handshake between Cloudflare and the server failed.",
          "Cloudflare 与服务器之间的 TLS 握手失败。",
          "If you switched Authenticated Origin Pulls off, switch it back on "
          "(SSL/TLS > Origin Server), then: veil origin-pull",
          "如果你关闭了 Authenticated Origin Pulls，请重新开启（SSL/TLS > 源服务器），然后运行：veil origin-pull"),
    526: ("Cloudflare does not accept the server's certificate (SSL mode Full (strict) needs a "
          "Cloudflare origin certificate).",
          "Cloudflare 不接受服务器的证书（完全（严格）模式需要 Cloudflare 源服务器证书）。",
          "Create one in Cloudflare (SSL/TLS > Origin Server > Create Certificate) and paste it: "
          "veil > Change CDN domain (same name), or: veil cdn-cert --cert FILE --key FILE",
          "在 Cloudflare 创建（SSL/TLS > 源服务器 > 创建证书）并粘贴：veil > 更换 CDN 域名（同一名字），"
          "或运行：veil cdn-cert --cert 文件 --key 文件"),
}


def check_cdn(state: dict, public_ip: str | None) -> list[Check]:
    c = state["cdn"]
    if not c["enabled"]:
        return [_c(INFO, "no CDN route configured (optional backup route through Cloudflare)",
                   "未配置 CDN 线路（可选的 Cloudflare 备用线路）",
                   "Add one any time: veil > Change CDN domain", "随时可以添加：veil > 更换 CDN 域名")]
    host = c["host"]
    out = []
    if net.behind_cloudflare(host):
        out.append(_c(OK, f"{host} is proxied by Cloudflare (orange cloud)",
                      f"{host} 已由 Cloudflare 代理（橙色云朵）"))
    else:
        addrs = net.resolve_a(host)
        if not addrs:
            fix = (f"Cloudflare > DNS > Add record: A, name {host.split('.')[0]}, IPv4 "
                   f"{public_ip or 'this server'}, Proxy status Proxied (orange cloud).",
                   f"Cloudflare > DNS > 添加记录：A，名称 {host.split('.')[0]}，IPv4 "
                   f"{public_ip or '本服务器 IP'}，代理状态：已代理（橙色云朵）。")
            out.append(_c(FAIL, f"{host} has no DNS record", f"{host} 没有 DNS 记录", *fix))
        else:
            out.append(_c(FAIL, f"{host} is not proxied by Cloudflare", f"{host} 未被 Cloudflare 代理",
                          "Cloudflare > DNS: click the grey cloud of this record so it turns orange "
                          "(Proxied).",
                          "Cloudflare > DNS：点击该记录的灰色云朵，使其变为橙色（已代理）。"))
        return out

    status, headers, _, err = net.fetch(f"https://{host}/", timeout=20, redirects=False)
    location = headers.get("Location", headers.get("location", ""))
    if status == 200:
        out.append(_c(OK, "the CDN host answers through Cloudflare", "CDN 主机名可通过 Cloudflare 访问"))
    elif status in (301, 302, 307, 308) and location.startswith(f"https://{host}"):
        out.append(_c(FAIL, "Cloudflare's SSL mode is Flexible (it connects to the server without "
                            "encryption and loops)",
                      "Cloudflare 的 SSL 模式是灵活（Flexible），它不加密地连接服务器并陷入循环",
                      "Cloudflare > SSL/TLS > Overview > Configure: Full (strict).",
                      "Cloudflare > SSL/TLS > 概述 > 配置：完全（严格）。"))
    elif status in CF_ERRORS:
        en, zh, fix_en, fix_zh = CF_ERRORS[status]
        out.append(_c(FAIL, f"Cloudflare error {status}: {en}", f"Cloudflare 错误 {status}：{zh}",
                      fix_en, fix_zh))
    elif status == 403 and "cloudflare" in headers.get("Server", headers.get("server", "")).lower():
        out.append(_c(FAIL, "a Cloudflare security rule blocks requests to the CDN host",
                      "Cloudflare 的安全规则拦截了对 CDN 主机名的请求",
                      "Cloudflare > Security: turn Bot Fight Mode off and check WAF custom rules.",
                      "Cloudflare > 安全性：关闭 Bot Fight Mode，并检查 WAF 自定义规则。"))
    else:
        out.append(_c(FAIL, f"the CDN host does not answer properly through Cloudflare "
                            f"({status or err})",
                      f"CDN 主机名通过 Cloudflare 访问异常（{status or err}）",
                      "Wait a few minutes after DNS changes, then run veil doctor again.",
                      "DNS 修改后请等待几分钟，再运行 veil doctor。"))
        return out
    if status != 200:
        return out

    line = net.websocket_upgrade(host, c["path"])
    if " 101" in line:
        out.append(_c(OK, "WebSocket tunnel works through Cloudflare", "WebSocket 隧道可通过 Cloudflare 使用"))
    else:
        out.append(_c(FAIL, f"WebSocket tunnel fails through Cloudflare ({line})",
                      f"WebSocket 隧道无法通过 Cloudflare 使用（{line}）",
                      "Cloudflare > Network: WebSockets On.", "Cloudflare > 网络：WebSockets 开启。"))

    days = system.cert_days_left(P.CDN_CRT)
    if days is None:
        out.append(_c(WARN, "the CDN host uses a self-signed certificate (works only with SSL mode "
                            "Full, not Full (strict))",
                      "CDN 主机名使用自签名证书（只能配合完全模式，不能使用完全（严格））",
                      "Better: create a Cloudflare origin certificate and paste it via "
                      "veil > Change CDN domain (same name), then set Full (strict).",
                      "更好的做法：创建 Cloudflare 源服务器证书，通过 veil > 更换 CDN 域名（同一名字）粘贴，"
                      "然后设为完全（严格）。"))
    else:
        out.append(_c(OK if days >= 30 else WARN,
                      f"Cloudflare origin certificate valid for {days:.0f} more days",
                      f"Cloudflare 源服务器证书还剩 {days:.0f} 天"))

    err = system.origin_pull(state)
    if state["cdn"]["origin_pull"]:
        out.append(_c(OK, "Authenticated Origin Pulls is enforced: the CDN host only answers Cloudflare",
                      "Authenticated Origin Pulls 已强制执行：CDN 主机名只响应 Cloudflare"))
    elif err:
        out.append(_c(FAIL, err, "Authenticated Origin Pulls 检查失败（见英文说明）"))
    else:
        out.append(_c(WARN, "Authenticated Origin Pulls is off in Cloudflare",
                      "Cloudflare 中的 Authenticated Origin Pulls 尚未开启",
                      f"Cloudflare > the domain of {host} > SSL/TLS > Origin Server > "
                      "Authenticated Origin Pulls: On. veil then enforces it by itself.",
                      f"Cloudflare > {host} 所在域名 > SSL/TLS > 源服务器 > Authenticated Origin Pulls：开启。"
                      "之后 veil 会自动强制执行。"))
    return out


# ---------------------------------------------------------------- upkeep

def check_upkeep(state: dict) -> list[Check]:
    m = state["maint"]
    out = []
    if m["notify_url"]:
        kind = "Bark" if system.is_bark(m["notify_url"]) else "ntfy"
        out.append(_c(OK, f"problem alerts go to your phone ({kind})", f"故障提醒会发送到你的手机（{kind}）"))
    else:
        out.append(_c(WARN, "problem alerts are off: nobody hears about problems the nightly check finds",
                      "故障提醒未开启：每晚自检发现的问题没有人会知道",
                      "Set them up: veil > Settings > Alerts", "设置方法：veil > 设置 > 故障提醒"))

    try:
        status = json.loads(P.STATUS.read_text(encoding="utf-8"))
        age = (time.time() - status["time"]) / 3600
        if status.get("problems"):
            out.append(_c(WARN, f"last nightly maintenance ({age:.0f} h ago) reported: "
                                + "; ".join(status["problems"]),
                          f"上次每晚维护（{age:.0f} 小时前）报告了问题（见英文）",
                          "Run it again after fixing: veil maint", "修复后重新运行：veil maint"))
        elif age > 48:
            out.append(_c(WARN, f"nightly maintenance last ran {age:.0f} hours ago",
                          f"每晚维护上次运行于 {age:.0f} 小时前",
                          "Check: systemctl status veil-maint.timer", "检查：systemctl status veil-maint.timer"))
        else:
            out.append(_c(OK, f"nightly maintenance ran {age:.0f} h ago without problems",
                          f"每晚维护于 {age:.0f} 小时前运行，没有问题"))
    except (OSError, ValueError, KeyError):
        out.append(_c(INFO, "nightly maintenance has not run yet (it runs between 19:00 and 21:00 UTC)",
                      "每晚维护尚未运行（在 UTC 19:00–21:00 之间运行）"))

    backups = system.list_backups()
    if backups:
        age = (time.time() - backups[-1].stat().st_mtime) / 86400
        out.append(_c(OK if age < 3 else WARN, f"{len(backups)} automatic backups on the server, "
                                               f"newest {age:.0f} days old",
                      f"服务器上有 {len(backups)} 份自动备份，最新的是 {age:.0f} 天前",
                      "Keep one copy on your own computer too: veil > Backups",
                      "也请在自己的电脑上保存一份：veil > 备份"))
    else:
        out.append(_c(INFO, "no automatic backup yet (made every night)", "尚无自动备份（每晚自动生成）",
                      "Make one now and copy it to your computer: veil > Backups",
                      "现在就做一份并复制到你的电脑：veil > 备份"))

    latest = system.latest_release()
    newer = latest if latest and system._vtuple(latest) > system._vtuple(__version__) else None
    if not latest:
        out.append(_c(INFO, f"veil {__version__}; could not check GitHub for a newer release",
                      f"veil {__version__}；无法从 GitHub 检查新版本"))
    elif newer:
        out.append(_c(INFO, f"veil {newer} is available (installed: {__version__})",
                      f"veil {newer} 已发布（当前：{__version__}）",
                      "Update: veil update   (keys, settings and links stay the same)",
                      "更新：veil update（密钥、设置和链接都保持不变）"))
    else:
        out.append(_c(OK, f"veil {__version__} is the latest version", f"veil {__version__} 已是最新版本"))
    return out


# ---------------------------------------------------------------- report

SECTIONS = {
    "system": ("Server", "服务器"),
    "site": ("Site host and direct routes", "站点主机名与直连线路"),
    "cdn": ("CDN route (Cloudflare)", "CDN 线路（Cloudflare）"),
    "upkeep": ("Maintenance, alerts, backups", "维护、提醒与备份"),
}


def run(state: dict, only: list[str] | None = None) -> dict[str, list[Check]]:
    wanted = only or list(SECTIONS)
    ip = net.public_ipv4() if {"site", "cdn"} & set(wanted) else None
    funcs = {"system": lambda: check_system(state), "site": lambda: check_site(state, ip),
             "cdn": lambda: check_cdn(state, ip), "upkeep": lambda: check_upkeep(state)}
    return {name: funcs[name]() for name in SECTIONS if name in wanted}


def render(results: dict[str, list[Check]], color: bool | None = None) -> str:
    color = sys.stdout.isatty() if color is None else color
    lines = []
    for name, checks in results.items():
        en, zh = SECTIONS[name]
        lines.append(f"\n  {en} / {zh}")
        for chk in checks:
            tint, mark = _MARK[chk.level]
            mark = f"{tint}{mark}\033[0m" if color else mark
            lines.append(f"   {mark} {chk.en}")
            lines.append(f"       {chk.zh}")
            for i, fix in enumerate(chk.fix):
                lines.append(f"       {'->' if i % 2 == 0 else '  '} {fix}")
    counts = {lvl: sum(c.level == lvl for cs in results.values() for c in cs) for lvl in _MARK}
    lines.append(f"\n  {counts[FAIL]} problem(s), {counts[WARN]} warning(s) / "
                 f"{counts[FAIL]} 个问题，{counts[WARN]} 个警告\n")
    return "\n".join(lines)


def failed(results: dict[str, list[Check]]) -> bool:
    return any(c.level == FAIL for cs in results.values() for c in cs)
