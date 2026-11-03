#!/usr/bin/env bash
# veil - one-click installer and manager. Debian 11+/Ubuntu 22.04+, run as root.
# veil 一键安装与管理脚本。适用于 Debian 11+/Ubuntu 22.04+，需以 root 运行。
#
#   bash veil-install.sh                 guided install (a menu if already installed)
#                                        分步引导安装（已安装时显示菜单）
#   bash veil-install.sh --update        update veil, keep keys / 更新 veil，保留密钥
#   bash veil-install.sh --uninstall     remove veil / 卸载 veil
#   bash veil-install.sh --restore FILE  rebuild from a `veil backup` archive / 从备份恢复（迁移）
#   bash veil-install.sh --site-host H --email E [--cdn-host H --cdn-cert F --cdn-key F]
#                        [--no-hy2] [--upgrade] [--notify URL] [--yes]
#                                      non-interactive install / 非交互安装
# Safe to run again at any time. / 可随时重复运行。
# After installing, type `veil` for the management menu. / 安装后输入 `veil` 打开管理菜单。
set -Eeuo pipefail

SELF="$(readlink -f "${BASH_SOURCE[0]}" 2>/dev/null || echo "${BASH_SOURCE[0]}")"
HERE="$(dirname "$SELF")"
SITE_HOST="" CDN_HOST="" EMAIL="" RESTORE="" CDN_CERT="" CDN_KEY="" EXTRACT_TO=""
NO_HY2=0 ASSUME_YES=0 UPGRADE=0 MODE="" FRESH=1 PUBLIC_IP="" SRC="" TMPD=""
NOTIFY_URL="" INTERACTIVE=0
LOG=/var/log/veil-install.log
HOST_RE='^([A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$'
EMAIL_RE='^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$'

say()  { printf '\033[1;32m==>\033[0m %s\n' "$1"; [[ -z "${2:-}" ]] || printf '    \033[2m%s\033[0m\n' "$2"; }
warn() { printf '\033[1;33m!!\033[0m  %s\n' "$1" >&2; [[ -z "${2:-}" ]] || printf '    %s\n' "$2" >&2; }
die()  { printf '\033[1;31mxx\033[0m  %s\n' "$1" >&2; [[ -z "${2:-}" ]] || printf '    %s\n' "$2" >&2; exit 1; }
cleanup() { [[ -z "$TMPD" ]] || rm -rf "$TMPD"; }
trap cleanup EXIT
on_error() {
  # With errtrace, bash also fires ERR for `return 1` from a function used as a
  # condition (confirm ... || x). That is a "no" answer, not a failure.
  if [[ "$2" == return* ]]; then return 0; fi
  die "failed at line $1: $2
    Nothing is lost: fix the cause above and run the installer again - it is safe to rerun.
    Full log: $LOG" "第 $1 行出错。不会丢失任何数据：修复上述原因后重新运行安装脚本即可（可安全重复运行）。完整日志：$LOG"
}
trap 'on_error "$LINENO" "$BASH_COMMAND"' ERR

usage() { sed -n '2,15p' "$SELF" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

# ask VAR "english" "中文" DEFAULT REGEX
ask() {
  local v
  while true; do
    read -rp "  $2 / $3${4:+ [$4]}: " v || die "input closed"
    v="${v:-${4:-}}"
    if [[ "$v" =~ $5 ]]; then printf -v "$1" '%s' "$v"; return 0; fi
    echo "    Invalid input, try again / 输入无效，请重试"
  done
}

# confirm "english" "中文" y|n
confirm() {
  [[ $ASSUME_YES -eq 1 ]] && return 0
  local a hint="y/N"
  [[ "${3:-n}" == y ]] && hint="Y/n"
  read -rp "  $1 / $2 [$hint]: " a || return 1
  a="${a:-${3:-n}}"
  # Answer with `return`, never with a failing test as the last command: the
  # ERR trap (set -E) would fire inside the function and abort the installer.
  if [[ "$a" =~ ^([yY]|[yY][eE][sS]|是)$ ]]; then return 0; fi
  return 1
}

state_get() { python3 -c "import json,sys;print(json.load(open('/etc/veil/state.json'))$1)"; }

# ================================================================ source files

# Running from the repository uses server/ directly; the single-file installer
# carries the same files as a base64 tarball after the __VEIL_PAYLOAD__ line.
locate_source() {
  if [[ -d "$HERE/veil" && -d "$HERE/decoy" && -d "$HERE/systemd" ]]; then
    SRC="$HERE"
    return
  fi
  [[ -f "$SELF" ]] || die "Save the installer to a file first, e.g.: wget -O veil-install.sh URL && bash veil-install.sh" \
                          "请先把安装脚本保存为文件再运行。"
  local line
  line="$(grep -an '^__VEIL_PAYLOAD__$' "$SELF" | tail -1 | cut -d: -f1)" || true
  [[ -n "$line" ]] || die "Installer payload missing - download veil-install.sh again." "安装包内容缺失，请重新下载。"
  [[ -n "$TMPD" ]] || TMPD="$(mktemp -d)"
  mkdir -p "$TMPD/src"
  tail -n +"$((line + 1))" "$SELF" | base64 -d | tar -xz -C "$TMPD/src" \
    || die "Installer payload is corrupted - download veil-install.sh again." "安装包已损坏，请重新下载。"
  SRC="$TMPD/src"
}

# ================================================================ DNS helpers

detect_public_ip() {
  PUBLIC_IP="$(curl -4 -fsS --max-time 8 https://api.ipify.org 2>/dev/null)" || true
  if [[ -z "$PUBLIC_IP" ]]; then
    PUBLIC_IP="$(ip -4 route get 1.1.1.1 | awk '{for(i=1;i<=NF;i++) if($i=="src") print $(i+1)}')" || true
  fi
}

# A record as seen by a public resolver (avoids the local negative cache while
# you are still creating the record).
dns_ip() {
  local ip
  ip="$(curl -fsS --max-time 8 -H 'accept: application/dns-json' \
        "https://cloudflare-dns.com/dns-query?name=$1&type=A" 2>/dev/null \
        | grep -o '"data":"[0-9.]*"' | head -1 | cut -d'"' -f4)" || true
  [[ -n "$ip" ]] || ip="$(getent ahostsv4 "$1" | awk 'NR==1{print $1}')" || true
  printf '%s' "$ip"
}

behind_cloudflare() {
  if curl -fsS --max-time 6 "http://$1/cdn-cgi/trace" 2>/dev/null | grep -q '^fl='; then return 0; fi
  return 1
}

