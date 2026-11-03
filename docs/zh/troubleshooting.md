# 故障排查

**先在服务器上运行 `veil doctor`。** 它会检查服务、DNS、证书、经过 Cloudflare 的
CDN 线路、Authenticated Origin Pulls、提醒、备份和更新，并为每个问题给出解决方法。
每次修复后再运行一次。

## 安装过程中

| 提示 | 原因和解决方法 |
|---|---|
| *Port 80/TCP is already used by 'nginx'*（或 apache2、其他代理） | 另一个程序占用了 veil 需要的端口。停止它：`systemctl disable --now nginx`，然后重新运行安装脚本。 |
| *Could not find this server's public IPv4* | VPS 没有自己的公网 IPv4（NAT/仅 IPv6）。veil 需要独立 IPv4。 |
| *... does not resolve yet* / *points to ..., not to this server* | DNS 记录缺失或错误。在 Cloudflare 中修正，等一分钟后按回车。 |
| 站点域名提示 *... is proxied by Cloudflare (orange cloud)* | 点击云朵使其变为灰色（仅 DNS）。 |
| *The private key does not belong to this certificate* | 你粘贴了两个不同证书的内容。重新创建源服务器证书，并从同一页面粘贴两个框。 |
| *failed at line N* | 阅读上面一行的信息。修复原因后重新运行安装脚本——可以安全重复运行。完整日志在 `/var/log/veil-install.log`。 |
| *Another veil installer is already running* | 等它结束；如果上次运行被强行终止：`rm /run/veil-install.lock`。 |
| apt 或 dpkg 错误、*grub-pc* 错误 | 安装脚本会修复常见的镜像问题（GRUB 指向不存在的磁盘）和配置到一半的软件包；重新运行即可。如果仍然失败：`dpkg --configure -a`，然后重新运行。 |

## 证书一直没有签发

- 站点域名必须是 **仅 DNS（灰色云朵）** 并指向服务器 IP。
- 商家防火墙必须放行 TCP 80（Let's Encrypt 会检查它）。
- `veil logs web` 会显示 Caddy 的 ACME 错误。
- 修复后：`veil sync-cert && veil apply`。证书存在后 Hysteria2 才会启动。

## 完全连不上

1. 在服务器上运行 `veil doctor`——修复所有标记为 **XX** 的项目。
2. 在 **关闭** 代理的情况下，浏览器能否打开 `https://www.example.com`（你的站点域名）？
   - 能 → 服务器可以访问；检查应用（后续步骤）。
   - 不能，但在国外可以 → IP 或域名被封。选择 `CDN` 线路，并迁移到新 IP
     （[backup.md](backup.md)）。
3. 设备时间：REALITY 拒绝误差超过 2 分钟的时钟。开启自动设置时间。
4. 在应用中手动更新订阅。
5. 同一时间只能运行一个 VPN/代理应用。

## Hysteria2（HY2）慢、不通或不显示延迟

- Shadowrocket 从不为 Hysteria2 节点显示延迟。选中它并打开网页测试。
- 晚上 UDP 限速很常见；`MEDIA` 会自动切换到 REALITY。
- 商家防火墙必须放行 UDP 443 **以及** 跳跃端口范围（`veil doctor` 会显示）。
- 如果 UDP 总是被限速，在画像中把 HY2 放到最后
  （`"media": ["REALITY", "HY2", "CDN"]`），或尝试 `"hy2_obfs": true`
  （[profiling.md](profiling.md)）——混淆会隐藏 QUIC 特征，但会让流量变成不透明的
  UDP，有些网络对此限速更严重。两种都试试。

## CDN 线路：Cloudflare 错误代码

`veil doctor` 会帮你解读。简要说明：

| 代码 / 现象 | 含义 | 解决方法 |
|---|---|---|
| 重定向循环 | SSL 模式为 **灵活 / Flexible** | SSL/TLS → **完全（严格）/ Full (strict)** |
| 520 | 服务器拒绝了 Cloudflare 的请求——通常是因为它的客户端证书 | `veil origin-pull`（如果是这个原因，veil 会自动退回） |
| 521 | 服务器拒绝连接 | 商家防火墙必须放行 TCP 443；`veil apply --restart` |
| 522 / 523 | Cloudflare 无法连接服务器 | 检查 A 记录的 IP 和防火墙 |
| 525 | TLS 握手失败 | Cloudflare 中关闭了 Authenticated Origin Pulls，而 veil 要求它：重新开启，然后 `veil origin-pull` |
| 526 | 完全（严格）模式但没有有效的源服务器证书 | 创建一个并粘贴：`veil` → **13**（相同域名）或 `veil cdn-cert` |
| Cloudflare 返回 403 | Cloudflare 的安全规则 | 安全性 → 关闭 **Bot Fight Mode**，检查 WAF 规则 |
| WebSocket 失败 | WebSockets 已关闭 | 网络 → **WebSockets：开启** |

## 晚上慢

几乎都是你的运营商到 VPS 之间的线路问题。测试你的每条线路（晚上 9 点用
`nexttrace` 追踪到服务器），使用最好的那条，降低视频清晰度，或者选择针对你的
运营商有优质线路（CN2 GIA、9929、CMIN2）的 VPS。

## 订阅无法更新

- 如果所有线路都不通，应用无法通过自己更新：关闭代理后再更新。
- 订阅链接使用 CDN 域名；`veil doctor` 必须显示 CDN 线路正常。
- 运行 `veil reset-sub` 或 `veil cdn-host` 后，旧链接失效——需要重新导入。

## 收不到提醒

- `veil alert-test`——它会显示服务是否接受了消息。
- ntfy：应用中的主题必须完全一致；不走代理时，国内可能无法访问 ntfy.sh。
- Bark：重新从应用中复制设备地址。

## SSH 被锁定

10 分钟内输错 5 次密码会封禁你的 IP（一小时，重复则更长）。等待、换一个网络，
或通过商家的网页控制台登录并运行 `fail2ban-client set sshd unbanip 你的IP`。

## 维护报告软件包被锁定

sing-box 或 Caddy 的自动升级未通过检查，已回滚。等更新的版本发布后：

```bash
apt-mark unhold sing-box    # 或 caddy
veil maint
```

## 寻求帮助

分享 `veil doctor` 的输出和 `veil logs -n 100`。分享任何内容之前，请删除你的 IP、
域名、UUID、密码和订阅令牌。
