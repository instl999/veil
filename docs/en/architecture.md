# How veil works

## The routes

```
                      one IP, everything on port 443
client ──TCP 443──► sing-box REALITY ──(no key)──► Caddy: real site + Let's Encrypt cert for www.<domain>
client ──UDP 443──► sing-box Hysteria2 ─(no key)─► same site over HTTP/3 (masquerade)
client ──UDP hop──► nftables redirect ──► UDP 443                      (port hopping)
client ──TLS──► Cloudflare ──► TCP 443 ──► REALITY relays to Caddy ──► WebSocket ──► sing-box (loopback)
```

| Route | Transport | Good for | Weak against |
|---|---|---|---|
| REALITY | VLESS + REALITY + XTLS Vision over TCP | everyday browsing | an IP block |
| HY2 | Hysteria2 (QUIC) on UDP 443 + a hop range | video, lossy lines | UDP throttling |
| CDN | VLESS over WebSocket through Cloudflare | when the IP is blocked; subscription updates | slower; Cloudflare's rules |

- **Self-steal REALITY.** REALITY forwards anyone without the key, byte for
  byte, to Caddy on `127.0.0.1:8443`, which serves the cover site with a real
  certificate for the same name. Name, IP and certificate all match, because the
  "borrowed" site is your own.
- **Hysteria2** uses the same certificate; failed authentication is answered by
  the cover site over HTTP/3. The TCP site advertises HTTP/3 (`Alt-Svc`), so
  QUIC on 443 is expected. Clients use BBR instead of Hysteria's fixed-rate
  sender to look less unusual.
- **CDN.** Cloudflare connects to TCP 443 with the CDN name; REALITY relays it
  to Caddy, which requires Cloudflare's client certificate (Authenticated Origin
  Pulls) and passes the secret WebSocket path to sing-box on loopback.
- **Subscriptions** are served by Caddy under a random path on both names and
  handed out through the CDN name, so updates arrive even when the IP is blocked.

## Clients

Each device gets a mihomo (Clash Meta) profile with its own TLS fingerprint.
Groups: `PROXY` (select), `AUTO` (fallback for browsing), `MEDIA` (fallback for
video), `GAMES` (Steam content direct). Mainland traffic goes direct; DNS for
foreign names goes through the proxy. Shadowrocket gets a base64 list of share
links.

## On the server

| Path | Contents |
|---|---|
| `/etc/veil/state.json` | the single source of truth: keys, credentials, settings (root, 0600) |
| `/etc/veil/sing-box.json`, `/etc/veil/veil.nft`, `/etc/caddy/Caddyfile` | generated from the state — never edit |
| `/etc/veil/tls/` | copy of Caddy's certificate for sing-box |
| `/etc/caddy/veil-cdn.*`, `cloudflare-origin-pull-ca.pem` | Cloudflare origin certificate; Cloudflare's client CA |
| `/var/lib/veil/www`, `sub`, `backups`, `status.json` | cover site, subscriptions, nightly backups, last health report |
| `/opt/veil` | the `veil` tool (Python, standard library only), units, cover-site template |

Every change goes through the same path: update `state.json` → render all
configs → validate each with its own tool (`sing-box check`, `caddy validate`,
`nft -c`) → swap files in atomically → restart only what changed.

| Unit | Role |
|---|---|
| `veil-singbox.service` | sing-box as the unprivileged `veil` user |
| `caddy.service` | the website, ACME, subscriptions, CDN termination |
| `veil-nft.service` | the port-hopping redirect |
| `veil-maint.timer` | nightly maintenance |

## Design decisions

- **Audited components only**: sing-box, Caddy, nftables. No home-made crypto.
- **Standard library Python**: nothing to install from PyPI on the server.
- **One state file**: a backup of it rebuilds the server with identical links.
- **Rotation with a grace period**: old and new credentials overlap, so apps
  switch over on their next refresh without an outage.
- **Safe upgrades**: a new sing-box or Caddy must validate the current configs
  and start, or it is rolled back and held.
- **Humans first**: `veil doctor` explains, the installer verifies each manual
  step, and every message is in English and Chinese.