wait_choice() {
  local a
  read -rp "  [Enter] check again / 重新检查   [s] skip / 跳过   [q] quit / 退出: " a || a=q
  case "$a" in s|S) return 1 ;; q|Q) exit 1 ;; esac
  return 0
}

check_site_dns() {
  local r
  while true; do
    r="$(dns_ip "$SITE_HOST")"
    if [[ -n "$r" && "$r" == "$PUBLIC_IP" ]]; then
      say "DNS OK: $SITE_HOST -> $r"
      return
    fi
    if [[ -z "$r" ]]; then
      warn "$SITE_HOST does not resolve yet." "$SITE_HOST 尚未解析。"
    elif behind_cloudflare "$SITE_HOST"; then
      warn "$SITE_HOST is proxied by Cloudflare (orange cloud). Switch it to DNS only (grey cloud)." \
           "$SITE_HOST 正被 Cloudflare 代理（橙色云朵），请改为仅 DNS（灰色云朵）。"
    else
      warn "$SITE_HOST points to $r, not to this server ($PUBLIC_IP)." "$SITE_HOST 指向 $r，而不是本服务器（$PUBLIC_IP）。"
    fi
    wait_choice || return 0
  done
}

check_cdn_dns() {
  local r
  while true; do
    r="$(dns_ip "$CDN_HOST")"
    if [[ -n "$r" ]] && behind_cloudflare "$CDN_HOST"; then
      say "DNS OK: $CDN_HOST is proxied by Cloudflare"
      return
    fi
    if [[ -z "$r" ]]; then
      warn "$CDN_HOST does not resolve yet." "$CDN_HOST 尚未解析。"
    elif [[ "$r" == "$PUBLIC_IP" ]]; then
      warn "$CDN_HOST points straight at this server. Switch it to Proxied (orange cloud)." \
           "$CDN_HOST 直接指向本服务器，请改为已代理（橙色云朵）。"
    else
      warn "$CDN_HOST resolves to $r but does not look like Cloudflare." "$CDN_HOST 解析为 $r，但不像是 Cloudflare。"
    fi
    wait_choice || return 0
  done
}

# ================================================================ origin certificate

# read_pem FILE END-REGEX: read pasted lines up to and including the END line.
read_pem() {
  local line out=""
  while IFS= read -r line; do
    line="${line%$'\r'}"
    out+="$line"$'\n'
    [[ "$line" =~ $2 ]] && break
  done
  printf '%s' "$out" > "$1"
}

check_origin_cert() {
  openssl x509 -noout -in "$CDN_CERT" 2>/dev/null || { warn "Not a valid certificate." "证书无效。"; return 1; }
  openssl pkey -noout -in "$CDN_KEY" 2>/dev/null || { warn "Not a valid private key." "私钥无效。"; return 1; }
  if [[ "$(openssl x509 -noout -pubkey -in "$CDN_CERT" | openssl sha256)" != \
        "$(openssl pkey -pubout -in "$CDN_KEY" | openssl sha256)" ]]; then
    warn "The private key does not belong to this certificate." "私钥与证书不匹配。"
    return 1
  fi
  local base="${CDN_HOST#*.}"
  if ! openssl x509 -noout -ext subjectAltName -in "$CDN_CERT" 2>/dev/null \
       | grep -Eq "DNS:($CDN_HOST|\*\.$base)(,|$)"; then
    warn "The certificate does not list $CDN_HOST; Cloudflare will reject it in Full (strict) mode." \
         "证书中不包含 $CDN_HOST，Cloudflare 在完全（严格）模式下会拒绝它。"
    confirm "Use it anyway?" "仍然使用？" n || return 1
  fi
  say "Origin certificate OK." "源服务器证书有效。"
}

ask_origin_cert() {
  echo
  say "Cloudflare origin certificate for $CDN_HOST" "$CDN_HOST 的 Cloudflare 源服务器证书"
  echo "    Cloudflare: SSL/TLS > Origin Server > Create Certificate (ECC, 15 years)"
  echo "    1. Paste it here (recommended) / 直接粘贴（推荐）"
  echo "    2. Read it from files on this server / 从服务器上的文件读取"
  echo "    3. Skip: self-signed, set Cloudflare SSL mode to Full / 跳过：使用自签名证书，Cloudflare SSL 模式设为完全"
  local c
  while true; do
    read -rp "  Choose / 请选择 [1]: " c || c=3
    case "${c:-1}" in
      1)
        CDN_CERT="$TMPD/origin.pem" CDN_KEY="$TMPD/origin.key"
        say "Paste the Origin Certificate (ends with -----END CERTIFICATE-----):" "粘贴源服务器证书（以 -----END CERTIFICATE----- 结尾）："
        read_pem "$CDN_CERT" 'END CERTIFICATE'
        say "Paste the Private Key (ends with -----END PRIVATE KEY-----):" "粘贴私钥（以 -----END PRIVATE KEY----- 结尾）："
        read_pem "$CDN_KEY" 'END .*PRIVATE KEY'
        check_origin_cert && return
        ;;
      2)
        ask CDN_CERT "Certificate file" "证书文件" "" '^/.+'
        ask CDN_KEY "Private key file" "私钥文件" "" '^/.+'
        [[ -f "$CDN_CERT" && -f "$CDN_KEY" ]] && check_origin_cert && return
        warn "Files not found or invalid." "文件不存在或无效。"
        ;;
      3)
        CDN_CERT="" CDN_KEY=""
        warn "Remember: Cloudflare SSL/TLS mode must be Full (not strict)." "注意：Cloudflare SSL/TLS 模式须设为完全（非严格）。"
        return
        ;;
    esac
  done
}

# ================================================================ interactive wizard

STEP_TOTAL=11
step() {
  printf '\n\033[1;36m━━━ Step %s of %s · %s\033[0m\n' "$1" "$STEP_TOTAL" "$2"
  printf '\033[1;36m━━━ 第 %s 步，共 %s 步 · %s\033[0m\n\n' "$1" "$STEP_TOTAL" "$3"
}

pause() { [[ $ASSUME_YES -eq 1 ]] || read -rp "  Press Enter to continue / 按回车继续..." _ || true; }

