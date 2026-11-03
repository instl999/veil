# 安装参考

[新手指南](guide.md) 介绍了第一次安装的完整过程。本页是参考资料：系统要求、所有
安装方式、安装脚本会修改什么，以及重复运行、更新、恢复和卸载的方式。

## 系统要求

| | |
|---|---|
| 系统 | Debian 11/12 或 Ubuntu 22.04/24.04，使用 systemd |
| CPU | amd64 或 arm64 |
| 内存 / 磁盘 | 512 MB 内存（推荐 1 GB 以上），1.5 GB 可用磁盘 |
| 网络 | 服务器拥有公网 IPv4（不支持 NAT）；推荐 KVM（OpenVZ/LXC 可能无法使用 BBR） |
| 端口 | TCP 80、TCP 443、UDP 443 未被占用（安装脚本会检查，并指出占用端口的程序） |
| 域名 | 一个在 Cloudflare 上的域名用于站点域名；最好再有一个无关的域名用于 CDN 线路 |
| 权限 | root（或 `sudo -i`） |

## 安装方式

### 1. 最新发布版（推荐）

```bash
curl -fsSLO https://github.com/instl999/veil/releases/latest/download/veil-install.sh
bash veil-install.sh
```

`veil-install.sh` 是单个文件：包含安装脚本、`veil` 管理工具、服务单元和伪装网站，
由 CI 从本仓库构建。每个发布版还附带 `veil-install.sh.sha256`：

```bash
curl -fsSLO https://github.com/instl999/veil/releases/latest/download/veil-install.sh.sha256
sha256sum -c veil-install.sh.sha256
```

### 2. 从 git 仓库安装

```bash
apt-get update && apt-get install -y git
git clone https://github.com/instl999/veil.git /root/veil
bash /root/veil/install.sh
```

请保留这个目录：之后 `veil update` 会在其中运行 `git pull` 并重新安装。

### 3. 离线复制

在电脑上构建（`python tools/build.py`），用 `scp` 把 `dist/veil-install.sh` 复制到
服务器后运行。

## 分步引导

不带参数运行时，安装脚本先检查服务器（CPU 架构、内存、磁盘、端口占用、网络、
公网 IP），然后分 11 步引导你：

1. 需要准备的东西；2. 站点域名，显示 DNS 记录并实时检查；3. 可选的 CDN 线路：
DNS 记录（检查）、SSL 模式、源服务器证书（粘贴后检查与私钥、域名是否匹配）、
Authenticated Origin Pulls；4. 邮箱；5. Hysteria2 和系统更新；6. 手机提醒（ntfy 或
Bark）；7. 确认——**在此之前不会修改服务器**；8. 全面检查（`veil doctor`）、
Authenticated Origin Pulls 和测试提醒，每项都会反复检查直到通过或你选择跳过；
9. 服务商防火墙端口；10. 设备链接和二维码；11. 生成备份并给出复制到电脑的命令。

## 非交互安装

```bash
bash veil-install.sh --site-host www.example.com --email you@example.com \
  --cdn-host static.example.net --cdn-cert origin.pem --cdn-key origin.key \
  --notify https://ntfy.sh/your-random-topic --upgrade --yes
```

| 参数 | 含义 |
|---|---|
| `--site-host H` | 站点域名（仅 DNS / 灰色云朵）——必填 |
| `--email E` | Let's Encrypt 联系邮箱——必填 |
| `--cdn-host H` | CDN 域名（已代理 / 橙色云朵） |
| `--cdn-cert F --cdn-key F` | Cloudflare 源服务器证书和私钥文件 |
| `--no-hy2` | 不启用 Hysteria2 |
| `--notify URL` | 提醒地址：ntfy 主题或 Bark 地址 |
| `--upgrade` | 先安装待处理的系统更新 |
| `--yes` | 所有问题都回答"是" |
| `--update` | 更新 veil，保留密钥和设置 |
| `--restore FILE` | 从 `veil backup` 备份安装（[backup.md](backup.md)） |
| `--uninstall` | 卸载 veil |

## 安装脚本会修改什么

| 方面 | 修改 |
|---|---|
| 软件包 | sing-box（SagerNet apt 源）、Caddy（Caddy apt 源）、nftables、python3、qrencode、fail2ban、unattended-upgrades |
| veil | `/opt/veil`（程序）、`/usr/local/bin/veil`、`/etc/veil`（状态和密钥，仅 root 可读）、`/var/lib/veil`（网站、订阅、备份） |
| 服务 | `veil-singbox`、`veil-nft`、`veil-maint.timer`；Caddy 配置 `/etc/caddy/Caddyfile` |
| 网络 | BBR + fq、更大的 UDP 缓冲区（`/etc/sysctl.d/90-veil.conf`）；关闭 LLMNR/mDNS |
| 更新 | 自动安全更新；更新需要时在 UTC 22:00 自动重启（`/etc/apt/apt.conf.d/52veil-reboot`） |
| 安全 | SSH 的 Fail2ban（`/etc/fail2ban/jail.d/90-veil.conf`）；SSH 密码登录保持开启 |
| 其他 | 时间同步；小内存且无交换空间的服务器添加 512 MB 交换文件；修复部分镜像的 GRUB 安装设备问题 |

安装阶段的输出记录在 `/var/log/veil-install.log`（仅 root 可读）。

## 重复运行

安装脚本可以安全地运行任意次数：

- 在已安装的服务器上，它会显示菜单：**更新或修复**、**全面检查**、**管理菜单**、
  **卸载**。密钥、设置和订阅链接始终保留。
- 如果安装中途被中断，重新运行即可：它会继续安装，并保留已生成的密钥。
- 同一时间只能运行一个安装脚本（锁文件防止重复运行）。

## 更新

```bash
veil update            # 或：veil → 15
veil update --check    # 只比较版本
```

通过发布版安装时，`veil update` 会下载最新发布版，用其 SHA-256 文件校验后以
`--update` 运行。通过 git 安装时，它会在仓库目录中运行 `git pull --ff-only`，再运行
`install.sh --update`。veil 不会自动更新自己；有新版本时，每晚自检会发送提醒。
sing-box、Caddy 和系统会自动更新——见 [operations.md](operations.md#更新)。

## 卸载

```bash
bash /opt/veil/veil-install.sh --uninstall     # 或：veil → 16
```

它会先提示备份，然后删除 veil 的服务、文件和系统设置（包括它添加的交换文件），
并询问是否同时删除 sing-box、Caddy 和 Fail2ban 软件包。
