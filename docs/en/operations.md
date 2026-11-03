# Administration and maintenance

Everything day to day is in the `veil` menu; every menu item is also a command.

## The menu

Log in to the server and type `veil`:

```
  ── Devices and subscriptions ──        ── Maintenance ──
   1. Show subscription links             8. Settings: alerts, rotation, upgrades
   2. Show QR code                        9. Rotate proxy credentials now
   3. Add a device                       10. Run nightly maintenance now
   4. Remove a device                    11. Backups
   5. Reset subscription URLs (leaked)   12. Restart services
  ── Health ──                           ── Advanced ──
   6. Check everything (doctor)          13. Change CDN domain
   7. View logs                          14. Apply personalization profile
                                         15. Update veil
                                         16. Uninstall veil
```

## Commands

| Command | What it does |
|---|---|
| `veil doctor [--only system site cdn upkeep]` | check everything; every problem comes with a fix (exit code 1 if any) |
| `veil status` | the same health data as JSON, for scripts |
| `veil links [--qr NAME] [--json]` | subscription URLs, share links, QR codes |
| `veil device list` / `add NAME --fingerprint F --client C` / `rm NAME` | per-device profiles |
| `veil reset-sub` | new subscription URLs for every device; old ones stop at once |
| `veil rotate creds\|path\|short_id\|hop\|all [--grace DAYS]` | replace secrets now (old ones stay valid for the grace period) |
| `veil set notify_url URL` | alerts: `https://ntfy.sh/<topic>`, `https://api.day.app/<key>` (Bark), or empty for off |
| `veil alert-test [URL]` | send a test alert |
| `veil set rotate_days N` / `grace_days N` | credential rotation interval (0 = off) / grace period |
| `veil set auto_upgrade true\|false` | automatic sing-box/Caddy upgrades |
| `veil maint` | run the nightly maintenance now |
| `veil backup [--out FILE]` / `--list` | make a backup (prints the copy command) / list the nightly ones |
| `veil restore FILE` | restore a backup on this server, then `veil apply --restart` |
| `veil logs [proxy\|web\|maint\|fail2ban\|all] [-n N] [-f]` | recent log lines |
| `veil apply [--restart]` | re-render configs and restart what changed (or everything) |
| `veil cdn-host HOST [--cert F --key F]` | move the CDN route to another domain |
| `veil cdn-cert --cert F --key F` | install or replace the Cloudflare origin certificate |
| `veil origin-pull` | check Authenticated Origin Pulls and enforce it once Cloudflare sends its certificate |
| `veil profile show` / `apply FILE` | view or apply a personalization profile ([profiling.md](profiling.md)) |
| `veil update [--check] [--force]` | update veil itself ([install.md](install.md#updating)) |
| `veil --version` | installed version |
| `fail2ban-client status sshd` | SSH failures and banned IPs; `fail2ban-client set sshd unbanip IP` to unban |

## What runs by itself

`veil-maint.timer` runs every night between 19:00 and 21:00 UTC (03:00–05:00
China time). Each run:

1. copies a renewed Let's Encrypt certificate to sing-box (Caddy renews it);
2. drops retired credentials whose grace period has ended;
3. rotates credentials every 30 days; old ones keep working for 7 days so apps
   switch over on their next subscription refresh, and you get an alert;
4. upgrades sing-box and Caddy **safely**: the new version must pass the config
   check and start, otherwise the old binary is put back and the package is
   held (you get an alert); if apt is busy it simply retries the next night;
5. checks Authenticated Origin Pulls (enforces it, or backs off if enforcing
   breaks the CDN route);
6. writes a backup to `/var/lib/veil/backups` (14 kept);
7. checks whether a newer veil release exists (alert once per version);
8. health-checks everything, writes `/var/lib/veil/status.json`, and sends an
   alert if anything is wrong.

## Updates

| What | How | When |
|---|---|---|
| Debian security updates | `unattended-upgrades` | daily |
| Restart after kernel/library updates | automatic, only when needed | 22:00 UTC (06:00 China time) |
| sing-box, Caddy | nightly maintenance, with check and rollback | nightly |
| veil itself | **you**: `veil update` (alert when available) | when you choose |

veil is not updated unattended on purpose: automatic code updates would let
anyone who ever took over the GitHub repository run code on your server.

## Alerts

`veil` → **8. Settings → Alerts** sets them up and sends a test:

- **ntfy** (iPhone and Android): veil generates a random topic; subscribe to it
  in the ntfy app. Anyone who knows the topic can read the alerts, so keep it
  random. ntfy.sh may need the proxy to reach your phone in China.
- **Bark** (iPhone): paste the device URL from the Bark app
  (`https://api.day.app/<key>`). It works inside China.

Alerts carry problem descriptions and the site name, never keys or links.

## Credentials and subscription links

- Each device has its own subscription URL (its own TLS fingerprint).
- Rotation changes the proxy passwords, not the URLs. Apps that refresh their
  subscription (every 12 h by default; Shadowrocket needs **Auto update** on)
  never notice.
- If a URL leaks: `veil` → **5** (or `veil reset-sub`). Every URL changes;
  re-import on each device. Rotate credentials too (`veil rotate all`).

## Devices

`veil` → **3. Add a device** asks for a name, the device's browser/OS (TLS
fingerprint) and the client app, then shows the URL and a QR code (FlClash gets
a one-tap import link). From the command line:

```bash
veil device add ipad --fingerprint ios --client shadowrocket
veil device rm windows
veil device list
```

## Moving the CDN route to another domain

`veil` → **13** shows the Cloudflare steps for the new domain, checks that it is
proxied, takes the origin certificate by paste and moves the route. Subscription
URLs change (they use the CDN name): re-import them on every device, then delete
the old DNS record.

## Logs

```bash
veil logs            # all services, last 100 lines
veil logs proxy -f   # follow sing-box
veil logs maint      # nightly maintenance
```

Logs are kept for 14 days. sing-box logs warnings only, and Caddy keeps no
access log, so neither records the sites you visit.

## Backups

See [backup.md](backup.md).
