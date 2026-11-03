# Security model

## What veil is designed for

One person (and their devices) using one VPS from a network that blocks and
throttles foreign services. The goals are, in order: stay hard to detect, keep
working when something is blocked, keep the server safe, and need no attention.

veil makes detection **expensive** and recovery **fast**. No tool makes a proxy
truly indistinguishable, and nothing here protects you from a compromised
device, from someone who has your subscription link, or from the law where you
live.

## Automatic protections (on by default)

| Protection | What it does |
|---|---|
| REALITY self-steal | Strangers, scanners and Cloudflare reach a real website with a real Let's Encrypt certificate for the same name and IP. Only clients with the key reach the proxy. |
| Hysteria2 masquerade | Unauthenticated QUIC gets the same website over HTTP/3. |
| Few open ports | Only TCP 22/80/443, UDP 443 and the hop range. LLMNR/mDNS are turned off. |
| No access to the server itself | Proxy traffic cannot reach the server's own loopback or private addresses, even through names like `localhost`. Caddy's admin API is a Unix socket, not a TCP port. |
| Abuse blocking | BitTorrent and outgoing SMTP (port 25) are refused, so a leaked link cannot get the VPS suspended. |
| Fail2ban | 5 failed SSH logins in 10 minutes ban the IP for an hour, longer for repeat offenders. Password login stays available. |
| Authenticated Origin Pulls | Once you switch it on in Cloudflare, the CDN name answers only Cloudflare. veil detects, enforces, and backs off if enforcing would break the route. |
| CDN name not revealed on port 80 | The server answers the CDN name on plain HTTP exactly like any unknown name. |
| Private subscriptions | Settings are served only under a 128-bit random path; anything else gets the cover site's 404. |
| Credential rotation | Proxy passwords and REALITY short IDs change every 30 days; old ones keep working 7 days. |
| Updates | Debian security updates daily, restart when needed (22:00 UTC); sing-box and Caddy upgraded nightly with config check and rollback. |
| Backups | Nightly, root-only, 14 kept. |
| Least privilege | sing-box runs as an unprivileged user with only the capability to bind low ports, a read-only filesystem view and no new privileges. Keys and state are root-only. |
| No traffic logs | sing-box logs warnings only, Caddy keeps no access log, journals are trimmed to 14 days. |
| Health and alerts | `veil doctor` and the nightly check; alerts by ntfy or Bark. |

## Protections only you can set up

| Step | Where |
|---|---|
| Two unrelated domains (site name and CDN name) | [guide](guide.md) Part 1 |
| Grey cloud for the site name; orange cloud, **Full (strict)**, origin certificate and **Authenticated Origin Pulls** for the CDN name | installer step 3 |
| Provider firewall: allow only the ports from installer step 9 | provider panel |
| Alerts on your phone | installer step 6, `veil` → **8** |
| Auto update in Shadowrocket (and every app) | [clients.md](clients.md) |
| A backup on your computer, kept private | [backup.md](backup.md) |
| Optional: SSH key login | [guide](guide.md) Part 4 |

## Secrets and where they live

| Secret | Location | If it leaks |
|---|---|---|
| Subscription URLs (contain all proxy credentials) | your devices; `/var/lib/veil/sub` | `veil reset-sub` and `veil rotate all`, re-import |
| Proxy credentials, REALITY private key | `/etc/veil/state.json` (root-only) | `veil rotate all` |
| Cloudflare origin certificate key | `/etc/caddy/veil-cdn.key` (root and Caddy) | revoke it in Cloudflare, create a new one, `veil cdn-cert` |
| Backups | `/var/lib/veil/backups`, your computer | treat as all of the above |
| ntfy topic / Bark key | `state.json` | set a new one (`veil` → **8**) |

Alerts never contain keys or links.

## Why veil does not update itself

sing-box, Caddy and the OS update automatically, from their signed apt
repositories. veil itself only tells you a new release exists; you run
`veil update`. An automatic update would let anyone who ever gained control of
the GitHub repository run code as root on your server. Downloads are checked
against the release's SHA-256 file.

## Publishing this repository safely

The repository must never contain a real server IP, domain, key, certificate,
link or log. `tools/check_sanitized.py` enforces it in CI (files and the whole
git history) and locally — see [development.md](development.md).

## Reporting a problem

See [SECURITY.md](../../SECURITY.md).