# Checks that need no answers: run before asking anything, so a server that
# cannot work is reported up front instead of halfway through.
preflight() {
  local arch mem disk virt port proto who
  arch="$(dpkg --print-architecture 2>/dev/null || uname -m)"
  case "$arch" in
    amd64|arm64|x86_64|aarch64) ;;
    *) die "Unsupported CPU architecture $arch (need amd64 or arm64)." "不支持的 CPU 架构 $arch（需要 amd64 或 arm64）。" ;;
  esac
  mem="$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo)"
  (( mem >= 400 )) || die "This server has ${mem} MB of memory; veil needs at least 512 MB." \
                          "本服务器内存为 ${mem} MB，veil 至少需要 512 MB。"
  disk="$(df -Pm / | awk 'NR==2 {print $4}')"
  (( disk >= 1500 )) || die "Only ${disk} MB of free disk space; veil needs 1.5 GB." \
                            "剩余磁盘空间仅 ${disk} MB，veil 需要 1.5 GB。"
  virt="$(systemd-detect-virt 2>/dev/null || true)"
  case "$virt" in
    openvz|lxc|lxc-libvirt)
      warn "This is a $virt container: BBR and some network features may be unavailable. A KVM VPS is recommended." \
           "这是 $virt 容器：可能无法使用 BBR 和部分网络功能。推荐使用 KVM 类型的 VPS。" ;;
  esac
  # Another web server or proxy on the ports veil needs is the most common
  # reason a first install fails.
  for port in tcp:80 tcp:443 udp:443; do
    proto="${port%%:*}"
    who="$(ss -Hlnp -A "$proto" "sport = :${port#*:}" 2>/dev/null \
           | grep -o 'users:(("[^"]*"' | cut -d'"' -f2 | sort -u | grep -vxE 'caddy|sing-box' | head -1)" || true
    [[ -z "$who" ]] || die "Port ${port#*:}/${proto^^} is already used by '$who'. veil needs it. Stop it first, e.g.: systemctl disable --now $who" \
                           "端口 ${port#*:}/${proto^^} 已被 '$who' 占用，veil 需要它。请先停止，例如：systemctl disable --now $who"
  done
  curl -fsS --max-time 10 -o /dev/null https://deb.debian.org/ 2>/dev/null \
    || warn "Cannot reach the internet over HTTPS; the installation will probably fail." \
            "无法通过 HTTPS 访问互联网，安装很可能会失败。"
  detect_public_ip
  [[ -n "$PUBLIC_IP" ]] || die "Could not find this server's public IPv4 address. veil needs a VPS with its own public IPv4 (not NAT)." \
                               "无法获取本服务器的公网 IPv4 地址。veil 需要拥有独立公网 IPv4 的 VPS（不支持 NAT）。"
}

wizard_intro() {
  cat <<'EOF'

  ════════════════════════════════════════════════════════════════════════
    veil - personal stealth proxy / 个人隐蔽代理
    VLESS+REALITY · Hysteria2 · Cloudflare CDN fallback
  ════════════════════════════════════════════════════════════════════════
EOF
  step 1 "Before you start" "开始之前"
  cat <<EOF
  This wizard sets up everything and checks each step with you. It takes
  about 15 minutes. Nothing changes on this server until step 7, and you can
  press Ctrl+C at any time and simply run the installer again later.
  本向导会完成全部设置，并和你一起检查每一步，大约需要 15 分钟。第 7 步之前
  不会修改服务器；随时可以按 Ctrl+C 退出，之后重新运行安装脚本即可。

  You need / 你需要准备：
    • a Cloudflare account (free): https://dash.cloudflare.com/sign-up
      一个 Cloudflare 账号（免费）
    • one domain on Cloudflare showing "Active" - two unrelated domains are best:
      the second one carries the backup route through Cloudflare's network
      一个已在 Cloudflare 生效（Active）的域名——最好是两个互不相关的域名：
      第二个用于经 Cloudflare 网络的备用线路
    • the Cloudflare dashboard open in your browser, next to this window
      在浏览器中打开 Cloudflare 控制台，放在本窗口旁边

  This server's public IP / 本服务器公网 IP:  $PUBLIC_IP

EOF
  confirm "Ready?" "准备好了吗？" y || {
    echo "  Run this installer again when you are ready. / 准备好后重新运行安装脚本即可。"
    exit 0
  }
}

wizard_site() {
  step 2 "The site name (direct routes)" "站点域名（直连线路）"
  cat <<EOF
  Your proxy hides behind a small real website on this server. Its name is
  what visitors and network filters see, so it must point straight at this
  server (Cloudflare's "grey cloud"). Pick an ordinary name such as
  www.<domain>; avoid words like proxy, vpn or ss.
  你的代理隐藏在本服务器上一个真实的小网站后面。外界看到的就是这个名字，所以它
  必须直接指向本服务器（Cloudflare 的"灰色云朵"）。用普通的名字，例如 www.<域名>，
  避免使用 proxy、vpn、ss 等字样。

  In Cloudflare, open your first domain > DNS > Records > Add record:
  在 Cloudflare 中打开第一个域名 > DNS > 记录 > 添加记录：

      Type / 类型    Name / 名称   IPv4 address / IPv4 地址   Proxy status / 代理状态
      A              www           $PUBLIC_IP                 DNS only (grey) / 仅 DNS（灰色）

EOF
  ask SITE_HOST "Site name, e.g. www.example.com" "站点域名，例如 www.example.com" "" "$HOST_RE"
  SITE_HOST="${SITE_HOST,,}"
  check_site_dns
}

wizard_cdn() {
  step 3 "Backup route through Cloudflare (recommended)" "经 Cloudflare 的备用线路（推荐）"
  cat <<'EOF'
  If your network ever blocks this server's IP, this route still works: your
  devices connect to Cloudflare, and Cloudflare forwards to this server. It also
  carries your subscription updates. Use a SECOND domain unrelated to the first,
  so nobody can link the two names together.
  如果你的网络封锁了本服务器的 IP，这条线路依然可用：设备连接 Cloudflare，再由
  Cloudflare 转发到本服务器。订阅更新也走这条线路。请使用与第一个域名无关的第二个
  域名，这样别人无法把两个名字联系起来。

EOF
  if ! confirm "Set up the Cloudflare backup route?" "设置 Cloudflare 备用线路？" y; then
    CDN_HOST=""
    return
  fi
  cat <<EOF

  In Cloudflare, open your SECOND domain and do these four things:
  在 Cloudflare 中打开第二个域名，完成以下四项：

  a) DNS > Records > Add record / DNS > 记录 > 添加记录：
       A    static    $PUBLIC_IP    Proxied (orange) / 已代理（橙色）
  b) SSL/TLS > Overview > Configure: Full (strict) > Save
     SSL/TLS > 概述 > 配置：完全（严格）> 保存
     (Cloudflare checks this server's certificate on every connection.)
     （Cloudflare 每次连接都会校验本服务器的证书。）
  c) SSL/TLS > Origin Server > Create Certificate > keep defaults > Create.
     Leave that page open: you paste its two boxes here in a moment.
     SSL/TLS > 源服务器 > 创建证书 > 保持默认 > 创建。保持页面打开，稍后把两个框的内容粘贴到这里。
  d) SSL/TLS > Origin Server > Authenticated Origin Pulls: On
     SSL/TLS > 源服务器 > Authenticated Origin Pulls：开启
     (Cloudflare then proves itself with its own certificate, and this server
     refuses everyone else on this name. veil checks it after installing.)
     （之后 Cloudflare 会用自己的证书证明身份，本服务器对这个名字拒绝其他所有人。安装后 veil 会检查。）

