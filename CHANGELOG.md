# Changelog

## [0.2.0] - 2026-11-03

First public release.

### Installer
- Guided setup in 11 steps (English and Chinese): checks the server first,
  explains every setting, shows exactly what to configure in Cloudflare, and
  verifies DNS, the origin certificate, Authenticated Origin Pulls and alerts
  before moving on. Nothing changes until you confirm.
- Safe to rerun: on an installed server it offers update/repair, health check,
  menu and uninstall; an interrupted install resumes and keeps its keys; a lock
  prevents two installers at once.
- Clear errors with the failing step, the cause and how to recover; a root-only
  install log in `/var/log/veil-install.log`.
- Installs from a GitHub release (`veil-install.sh` with a SHA-256 file) or from
  a git clone; `--notify` flag for alerts.
- Adds 512 MB of swap on small servers without any.

### Management
- `veil doctor`: checks services, clock, BBR, disk, DNS, certificates, the CDN
  route through Cloudflare (with explanations for Cloudflare errors 520–526 and
  Flexible SSL), WebSocket, Authenticated Origin Pulls, alerts, backups and
  updates, each with a fix.
- `veil logs`, `veil alert-test`, `veil update [--check]`, `veil backup --list`.
- Alerts by ntfy or Bark, set up from the menu with a test message.
- Reorganized menu with health, logs, alerts, backups, update and uninstall.

### Maintenance
- Nightly backups (14 kept), a once-per-version alert for new veil releases, and
  restart after kernel or library updates at 22:00 UTC when needed.
- sing-box/Caddy upgrades retry the next night when apt is busy instead of
  holding the package.
- Authenticated Origin Pulls backs off automatically if enforcing it would break
  the CDN route.

### Security
- Proxy traffic can no longer reach the server's own loopback services, including
  through names such as `localhost`; Caddy's admin API moved to a Unix socket.
- The CDN name is no longer answered differently on port 80.

### Repository
- Documentation rewritten for beginners in English and Chinese.
- CI: unit tests, shellcheck, build, validation of generated configs with real
  sing-box, Caddy and nftables, and a leak check of files and git history.
- Releases built and published from tags.

## [0.1.0]

Private first version: VLESS + REALITY + Vision with a self-hosted cover site,
Hysteria2 with port hopping, Cloudflare CDN WebSocket route, per-device mihomo
profiles and Shadowrocket subscription, credential rotation with a grace period,
safe sing-box/Caddy upgrades with rollback, Fail2ban, backup and restore, and the
traffic profiler.
