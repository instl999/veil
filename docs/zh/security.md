# 安全模型

## veil 的设计目标

一个人（及其设备）在一个封锁和限速境外服务的网络中使用一台 VPS。目标依次是：
难以被识别、部分线路被封时仍能使用、保证服务器安全、无需照看。

veil 让识别变得 **代价高昂**，让恢复变得 **迅速**。没有任何工具能让代理真正无法
区分；本项目也无法在设备被入侵、订阅链接落入他人之手或当地法律方面保护你。

## 自动开启的防护

| 防护 | 作用 |
|---|---|
| REALITY 自偷 | 陌生人、扫描器和 Cloudflare 看到的是真实网站，以及同一域名和 IP 的真实 Let's Encrypt 证书。只有持有密钥的客户端才能连到代理。 |
| Hysteria2 伪装 | 未认证的 QUIC 连接得到同一个网站的 HTTP/3 版本。 |
| 开放端口少 | 只有 TCP 22/80/443、UDP 443 和跳跃端口范围。关闭 LLMNR/mDNS。 |
| 禁止访问服务器自身 | 代理流量无法访问服务器自己的回环和内网地址，包括通过 `localhost` 之类的名字。Caddy 管理接口是 Unix 套接字，不是 TCP 端口。 |
| 拦截滥用 | 拒绝 BitTorrent 和对外 SMTP（25 端口），即使链接泄露也不会导致 VPS 被商家封停。 |
| Fail2ban | 10 分钟内 SSH 登录失败 5 次封禁该 IP 一小时，屡犯更长。密码登录保持可用。 |
| Authenticated Origin Pulls | 在 Cloudflare 中开启后，CDN 域名只响应 Cloudflare。veil 会自动检测、强制，并在强制会导致线路不通时退回。 |
| 80 端口不暴露 CDN 域名 | 服务器在明文 HTTP 上对 CDN 域名的响应与任何未知域名完全一样。 |
| 私密订阅 | 配置只在 128 位随机路径下提供；其他路径得到伪装网站的 404。 |
| 凭据轮换 | 代理密码和 REALITY short ID 每 30 天更换；旧的继续有效 7 天。 |
| 更新 | 每天安装 Debian 安全更新，需要时重启（UTC 22:00）；每晚升级 sing-box 和 Caddy，带配置检查和回滚。 |
| 备份 | 每晚备份，仅 root 可读，保留 14 份。 |
| 最小权限 | sing-box 以无特权用户运行，只有绑定低端口的能力、只读的文件系统视图，且禁止提权。密钥和状态仅 root 可读。 |
| 不记录流量 | sing-box 只记录警告，Caddy 不保留访问日志，系统日志只保留 14 天。 |
| 健康检查与提醒 | `veil doctor` 和每晚检查；通过 ntfy 或 Bark 提醒。 |

## 只能由你设置的防护

| 步骤 | 位置 |
|---|---|
| 两个互不相关的域名（站点域名和 CDN 域名） | [指南](guide.md) 第 1 部分 |
| 站点域名灰色云朵；CDN 域名橙色云朵、**完全（严格）**、源服务器证书和 **Authenticated Origin Pulls** | 安装脚本第 3 步 |
| 商家防火墙：只放行安装脚本第 9 步列出的端口 | 商家面板 |
| 手机提醒 | 安装脚本第 6 步，`veil` → **8** |
| Shadowrocket（及所有应用）开启自动更新 | [clients.md](clients.md) |
| 在电脑上私密保存一份备份 | [backup.md](backup.md) |
| 可选：SSH 密钥登录 | [指南](guide.md) 第 4 部分 |

## 密钥及其存放位置

| 密钥 | 位置 | 如果泄露 |
|---|---|---|
| 订阅链接（包含全部代理凭据） | 你的设备；`/var/lib/veil/sub` | `veil reset-sub` 和 `veil rotate all`，重新导入 |
| 代理凭据、REALITY 私钥 | `/etc/veil/state.json`（仅 root） | `veil rotate all` |
| Cloudflare 源服务器证书私钥 | `/etc/caddy/veil-cdn.key`（root 和 Caddy） | 在 Cloudflare 中吊销，创建新的，`veil cdn-cert` |
| 备份 | `/var/lib/veil/backups`、你的电脑 | 视同以上全部泄露 |
| ntfy 主题 / Bark key | `state.json` | 设置新的（`veil` → **8**） |

提醒中从不包含密钥或链接。

## 为什么 veil 不自动更新自己

sing-box、Caddy 和系统从各自签名的 apt 源自动更新。veil 本身只会告诉你有新版本；
由你运行 `veil update`。自动更新会让任何一旦控制了 GitHub 仓库的人以 root 身份在你
的服务器上运行代码。下载的文件会用发布版的 SHA-256 文件校验。

## 安全地公开本仓库

仓库中绝不能包含真实的服务器 IP、域名、密钥、证书、链接或日志。
`tools/check_sanitized.py` 在 CI（文件和完整的 git 历史）和本地强制检查——见
[development.md](development.md)。

## 报告问题

见 [SECURITY.md](../../SECURITY.md)。