EOF
  while true; do
    ask CDN_HOST "CDN name, e.g. static.example.net" "CDN 域名，例如 static.example.net" "" "$HOST_RE"
    CDN_HOST="${CDN_HOST,,}"
    [[ "$CDN_HOST" != "$SITE_HOST" ]] && break
    warn "The CDN name must differ from the site name." "CDN 域名必须与站点域名不同。"
  done
  [[ "${CDN_HOST#*.}" != "${SITE_HOST#*.}" ]] || warn \
    "Both names are on the same domain; anyone who sees both can link the CDN route to this server. A second, unrelated domain is safer." \
    "两个名字在同一个域名下；同时看到两者的人可以把 CDN 线路和本服务器联系起来。使用另一个无关的域名更安全。"
  check_cdn_dns
  confirm "Is SSL/TLS set to Full (strict) for this domain (step b)?" "该域名的 SSL/TLS 是否已设为完全（严格）（第 b 项）？" y \
    || warn "Set it before using the CDN route; veil checks it after installing." "使用 CDN 线路前请先设置；安装后 veil 会检查。"
  ask_origin_cert
}

wizard_email() {
  step 4 "Email for certificates" "证书邮箱"
  cat <<'EOF'
  Let's Encrypt issues the site's certificate for free and renews it every
  two months by itself. It emails this address only if renewal ever fails.
  Let's Encrypt 免费为网站签发证书，并每两个月自动续期。只有续期失败时才会发邮件到这个地址。

EOF
  ask EMAIL "Email" "邮箱" "" "$EMAIL_RE"
}

wizard_options() {
  step 5 "Options" "选项"
  cat <<'EOF'
  Hysteria2 is a fast route over UDP (QUIC), good for video. Some networks slow
  UDP down in the evening; your apps then switch to another route by themselves.
  Hysteria2 是基于 UDP（QUIC）的快速线路，适合看视频。有些网络晚上会限制 UDP，
  这时应用会自动切换到其他线路。

EOF
  confirm "Enable Hysteria2?" "启用 Hysteria2？" y || NO_HY2=1
  echo
  cat <<'EOF'
  Installing the pending system updates now gives the server the latest security
  fixes before it goes online (a few minutes; it may restart once at the end).
  现在安装待处理的系统更新，让服务器在上线前获得最新的安全修复（需几分钟，结束时可能重启一次）。

EOF
  if confirm "Install system updates first?" "先安装系统更新？" y; then UPGRADE=1; fi
}

wizard_alerts() {
  step 6 "Alerts on your phone" "手机故障提醒"
  cat <<'EOF'
  The server looks after itself every night: certificates, credential changes,
  updates, backups and a health check. If it finds a problem, it can tell you
  on your phone. Without this, nobody hears about it.
  服务器每晚自动维护：证书、凭据更换、更新、备份和健康检查。发现问题时可以通知你的手机。
  不设置的话，没人会知道出了问题。

    1. ntfy - free app for iPhone and Android (recommended) / 免费应用，支持 iPhone 和安卓（推荐）
    2. Bark - free iPhone app that also works inside China / 免费 iPhone 应用，国内也能用
    3. Not now (set it up later: veil > Settings) / 暂不设置（之后可在 veil > 设置 中设置）

EOF
  local c topic url
  read -rp "  Choose / 请选择 [1]: " c || c=3
  case "${c:-1}" in
    1)
      topic="veil-$(od -An -N6 -tx1 /dev/urandom | tr -d ' \n')"
      NOTIFY_URL="https://ntfy.sh/$topic"
      cat <<EOF

    1. Install "ntfy" from the App Store or Google Play and open it.
       从 App Store 或 Google Play 安装 "ntfy" 并打开。
    2. Tap + and subscribe to this topic (a random name nobody can guess):
       点 +，订阅这个主题（别人猜不到的随机名字）：

           $topic

    A test alert is sent after installing. / 安装完成后会发送一条测试提醒。
