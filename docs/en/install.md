# Installation reference

The [beginner guide](guide.md) walks through a first installation. This page
is the reference: requirements, every way to install, what the installer
changes, and how re-running, updating, restoring and uninstalling work.

## Requirements

| | |
|---|---|
| OS | Debian 11/12 or Ubuntu 22.04/24.04, with systemd |
| CPU | amd64 or arm64 |
| Memory / disk | 512 MB RAM (1 GB+ recommended), 1.5 GB free disk |
| Network | a public IPv4 address on the server (no NAT); KVM recommended (OpenVZ/LXC may lack BBR) |
| Ports | TCP 80, TCP 443, UDP 443 free (the installer checks and names any program using them) |
| Domains | one domain on Cloudflare for the site name; ideally a second, unrelated one for the CDN route |
| Access | root (or `sudo -i`) |

## Ways to install

### 1. Latest release (recommended)

```bash
curl -fsSLO https://github.com/instl999/veil/releases/latest/download/veil-install.sh
bash veil-install.sh
```

`veil-install.sh` is a single file: the installer plus the `veil` tool, the
service units and the cover site, built by CI from this repository. Each release
also has `veil-install.sh.sha256`:

```bash
curl -fsSLO https://github.com/instl999/veil/releases/latest/download/veil-install.sh.sha256
sha256sum -c veil-install.sh.sha256
```

### 2. From a git checkout

```bash
apt-get update && apt-get install -y git
git clone https://github.com/instl999/veil.git /root/veil
bash /root/veil/install.sh
```

Keep the checkout: `veil update` then runs `git pull` there and re-installs.

### 3. Offline copy

Build on your computer (`python tools/build.py`), copy `dist/veil-install.sh`
with `scp`, and run it on the server.

## The guided setup

Run without options, the installer first checks the server (architecture,
memory, disk, free ports, internet access, public IP) and then guides you
through 11 steps:

1. what you need; 2. the site name, with its DNS record and a live DNS check;
3. the optional CDN route: DNS record (checked), SSL mode, origin certificate
(pasted and checked against the key and the name), Authenticated Origin Pulls;
4. email; 5. Hysteria2 and system updates; 6. phone alerts (ntfy or Bark);
7. review — **nothing on the server changes before this point**; 8. full check
(`veil doctor`), Authenticated Origin Pulls and a test alert, each repeated until
it passes or you skip it; 9. provider firewall ports; 10. device links and QR
codes; 11. a backup and the command to copy it to your computer.

## Non-interactive install

```bash
bash veil-install.sh --site-host www.example.com --email you@example.com \
  --cdn-host static.example.net --cdn-cert origin.pem --cdn-key origin.key \
  --notify https://ntfy.sh/your-random-topic --upgrade --yes
```

| Option | Meaning |
|---|---|
| `--site-host H` | site name (DNS only / grey cloud) — required |
| `--email E` | Let's Encrypt contact — required |
| `--cdn-host H` | CDN name (proxied / orange cloud) |
| `--cdn-cert F --cdn-key F` | Cloudflare origin certificate and key files |
| `--no-hy2` | leave out Hysteria2 |
| `--notify URL` | ntfy topic or Bark URL for alerts |
| `--upgrade` | install pending system updates first |
| `--yes` | answer yes to every question |
| `--update` | update veil, keep keys and settings |
| `--restore FILE` | install from a `veil backup` archive ([backup.md](backup.md)) |
| `--uninstall` | remove veil |

## What the installer changes

| Area | Change |
|---|---|
| Packages | sing-box (SagerNet apt repository), Caddy (Caddy apt repository), nftables, python3, qrencode, fail2ban, unattended-upgrades |
| veil | `/opt/veil` (code), `/usr/local/bin/veil`, `/etc/veil` (state and keys, root-only), `/var/lib/veil` (site, subscriptions, backups) |
| Services | `veil-singbox`, `veil-nft`, `veil-maint.timer`; Caddy's config at `/etc/caddy/Caddyfile` |
| Network | BBR + fq, larger UDP buffers (`/etc/sysctl.d/90-veil.conf`); LLMNR/mDNS off |
| Updates | unattended security upgrades, automatic restart at 22:00 UTC when an update needs it (`/etc/apt/apt.conf.d/52veil-reboot`) |
| Security | Fail2ban for SSH (`/etc/fail2ban/jail.d/90-veil.conf`); SSH password login stays on |
| Other | time sync; a 512 MB swap file on small servers without swap; GRUB install-device repair on images that need it |

Install-phase output is logged to `/var/log/veil-install.log` (root-only).

## Running it again

The installer is safe to run any number of times:

- On an installed server it shows a menu: **update or repair**, **check
  everything**, **management menu**, **uninstall**. Keys, settings and
  subscription links are always kept.
- If an install was interrupted, run it again: it continues and keeps whatever
  keys were already created.
- Only one installer runs at a time (a lock file prevents two).

## Updating

```bash
veil update            # or: veil → 15
veil update --check    # only compare versions
```

From a release install, `veil update` downloads the latest release, checks it
against its SHA-256 file and runs it with `--update`. From a git install it runs
`git pull --ff-only` in the checkout and then `install.sh --update`. veil never
updates itself unattended; the nightly check tells you (by alert) when a new
release exists. sing-box, Caddy and the OS update automatically — see
[operations.md](operations.md#updates).

## Uninstalling

```bash
bash /opt/veil/veil-install.sh --uninstall     # or: veil → 16
```

It offers a backup first, removes veil's services, files and system settings
(including its swap file), and asks whether to remove the sing-box, Caddy and
Fail2ban packages too.
