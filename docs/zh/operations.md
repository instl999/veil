# 管理与维护

日常操作都在 `veil` 菜单中；每个菜单项也都有对应的命令。

## 菜单

登录服务器后输入 `veil`：

```
  ── 设备与订阅 ──                       ── 维护 ──
   1. 显示订阅链接                        8. 设置：提醒、轮换、升级
   2. 显示二维码                          9. 立即轮换代理凭据
   3. 添加设备                           10. 立即运行每晚维护
   4. 删除设备                           11. 备份
   5. 重置订阅链接（泄露时）             12. 重启服务
  ── 健康 ──                             ── 高级 ──
   6. 全面检查（doctor）                 13. 更换 CDN 域名
   7. 查看日志                           14. 应用个性化画像
                                         15. 更新 veil
                                         16. 卸载 veil
```

## 命令

| 命令 | 作用 |
|---|---|
| `veil doctor [--only system site cdn upkeep]` | 全面检查；每个问题都附带解决方法（有问题时退出码为 1） |
| `veil status` | 同样的健康数据，JSON 格式，供脚本使用 |
| `veil links [--qr NAME] [--json]` | 订阅链接、分享链接、二维码 |
| `veil device list` / `add NAME --fingerprint F --client C` / `rm NAME` | 每台设备的配置 |
| `veil reset-sub` | 为所有设备生成新的订阅链接；旧链接立即失效 |
| `veil rotate creds\|path\|short_id\|hop\|all [--grace DAYS]` | 立即更换密钥（旧的在宽限期内仍然有效） |
| `veil set notify_url URL` | 提醒：`https://ntfy.sh/<主题>`、`https://api.day.app/<key>`（Bark），留空表示关闭 |
| `veil alert-test [URL]` | 发送测试提醒 |
| `veil set rotate_days N` / `grace_days N` | 凭据轮换间隔（0 = 关闭）/ 宽限期 |
| `veil set auto_upgrade true\|false` | 自动升级 sing-box/Caddy |
| `veil maint` | 立即运行每晚维护 |
| `veil backup [--out FILE]` / `--list` | 生成备份（并打印复制命令）/ 列出每晚备份 |
| `veil restore FILE` | 在本机恢复备份，然后运行 `veil apply --restart` |
| `veil logs [proxy\|web\|maint\|fail2ban\|all] [-n N] [-f]` | 最近的日志 |
| `veil apply [--restart]` | 重新生成配置并重启有变化的服务（或全部重启） |
| `veil cdn-host HOST [--cert F --key F]` | 把 CDN 线路迁移到另一个域名 |
| `veil cdn-cert --cert F --key F` | 安装或更换 Cloudflare 源服务器证书 |
| `veil origin-pull` | 检查 Authenticated Origin Pulls，并在 Cloudflare 发送客户端证书后强制要求 |
| `veil profile show` / `apply FILE` | 查看或应用个性化画像（[profiling.md](profiling.md)） |
| `veil update [--check] [--force]` | 更新 veil 本身（[install.md](install.md#更新)） |
| `veil --version` | 已安装的版本 |
| `fail2ban-client status sshd` | SSH 失败次数和被封禁的 IP；解封：`fail2ban-client set sshd unbanip IP` |

## 自动运行的内容

`veil-maint.timer` 每晚 UTC 19:00–21:00（北京时间 03:00–05:00）运行。每次：

1. 把 Caddy 续期的 Let's Encrypt 证书复制给 sing-box；
2. 删除宽限期已结束的旧凭据；
3. 每 30 天轮换一次凭据；旧凭据继续有效 7 天，应用在下次更新订阅时自动切换，
   同时你会收到提醒；
4. **安全地** 升级 sing-box 和 Caddy：新版本必须通过配置检查并成功启动，否则
   恢复旧版本并锁定该软件包（你会收到提醒）；如果 apt 正忙，第二天晚上再试；
5. 检查 Authenticated Origin Pulls（开启强制，或在强制会导致 CDN 线路不通时退回）；
6. 在 `/var/lib/veil/backups` 写入备份（保留 14 份）；
7. 检查是否有新的 veil 发布版（每个版本只提醒一次）；
8. 全面检查，写入 `/var/lib/veil/status.json`，有问题时发送提醒。

## 更新

| 内容 | 方式 | 时间 |
|---|---|---|
| Debian 安全更新 | `unattended-upgrades` | 每天 |
| 内核/库更新后的重启 | 自动，仅在需要时 | UTC 22:00（北京时间 06:00） |
| sing-box、Caddy | 每晚维护，带检查和回滚 | 每晚 |
| veil 本身 | **你自己**：`veil update`（有新版本时会提醒） | 由你决定 |

veil 故意不自动更新：自动更新代码意味着任何一旦控制了 GitHub 仓库的人都能在你的
服务器上运行代码。

## 提醒

`veil` → **8. 设置 → 提醒** 进行设置并发送测试：

- **ntfy**（iPhone 和安卓）：veil 生成一个随机主题，在 ntfy 应用中订阅即可。
  知道主题的人都能看到提醒，所以请保持随机。在国内，ntfy.sh 可能需要通过代理
  才能推送到手机。
- **Bark**（iPhone）：粘贴 Bark 应用中的设备地址（`https://api.day.app/<key>`）。
  在国内可以直接使用。

提醒只包含问题描述和站点域名，从不包含密钥或链接。

## 凭据和订阅链接

- 每台设备有自己的订阅链接（自己的 TLS 指纹）。
- 轮换只改变代理密码，不改变链接。会自动更新订阅的应用（默认每 12 小时；
  Shadowrocket 需要开启 **自动更新**）完全感觉不到。
- 如果链接泄露：`veil` → **5**（或 `veil reset-sub`）。所有链接都会改变，需要在每台
  设备上重新导入。同时轮换凭据（`veil rotate all`）。

## 设备

`veil` → **3. 添加设备** 会询问名称、设备的浏览器/系统（TLS 指纹）和客户端应用，
然后显示链接和二维码（FlClash 会得到一键导入链接）。命令行方式：

```bash
veil device add ipad --fingerprint ios --client shadowrocket
veil device rm windows
veil device list
```

## 把 CDN 线路迁移到另一个域名

`veil` → **13** 会显示新域名需要在 Cloudflare 完成的步骤，检查其是否已代理，
通过粘贴接收源服务器证书，然后迁移线路。订阅链接会改变（它们使用 CDN 域名）：
请在每台设备上重新导入，然后删除旧的 DNS 记录。

## 日志

```bash
veil logs            # 所有服务，最近 100 行
veil logs proxy -f   # 实时查看 sing-box
veil logs maint      # 每晚维护
```

日志保留 14 天。sing-box 只记录警告，Caddy 不保留访问日志，因此都不会记录你访问
的网站。

## 备份

见 [backup.md](backup.md)。
