# veil

[English](README.md) | [中文](README.zh-CN.md)

A personal, stealth-first proxy toolkit for one person on one budget VPS,
tuned for networks that block and throttle foreign services. One command turns a
fresh Debian or Ubuntu server into three proxy routes behind a real website,
with a guided setup, nightly self-maintenance and phone alerts.

Built on audited, widely deployed components — sing-box (VLESS + REALITY +
Vision, Hysteria2), Caddy and nftables — with no home-made cryptography.

## Install

On a fresh Debian 12 VPS, as root:

```bash
curl -fsSLO https://github.com/instl999/veil/releases/latest/download/veil-install.sh && bash veil-install.sh
```

The installer checks the server, then walks you through 11 steps in English and
Chinese: it tells you exactly what to click in Cloudflare, verifies each step
before moving on, installs everything, checks the result, and shows your
subscription links and QR codes. It changes nothing on the server until you
confirm, and it is safe to run again at any time.

New to all of this? Follow the **[step-by-step guide](docs/en/guide.md)**.

## Documentation

| | |
|---|---|
| **[Step-by-step guide](docs/en/guide.md)** | from renting a VPS to a working phone — start here |
| [Installation reference](docs/en/install.md) | requirements, install methods, flags, rerunning, updating, uninstalling |
| [Clients](docs/en/clients.md) | Clash Verge Rev, FlClash, Shadowrocket, Stash, OpenClash |
| [Administration](docs/en/operations.md) | the `veil` menu and commands, nightly maintenance, updates, alerts |
| [Backup and recovery](docs/en/backup.md) | backups, restoring, moving to a new server or IP |
| [Troubleshooting](docs/en/troubleshooting.md) | installer errors, Cloudflare error codes, slow or blocked routes |
| [Security model](docs/en/security.md) | what is protected automatically and what only you can do |
| [How it works](docs/en/architecture.md) | routes, files, services, design decisions |
| [Profiler](docs/en/profiling.md) | optional: tune fingerprints and routes to your own traffic |
| [Development](docs/en/development.md) | tests, building, releasing, keeping the repository clean |

## What you get

```
client ──TCP 443──► REALITY ──(no key)──► Caddy: your real site + real certificate
client ──UDP 443──► Hysteria2 ─(no key)─► the same site over HTTP/3
client ──TLS──► Cloudflare ──► your server ──► WebSocket                (backup route)
```

- **Self-steal REALITY** — name, IP and certificate all match, because the site
  REALITY imitates is your own. Probes see an ordinary blog.
- **Three routes with automatic failover** — REALITY for browsing, Hysteria2 for
  video, Cloudflare CDN when the server's IP is blocked.
- **Hands-off** — certificates renew, credentials rotate with a grace period,
  security updates install, sing-box and Caddy upgrade with automatic rollback,
  backups are kept, and `veil doctor` checks everything nightly and alerts your
  phone (ntfy or Bark) when something needs you.
- **Secure by default** — Fail2ban, no access from the proxy to the server
  itself, BitTorrent/SMTP blocked, Authenticated Origin Pulls for the CDN,
  least-privilege services, no traffic logs.
- **Easy to manage** — type `veil` for a menu: links and QR codes, devices,
  health check, logs, settings, backups, updates.

## Repository layout

```
install.sh          git install entry point
server/             installer (bash) and the `veil` tool (Python, standard library)
profiler/           optional tools that run on your own computer
docs/en, docs/zh    documentation
tests/, tools/      tests, build, config validation, leak check
```

## Limits

No tool makes a proxy truly indistinguishable. veil makes detection expensive
and recovery fast (CDN backup route, migration with one backup file); it does
not make you invisible. Laws on cross-border network access differ by country;
understand the rules and risks where you live.

This is a personal project, provided as is, without warranty. Security issues:
see [SECURITY.md](SECURITY.md). Changes: [CHANGELOG.md](CHANGELOG.md).