EOF
      pause ;;
    2)
      while true; do
        read -rp "  Bark URL, e.g. https://api.day.app/AbCd1234 / Bark 地址: " url || url=""
        url="${url%/}"
        [[ -z "$url" ]] && break
        if [[ "$url" =~ ^https://api\.day\.app/[A-Za-z0-9]+$ ]]; then NOTIFY_URL="$url"; break; fi
        echo "    That does not look like a Bark URL / 这不像 Bark 地址"
      done ;;
  esac
}

wizard_review() {
  step 7 "Review and install" "确认并安装"
  cat <<EOF
    Site name / 站点域名      : $SITE_HOST
    CDN name  / CDN 域名      : ${CDN_HOST:-(none / 无)}${CDN_HOST:+  (certificate / 证书: ${CDN_CERT:+Cloudflare origin}${CDN_CERT:-self-signed})}
    Email     / 邮箱          : $EMAIL
    Hysteria2                 : $([[ $NO_HY2 -eq 1 ]] && echo "off / 关" || echo "on / 开")
    System updates / 系统更新 : $([[ $UPGRADE -eq 1 ]] && echo "yes / 是" || echo "no / 否")
    Alerts / 故障提醒         : ${NOTIFY_URL:-(off / 未开启)}

  Installing also switches on, without asking: BBR, time sync, automatic security
  updates (with a restart at 22:00 UTC when one needs it), a firewall against SSH
  password guessing (Fail2ban), blocking of BitTorrent and spam through the proxy,
  nightly backups and credential rotation every 30 days.
  安装时还会自动开启：BBR、时间同步、自动安全更新（需要时在 UTC 22:00 重启）、
  防 SSH 密码猜测（Fail2ban）、禁止通过代理使用 BT 和发送垃圾邮件、每晚备份、每 30 天更换凭据。

EOF
  confirm "Start the installation?" "开始安装？" y || exit 0
}

wizard() {
  wizard_intro
  wizard_site
  wizard_cdn
  wizard_email
  wizard_options
  wizard_alerts
  wizard_review
  INTERACTIVE=1
}

# ================================================================ after installing

# Re-run one doctor section until it passes, or the user skips it.
verify_loop() {
  while ! veil doctor --only "$@"; do
    echo "  Fix the items marked XX above (Cloudflare changes take a minute)."
    echo "  请修复上面标记 XX 的项目（Cloudflare 的修改需要一分钟左右生效）。"
    wait_choice || return 0
  done
}

post_verify() {
  step 8 "Check everything" "全面检查"
  echo "  Checking the server, the site name and the CDN route... / 正在检查服务器、站点域名和 CDN 线路……"
  verify_loop system site
  if [[ -n "$(state_get "['cdn']['host']")" ]]; then
    verify_loop cdn
    # Authenticated Origin Pulls is a warning in doctor; insist a little here.
    until [[ "$(veil origin-pull 2>&1)" == on* ]]; do
      cat <<'EOF'

  Authenticated Origin Pulls is not on yet. In Cloudflare, open the CDN name's
  domain > SSL/TLS > Origin Server > Authenticated Origin Pulls: On.
  Authenticated Origin Pulls 尚未开启。在 Cloudflare 中打开 CDN 域名所在的域名 >
  SSL/TLS > 源服务器 > Authenticated Origin Pulls：开启。
EOF
      wait_choice || break
    done
  fi
  if [[ -n "$NOTIFY_URL" ]]; then
    veil set notify_url "$NOTIFY_URL" >/dev/null
    while true; do
      veil alert-test || true
      confirm "Did the test alert arrive on your phone?" "手机收到测试提醒了吗？" y && break
      wait_choice || { veil set notify_url "" >/dev/null; warn "Alerts turned off; set them up later: veil > Settings" "提醒已关闭，之后可在 veil > 设置 中设置"; break; }
    done
  fi
  veil doctor --only upkeep || true
}

post_firewall() {
  local hop="" ports
  [[ "$(state_get "['hy2']['enabled']")" != True ]] || hop=", UDP 443, UDP $(state_get "['hy2']['hop']")"
  ports="TCP 22, TCP 80, TCP 443$hop"
  step 9 "Provider firewall" "服务商防火墙"
  cat <<EOF
  Some providers have their own firewall ("Security group", "Firewall") in their
  web panel. If yours does, allow exactly these incoming ports, and nothing else:
  有些服务商在网页面板中有自己的防火墙（"安全组"、"防火墙"）。如果有，请只放行以下入站端口：

      $ports

  TCP 22 is SSH, TCP 80 renews the certificate, TCP/UDP 443 and the UDP range
  are the proxy routes. If your provider has no such panel, nothing to do.
  TCP 22 用于 SSH，TCP 80 用于续期证书，TCP/UDP 443 和 UDP 端口范围是代理线路。没有这种面板则无需操作。

EOF
  pause
}

post_devices() {
  step 10 "Connect your devices" "连接你的设备"
  veil links || true
  cat <<'EOF'

  Each device has its own subscription URL. Install the app yourself, then:
  每台设备都有自己的订阅链接。自行安装应用后：

    Windows / Mac   Clash Verge Rev: Profiles > paste the URL > Import > select it,
                    then Settings > System Proxy (or TUN Mode) on.
                    订阅 > 粘贴链接 > 导入 > 选中，然后 设置 > 系统代理（或 TUN 模式）开启。
    Android         FlClash: Profiles > + > URL, or scan the device's QR code.
                    配置 > + > URL，或扫描该设备的二维码。
    iPhone / iPad   Shadowrocket: scan the 'shadowrocket' QR code, then
                    Settings > Subscription > Auto update ON (needed: credentials change monthly).
                    扫描 'shadowrocket' 二维码，然后 设置 > 订阅 > 自动更新 开启（凭据每月更换，必须开启）。
    Router          OpenClash: Config Subscribe > Add > the 'router' URL, auto update on.
                    配置订阅 > 添加 > 'router' 链接，开启自动更新。

  More devices later: veil > Add a device. / 以后添加设备：veil > 添加设备。

EOF
  local name
  while true; do
    read -rp "  Show a QR code? Type a name from the list above, or Enter to go on / 显示二维码？输入上面的名字，回车继续: " name || name=""
    [[ -n "$name" ]] || break
    veil links --qr "$name" | sed -n '/^QR for/,$p' || true
  done
}

post_backup() {
  step 11 "Keep a backup on your computer" "在电脑上保存备份"
  cat <<'EOF'
  A backup holds your keys and settings. With it, moving to a new server takes
  15 minutes and your devices keep working without changes. The server keeps
  nightly copies itself, but if the server is lost they are lost too, so keep
  one on your own computer.
  备份包含你的密钥和设置。有了它，迁移到新服务器只需 15 分钟，设备无需任何改动。
  服务器每晚会自动备份，但服务器丢失时这些备份也会丢失，所以请在自己的电脑上保存一份。

EOF
  veil backup || true
  pause
}

finish() {
  cat <<'EOF'

  ════════════════════════════════════════════════════════════════════════
    veil is ready. / veil 已就绪。

    veil            management menu / 管理菜单
    veil doctor     check everything, with fixes / 全面检查并给出修复方法
    veil links      subscription URLs / 订阅链接
    veil update     update veil (keys and links stay) / 更新 veil（密钥和链接不变）

    Everything else runs by itself every night. / 其他一切每晚自动运行。
  ════════════════════════════════════════════════════════════════════════
EOF
}

installed_menu() {
  local site c
  site="$(state_get "['site_host']")"
  cat <<EOF

  veil is already installed on this server ($site). Your keys and links are kept
  whatever you choose here.
  本服务器已安装 veil（$site）。无论选择哪项，密钥和链接都会保留。

    1. Update or repair veil with this installer / 用本安装脚本更新或修复 veil
    2. Check everything (doctor) / 全面检查
    3. Open the management menu / 打开管理菜单
    4. Uninstall veil / 卸载 veil
    0. Exit / 退出

EOF
  read -rp "  Choose / 请选择: " c || c=0
  case "$c" in
    1) MODE=update ;;
    2) veil doctor || true; exit 0 ;;
    3) cleanup; exec veil ;;
    4) MODE=uninstall ;;
    *) exit 0 ;;
  esac
}

# ================================================================ installation

