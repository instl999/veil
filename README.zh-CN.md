# veil

[English](README.md) | [中文](README.zh-CN.md)

个人专用、以隐蔽性优先的代理工具集：一个人、一台低价 VPS，针对封锁和限速境外
服务的网络环境调优。一条命令就能把全新的 Debian 或 Ubuntu 服务器变成藏在真实网站
后面的三条代理线路，带分步引导、每晚自动维护和手机提醒。

全部基于经过审计、广泛使用的组件——sing-box（VLESS + REALITY + Vision、
Hysteria2）、Caddy 和 nftables——不自创任何加密。

## 安装

在全新的 Debian 12 VPS 上，以 root 身份运行：

```bash
curl -fsSLO https://github.com/instl999/veil/releases/latest/download/veil-install.sh && bash veil-install.sh
```

安装脚本会先检查服务器，然后用中英文分 11 步引导你：准确告诉你在 Cloudflare 中
点击哪里，每一步都检查通过后再继续，安装所有组件，检查结果，并显示订阅链接和
二维码。在你确认之前不会修改服务器，并且随时可以安全地重新运行。

第一次接触？请按 **[新手分步指南](docs/zh/guide.md)** 操作。

## 文档

| | |
|---|---|
| **[新手分步指南](docs/zh/guide.md)** | 从租用 VPS 到手机可以使用——从这里开始 |
| [安装参考](docs/zh/install.md) | 系统要求、安装方式、参数、重复运行、更新、卸载 |
| [客户端](docs/zh/clients.md) | Clash Verge Rev、FlClash、Shadowrocket、Stash、OpenClash |
| [管理与维护](docs/zh/operations.md) | `veil` 菜单和命令、每晚维护、更新、提醒 |
| [备份与恢复](docs/zh/backup.md) | 备份、恢复、迁移到新服务器或新 IP |
| [故障排查](docs/zh/troubleshooting.md) | 安装错误、Cloudflare 错误代码、线路慢或被封 |
| [安全模型](docs/zh/security.md) | 哪些防护自动开启，哪些只能由你完成 |
| [工作原理](docs/zh/architecture.md) | 线路、文件、服务、设计决策 |
| [画像工具](docs/zh/profiling.md) | 可选：根据你自己的流量调整指纹和线路 |
| [开发](docs/zh/development.md) | 测试、构建、发布、保持仓库干净 |

## 功能

```
客户端 ──TCP 443──► REALITY ──（无密钥）──► Caddy：你的真实网站 + 真实证书
客户端 ──UDP 443──► Hysteria2 ─（无密钥）─► 同一网站的 HTTP/3
客户端 ──TLS──► Cloudflare ──► 你的服务器 ──► WebSocket                （备用线路）
```

- **REALITY 自偷** —— 域名、IP 和证书全部一致，因为 REALITY 模仿的网站就是你自己
  的。探测者只会看到一个普通博客。
- **三条线路自动切换** —— REALITY 用于浏览，Hysteria2 用于视频，服务器 IP 被封时
  走 Cloudflare CDN。
- **无需照看** —— 证书自动续期，凭据定期轮换并保留宽限期，安全更新自动安装，sing-box 和
  Caddy 升级失败自动回滚，自动备份；`veil doctor` 每晚全面检查，需要你处理时向
  手机发送提醒（ntfy 或 Bark）。
- **默认安全** —— Fail2ban、代理无法访问服务器自身、拦截 BitTorrent/SMTP、CDN 使用
  Authenticated Origin Pulls、服务最小权限、不记录流量。
- **易于管理** —— 输入 `veil` 打开菜单：链接和二维码、设备、健康检查、日志、设置、
  备份、更新。

## 仓库结构

```
install.sh          git 安装入口
server/             安装脚本（bash）和 `veil` 工具（Python 标准库）
profiler/           可选：在你自己电脑上运行的工具
docs/en, docs/zh    文档
tests/, tools/      测试、构建、配置验证、泄露检查
```

## 局限

没有任何工具能让代理流量完全不可区分。veil 的目标是提高被识别的成本、缩短恢复
时间（CDN 备用线路、凭一个备份文件迁移），而不是"隐形"。各国关于跨境网络访问的
法律不同，请了解你所在地的规定和风险。

这是个人项目，按原样提供，不作任何保证。安全问题：见 [SECURITY.md](SECURITY.md)。
变更记录：[CHANGELOG.md](CHANGELOG.md)。
