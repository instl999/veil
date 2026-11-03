# veil 的工作原理

## 线路

```
                      一个 IP，全部在 443 端口
客户端 ──TCP 443──► sing-box REALITY ──（无密钥）──► Caddy：真实网站 + www.<域名> 的 Let's Encrypt 证书
客户端 ──UDP 443──► sing-box Hysteria2 ─（无密钥）─► 同一网站的 HTTP/3（伪装）
客户端 ──UDP 跳跃──► nftables 重定向 ──► UDP 443                        （端口跳跃）
客户端 ──TLS──► Cloudflare ──► TCP 443 ──► REALITY 转给 Caddy ──► WebSocket ──► sing-box（回环）
```

| 线路 | 传输方式 | 适合 | 弱点 |
|---|---|---|---|
| REALITY | VLESS + REALITY + XTLS Vision，基于 TCP | 日常浏览 | IP 被封 |
| HY2 | Hysteria2（QUIC），UDP 443 + 跳跃端口范围 | 视频、丢包线路 | UDP 限速 |
| CDN | VLESS over WebSocket，经过 Cloudflare | IP 被封时；订阅更新 | 较慢；受 Cloudflare 规则约束 |

- **REALITY 自偷。** REALITY 把所有没有密钥的连接原样转发给 `127.0.0.1:8443` 上的
  Caddy，Caddy 用同一域名的真实证书提供伪装网站。域名、IP 和证书全部一致，因为
  "借用"的网站就是你自己的。
- **Hysteria2** 使用同一张证书；认证失败的连接由伪装网站通过 HTTP/3 响应。TCP 网站
  会声明支持 HTTP/3（`Alt-Svc`），所以 443 上出现 QUIC 是正常的。客户端使用 BBR，
  而不是 Hysteria 的固定速率发送，以减少异常特征。
- **CDN。** Cloudflare 以 CDN 域名连接 TCP 443；REALITY 把它转给 Caddy，Caddy 要求
  Cloudflare 的客户端证书（Authenticated Origin Pulls），并把秘密的 WebSocket 路径
  通过回环交给 sing-box。
- **订阅** 由 Caddy 在两个域名的随机路径下提供，并通过 CDN 域名分发，所以即使 IP
  被封，更新也能送达。

## 客户端

每台设备得到一份带有自己 TLS 指纹的 mihomo（Clash Meta）配置。分组：`PROXY`
（手动选择）、`AUTO`（浏览用的自动切换）、`MEDIA`（视频用的自动切换）、`GAMES`
（Steam 内容直连）。国内流量直连；境外域名的 DNS 通过代理解析。Shadowrocket 得到
base64 编码的分享链接列表。

## 服务器上

| 路径 | 内容 |
|---|---|
| `/etc/veil/state.json` | 唯一的数据来源：密钥、凭据、设置（root，0600） |
| `/etc/veil/sing-box.json`、`/etc/veil/veil.nft`、`/etc/caddy/Caddyfile` | 根据状态生成——不要手动修改 |
| `/etc/veil/tls/` | 给 sing-box 用的 Caddy 证书副本 |
| `/etc/caddy/veil-cdn.*`、`cloudflare-origin-pull-ca.pem` | Cloudflare 源服务器证书；Cloudflare 的客户端 CA |
| `/var/lib/veil/www`、`sub`、`backups`、`status.json` | 伪装网站、订阅、每晚备份、最近一次健康报告 |
| `/opt/veil` | `veil` 工具（Python，仅标准库）、服务单元、伪装网站模板 |

所有修改都走同一条路径：更新 `state.json` → 生成所有配置 → 用各自的工具验证
（`sing-box check`、`caddy validate`、`nft -c`）→ 原子替换文件 → 只重启有变化的服务。

| 单元 | 作用 |
|---|---|
| `veil-singbox.service` | 以无特权的 `veil` 用户运行 sing-box |
| `caddy.service` | 网站、ACME、订阅、CDN 终结 |
| `veil-nft.service` | 端口跳跃重定向 |
| `veil-maint.timer` | 每晚维护 |

## 设计决策

- **只用经过审计的组件**：sing-box、Caddy、nftables。不自制加密。
- **只用 Python 标准库**：服务器上无需从 PyPI 安装任何东西。
- **单一状态文件**：用它的备份就能重建出链接完全相同的服务器。
- **有宽限期的轮换**：新旧凭据同时有效一段时间，应用在下次更新时切换，不会中断。
- **安全升级**：新的 sing-box 或 Caddy 必须通过当前配置的验证并成功启动，否则回滚
  并锁定。
- **以人为本**：`veil doctor` 会解释问题，安装脚本会验证每个手动步骤，所有消息都
  有中英文。