# Many VPS images are built on a virtio disk (/dev/vda) and then deployed on
# another (/dev/sda), leaving GRUB's install target pointing at a disk that does
# not exist. A non-interactive grub-pc upgrade then fails and leaves dpkg
# half-configured. Point it at the disk that holds /boot, if that is unambiguous.
fix_grub_devices() {
  dpkg -s grub-pc >/dev/null 2>&1 || return 0
  [[ ! -d /sys/firmware/efi ]] || return 0
  local cur d ok=1 src disk id=""
  cur="$(debconf-show grub-pc 2>/dev/null | awk -F': ' '$1 ~ /grub-pc\/install_devices$/ {print $2}')"
  for d in ${cur//,/ }; do [[ -e "$d" ]] || ok=0; done
  [[ -z "$cur" || $ok -eq 0 ]] || return 0
  src="$(findmnt -no SOURCE /boot 2>/dev/null || findmnt -no SOURCE /)"
  disk="$(lsblk -no PKNAME "$src" 2>/dev/null | head -1)"
  [[ -n "$disk" && "$(lsblk -dno TYPE "/dev/$disk" 2>/dev/null)" == disk ]] || {
    warn "GRUB is set to install to '${cur:-nothing}' and the boot disk is unclear; fix it with: dpkg-reconfigure grub-pc" \
         "GRUB 安装目标无效，且无法确定启动盘，请运行 dpkg-reconfigure grub-pc 修复。"
    return 0
  }
  for d in /dev/disk/by-id/*; do
    [[ "$d" != *-part* && "$(readlink -f "$d")" == "/dev/$disk" ]] && { id="$d"; break; }
  done
  say "GRUB was set to install to '${cur:-nothing}'; using the boot disk ${id:-/dev/$disk} instead." \
      "GRUB 安装目标 '${cur:-无}' 不存在，已改为启动盘 ${id:-/dev/$disk}。"
  echo "grub-pc grub-pc/install_devices multiselect ${id:-/dev/$disk}" | debconf-set-selections
}

# Fix known problems left by the image or by an interrupted earlier run.
repair_dpkg() {
  export DEBIAN_FRONTEND=noninteractive
  fix_grub_devices
  dpkg --configure -a
}

# Ban IPs that keep failing SSH logins. Password login stays available (some
# providers never set up keys), but a scanner loses its source IP for an hour
# after 5 failures in 10 minutes, longer each time it comes back. Debian 12
# logs only to the journal, so the systemd backend is required.
setup_fail2ban() {
  apt-get install -y -q fail2ban python3-systemd >/dev/null
  cat > /etc/fail2ban/jail.d/90-veil.conf <<'EOF'
# Written by veil.
[DEFAULT]
backend = systemd
banaction = nftables-allports
banaction_allports = nftables-allports
ignoreip = 127.0.0.1/8 ::1
bantime = 1h
bantime.increment = true
bantime.maxtime = 1w
findtime = 10m
maxretry = 5

[sshd]
enabled = true
mode = aggressive
EOF
  systemctl enable fail2ban >/dev/null 2>&1
  systemctl restart fail2ban
  sleep 2
  if fail2ban-client status sshd >/dev/null 2>&1; then
    say "Fail2ban is on: 5 failed SSH logins in 10 minutes ban that IP." \
        "Fail2ban 已开启：10 分钟内 SSH 登录失败 5 次即封禁该 IP。"
  else
    warn "Fail2ban did not start; check: journalctl -u fail2ban" "Fail2ban 未能启动，请检查：journalctl -u fail2ban"
  fi
}

# A small swap file keeps a 1-2 GB server from running out of memory during
# large upgrades. Skipped in containers, when swap exists or disk is short.
setup_swap() {
  [[ -z "$(swapon --noheadings 2>/dev/null)" && ! -e /swapfile ]] || return 0
  [[ "$(systemd-detect-virt -c 2>/dev/null || true)" =~ ^(none|)$ ]] || return 0
  (( $(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo) < 4096 )) || return 0
  (( $(df -Pm / | awk 'NR==2 {print $4}') > 3072 )) || return 0
  fallocate -l 512M /swapfile 2>/dev/null || dd if=/dev/zero of=/swapfile bs=1M count=512 status=none
  chmod 600 /swapfile
  mkswap /swapfile >/dev/null && swapon /swapfile || { rm -f /swapfile; return 0; }
  echo '/swapfile none swap sw 0 0 # veil' >> /etc/fstab
  say "Added a 512 MB swap file." "已添加 512 MB 交换文件。"
}

system_upgrade() {
  say "Installing system updates..." "正在安装系统更新……"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -q
  apt-get -y -q -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold full-upgrade
}

install_core() {
  export DEBIAN_FRONTEND=noninteractive
  say "Installing base packages..." "正在安装基础软件包……"
  apt-get update -q
  apt-get install -y -q curl ca-certificates gnupg openssl iproute2 nftables python3 qrencode \
    unattended-upgrades >/dev/null

  install -d -m 755 /etc/apt/keyrings
  if [[ ! -f /etc/apt/sources.list.d/sagernet.sources ]]; then
    say "Adding the sing-box repository..." "正在添加 sing-box 软件源……"
    curl -fsSL https://sing-box.app/gpg.key -o /etc/apt/keyrings/sagernet.asc
    chmod a+r /etc/apt/keyrings/sagernet.asc
    cat > /etc/apt/sources.list.d/sagernet.sources <<'EOF'
Types: deb
URIs: https://deb.sagernet.org/
Suites: *
Components: *
Enabled: yes
Signed-By: /etc/apt/keyrings/sagernet.asc
EOF
  fi
  if [[ ! -f /etc/apt/sources.list.d/caddy-stable.list ]]; then
    say "Adding the Caddy repository..." "正在添加 Caddy 软件源……"
    curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/gpg.key \
      | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt \
      > /etc/apt/sources.list.d/caddy-stable.list
  fi
  apt-get update -q
  apt-get install -y -q sing-box caddy >/dev/null
  # veil runs its own hardened unit; the packaged one would fight over port 443.
  systemctl disable --now sing-box.service >/dev/null 2>&1 || true
  local singbox_bin
  singbox_bin="$(command -v sing-box)"

  id veil >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin veil
  install -d -m 750 -o root -g veil /etc/veil /etc/veil/tls
  install -d -m 755 /var/lib/veil /var/lib/veil/www
  install -d -m 750 -o root -g caddy /var/lib/veil/sub

  say "Installing veil to /opt/veil..." "正在安装 veil 到 /opt/veil……"
  # Remember where veil came from, for `veil update`: a git checkout is updated
  # with git pull, anything else from the latest GitHub release.
  local source
  source="$(cat /opt/veil/SOURCE 2>/dev/null || echo release)"
  if [[ -d "$HERE/../.git" ]]; then
    source="git $(cd "$HERE/.." && pwd)"
  elif [[ "$HERE" != /opt/veil ]]; then
    source=release
  fi
  rm -rf /opt/veil.new
  install -d /opt/veil.new
  cp -r "$SRC/veil" "$SRC/decoy" "$SRC/systemd" /opt/veil.new/
  install -m 700 "$SELF" /opt/veil.new/veil-install.sh
  echo "$source" > /opt/veil.new/SOURCE
  find /opt/veil.new -name __pycache__ -prune -exec rm -rf {} +
  rm -rf /opt/veil && mv /opt/veil.new /opt/veil
  cat > /usr/local/bin/veil <<'EOF'
#!/bin/sh
PYTHONPATH=/opt/veil exec python3 -m veil "$@"
EOF
  chmod 755 /usr/local/bin/veil

  local unit
  for unit in veil-nft.service veil-maint.service veil-maint.timer; do
    install -m 644 "$SRC/systemd/$unit" "/etc/systemd/system/$unit"
  done
  sed "s#@SINGBOX@#$singbox_bin#" "$SRC/systemd/veil-singbox.service" > /etc/systemd/system/veil-singbox.service
  systemctl daemon-reload

  say "Tuning the system: BBR, UDP buffers, time sync, security updates..." "正在优化系统：BBR、UDP 缓冲区、时间同步、安全更新……"
  cat > /etc/sysctl.d/90-veil.conf <<'EOF'
net.core.default_qdisc = fq
net.ipv4.tcp_congestion_control = bbr
net.core.rmem_max = 16777216
net.core.wmem_max = 16777216
vm.swappiness = 10
EOF
  # BBR ships with every Debian/Ubuntu kernel; load it now and at every boot.
  echo tcp_bbr > /etc/modules-load.d/90-veil.conf
  modprobe tcp_bbr 2>/dev/null || true
  sysctl --system >/dev/null
  if [[ "$(sysctl -n net.ipv4.tcp_congestion_control)" == bbr ]]; then
    say "BBR congestion control is on." "BBR 拥塞控制已开启。"
  else
    warn "This kernel does not offer BBR (common on OpenVZ/LXC containers); veil still works, a bit slower on lossy links." \
         "当前内核不支持 BBR（OpenVZ/LXC 容器常见），veil 仍可使用，但丢包时速度会慢一些。"
  fi
  # REALITY rejects clients whose clock differs by more than 2 minutes, and some
  # cloud images ship without any time-sync daemon.
  local have_ntp=0 pkg
  for pkg in chrony ntp ntpsec openntpd systemd-timesyncd; do
    dpkg -s "$pkg" >/dev/null 2>&1 && have_ntp=1
  done
  [[ $have_ntp -eq 1 ]] || apt-get install -y -q systemd-timesyncd >/dev/null
  timedatectl set-ntp true 2>/dev/null || warn "Could not enable NTP; keep the clock accurate." "无法开启 NTP，请保持时钟准确。"
  # systemd-resolved answers LLMNR on port 5355 from the internet by default:
  # an unusual open port that makes the server stand out. Turn it off.
  if systemctl is-active --quiet systemd-resolved; then
    install -d /etc/systemd/resolved.conf.d
    printf '[Resolve]\nLLMNR=no\nMulticastDNS=no\n' > /etc/systemd/resolved.conf.d/90-veil.conf
    systemctl restart systemd-resolved
  fi
  cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF
  # Kernel and libc fixes only take effect after a reboot. Reboot when an update
  # asks for it, at 22:00 UTC: after veil's maintenance window (19:00-21:00 UTC)
  # and before the day starts in East Asia. The time is in the server's zone.
  cat > /etc/apt/apt.conf.d/52veil-reboot <<EOF
// Written by veil.
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-WithUsers "true";
Unattended-Upgrade::Automatic-Reboot-Time "$(date -d '22:00 UTC' +%H:%M)";
EOF

  if [[ -n "$RESTORE" ]]; then
    say "Restoring $RESTORE..." "正在恢复 $RESTORE……"
    veil restore "$RESTORE"
    [[ -n "$(ls -A /var/lib/veil/www)" ]] || cp -r /opt/veil/decoy/. /var/lib/veil/www/
  elif [[ $FRESH -eq 1 ]]; then
    say "Generating keys..." "正在生成密钥……"
    local args=(--site-host "$SITE_HOST" --email "$EMAIL")
    [[ -z "$CDN_HOST" ]] || args+=(--cdn-host "$CDN_HOST")
    [[ $NO_HY2 -eq 0 ]] || args+=(--no-hy2)
    veil init "${args[@]}"
  fi
  if [[ -n "$CDN_CERT" ]]; then
    veil cdn-cert --cert "$CDN_CERT" --key "$CDN_KEY" --no-apply
  fi

  say "Starting services (waiting for the Let's Encrypt certificate)..." "正在启动服务（等待 Let's Encrypt 证书）……"
  veil apply --first-run
  systemctl enable --now veil-maint.timer >/dev/null
  setup_fail2ban
  setup_swap
  # Require Cloudflare's client certificate on the CDN host once Cloudflare
  # sends it; until then this prints how to switch it on.
  [[ -z "$(state_get "['cdn']['host']")" ]] || veil origin-pull || true
}

show_result() {
  local hop=""
  [[ "$(state_get "['hy2']['enabled']")" != True ]] || hop=", UDP 443, UDP $(state_get "['hy2']['hop']")"
  if [[ "$MODE" == update ]]; then
    veil doctor || true
    say "veil $(veil --version | awk '{print $2}') is installed; keys and links are unchanged." \
        "veil 已更新；密钥和链接保持不变。"
    return
  fi
  echo
  say "veil is ready." "veil 已就绪。"
  echo
  veil links || true
  cat <<EOF

  ─────────────────────────────────────────────────────────────────
  Firewall: if your provider has a firewall panel, allow
  防火墙：如果服务商有防火墙面板，请放行
      TCP 80, TCP 443$hop

  Manage everything with:  veil     (QR codes, devices, links, backups...)
  之后输入 veil 即可管理一切（二维码、设备、订阅链接、备份……）
  ─────────────────────────────────────────────────────────────────
EOF
}

maybe_reboot() {
  [[ -f /var/run/reboot-required ]] || return 0
  echo
  warn "A system update needs a reboot to take effect (veil starts again by itself)." \
       "系统更新需要重启才能生效（veil 会自动重新启动）。"
  if [[ $ASSUME_YES -eq 0 ]] && confirm "Reboot now?" "现在重启？" y; then
    say "Rebooting... reconnect in a minute and type: veil" "正在重启……一分钟后重新连接并输入：veil"
    systemctl reboot
  fi
}

uninstall() {
  confirm "Remove veil from this server?" "从本服务器卸载 veil？" n || exit 0
  if command -v veil >/dev/null && [[ -f /etc/veil/state.json ]] \
     && confirm "Make a backup first (keys, so you can restore later)?" "先备份（保留密钥以便日后恢复）？" y; then
    veil backup || true
  fi
  systemctl disable --now veil-maint.timer veil-singbox.service veil-nft.service >/dev/null 2>&1 || true
  rm -f /etc/systemd/system/veil-singbox.service /etc/systemd/system/veil-nft.service \
        /etc/systemd/system/veil-maint.service /etc/systemd/system/veil-maint.timer
  systemctl daemon-reload
  if grep -q '^/swapfile none swap sw 0 0 # veil$' /etc/fstab; then
    swapoff /swapfile 2>/dev/null || true
    sed -i '\|^/swapfile none swap sw 0 0 # veil$|d' /etc/fstab
    rm -f /swapfile
  fi
  rm -rf /etc/veil /var/lib/veil /usr/local/bin/veil /etc/sysctl.d/90-veil.conf /etc/modules-load.d/90-veil.conf /etc/fail2ban/jail.d/90-veil.conf \
         /etc/systemd/resolved.conf.d/90-veil.conf /etc/caddy/veil-cdn.crt /etc/caddy/veil-cdn.key \
         /etc/caddy/cloudflare-origin-pull-ca.pem /etc/apt/apt.conf.d/52veil-reboot
  systemctl restart fail2ban >/dev/null 2>&1 || true
  if confirm "Also remove the sing-box, Caddy and Fail2ban packages?" "同时删除 sing-box、Caddy 和 Fail2ban 软件包？" y; then
    systemctl disable --now caddy >/dev/null 2>&1 || true
    apt-get purge -y -q sing-box caddy fail2ban >/dev/null || true
    rm -f /etc/apt/sources.list.d/sagernet.sources /etc/apt/sources.list.d/caddy-stable.list \
          /etc/apt/keyrings/sagernet.asc /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  fi
  id veil >/dev/null 2>&1 && userdel veil || true
  rm -rf /opt/veil
  say "veil has been removed." "veil 已卸载。"
}

# ================================================================ main

main() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --site-host)    SITE_HOST="$2"; shift 2 ;;
      --cdn-host)     CDN_HOST="$2";  shift 2 ;;
      --email)        EMAIL="$2";     shift 2 ;;
      --cdn-cert)     CDN_CERT="$2";  shift 2 ;;
      --cdn-key)      CDN_KEY="$2";   shift 2 ;;
      --restore)      RESTORE="$2";   shift 2 ;;
      --no-hy2)       NO_HY2=1;       shift ;;
      --upgrade)      UPGRADE=1;      shift ;;
      --notify)       NOTIFY_URL="$2"; shift 2 ;;
      --yes|-y)       ASSUME_YES=1;   shift ;;
      --update)       MODE=update;    shift ;;
      --uninstall)    MODE=uninstall; shift ;;
      --extract-only) MODE=extract; EXTRACT_TO="$2"; shift 2 ;;
      -h|--help)      usage 0 ;;
      *) warn "Unknown option $1"; usage 1 ;;
    esac
  done
  TMPD="$(mktemp -d)"

  if [[ "$MODE" == extract ]]; then  # for testing the bundle
    locate_source
    mkdir -p "$EXTRACT_TO" && cp -r "$SRC/." "$EXTRACT_TO/"
    say "Extracted to $EXTRACT_TO"
    return 0
  fi

  [[ $EUID -eq 0 ]] || die "Run as root (sudo -i first)." "请以 root 运行（先执行 sudo -i）。"
  [[ -d /run/systemd/system ]] || die "systemd is required." "需要 systemd。"
  . /etc/os-release
  case "${ID:-}" in debian|ubuntu) ;; *) die "Unsupported OS ${ID:-unknown}; use Debian or Ubuntu." "不支持的系统，请使用 Debian 或 Ubuntu。" ;; esac
  # One installer at a time: two runs would fight over apt and the config files.
  exec 9>/run/veil-install.lock
  flock -n 9 || die "Another veil installer is already running." "另一个 veil 安装程序正在运行。"
  [[ -f /etc/veil/state.json ]] && FRESH=0

  [[ -n "$MODE" || -n "$RESTORE" || $FRESH -eq 1 || -n "$SITE_HOST" ]] || installed_menu

  case "$MODE" in
    uninstall) uninstall; return 0 ;;
    update)
      [[ $FRESH -eq 0 ]] || die "veil is not installed yet." "尚未安装 veil。"
      start_log
      locate_source
      repair_dpkg
      [[ $UPGRADE -eq 0 ]] || system_upgrade
      install_core
      stop_log
      show_result
      maybe_reboot
      return 0
      ;;
  esac

  if [[ -n "$RESTORE" ]]; then
    [[ -f "$RESTORE" ]] || die "Backup $RESTORE not found." "找不到备份 $RESTORE。"
    RESTORE="$(readlink -f "$RESTORE")"
  elif [[ $FRESH -eq 0 ]]; then
    warn "veil is already installed; updating it and keeping the existing keys." "已安装 veil，将更新并保留现有密钥。"
  elif [[ -n "$SITE_HOST" ]]; then
    [[ "$SITE_HOST" =~ $HOST_RE && "$EMAIL" =~ $EMAIL_RE ]] || die "--site-host and --email are required." "必须提供 --site-host 和 --email。"
    [[ -z "$CDN_CERT" || -n "$CDN_KEY" ]] || die "--cdn-cert needs --cdn-key." "--cdn-cert 需要同时提供 --cdn-key。"
  else
    preflight
    wizard
  fi
  [[ $FRESH -eq 0 || -n "$RESTORE" || $INTERACTIVE -eq 1 ]] || preflight

  start_log
  locate_source
  repair_dpkg
  [[ $UPGRADE -eq 0 ]] || system_upgrade
  install_core
  stop_log
  if [[ $INTERACTIVE -eq 1 ]]; then
    post_verify
    post_firewall
    post_devices
    post_backup
    finish
  else
    [[ -z "$NOTIFY_URL" ]] || { veil set notify_url "$NOTIFY_URL" && veil alert-test; } || true
    show_result
  fi
  maybe_reboot
}

# Keep a root-only log of the installation phase (not the questions).
start_log() {
  (umask 077 && touch "$LOG")
  chmod 600 "$LOG"
  printf '\n===== veil installer %s =====\n' "$(date -u '+%F %T UTC')" >> "$LOG"
  exec 3>&1 4>&2
  exec > >(tee -a "$LOG") 2>&1
}
stop_log() { exec 1>&3 2>&4 3>&- 4>&-; }

main "$@"
exit $?
