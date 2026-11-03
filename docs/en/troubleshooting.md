# Troubleshooting

**Start with `veil doctor` on the server.** It checks the services, DNS,
certificates, the CDN route through Cloudflare, Authenticated Origin Pulls,
alerts, backups and updates, and prints a fix for every problem. Run it again
after each fix.

## During installation

| Message | Cause and fix |
|---|---|
| *Port 80/TCP is already used by 'nginx'* (or apache2, another proxy) | Another program holds a port veil needs. Stop it: `systemctl disable --now nginx`, then run the installer again. |
| *Could not find this server's public IPv4* | The VPS has no public IPv4 of its own (NAT/IPv6-only). veil needs one. |
| *... does not resolve yet* / *points to ..., not to this server* | The DNS record is missing or wrong. Fix it in Cloudflare, wait a minute, press Enter. |
| *... is proxied by Cloudflare (orange cloud)* for the site name | Click the cloud so it turns grey (DNS only). |
| *The private key does not belong to this certificate* | You pasted the boxes of two different certificates. Create a new origin certificate and paste both boxes from the same page. |
| *failed at line N* | Read the line above it. Fix the cause and run the installer again — it is safe to repeat. The full log is in `/var/log/veil-install.log`. |
| *Another veil installer is already running* | Wait for it, or if a previous run was killed: `rm /run/veil-install.lock`. |
| apt or dpkg errors, *grub-pc* errors | The installer repairs the common image problem (GRUB pointing at a missing disk) and half-configured packages; run it again. If it persists: `dpkg --configure -a`, then rerun. |

## Certificate never issued

- The site name must be **DNS only (grey)** and point at the server's IP.
- TCP 80 must be open in the provider's firewall (Let's Encrypt checks it).
- `veil logs web` shows Caddy's ACME error.
- After fixing: `veil sync-cert && veil apply`. Hysteria2 starts once the
  certificate exists.

## Nothing connects

1. `veil doctor` on the server — fix anything marked **XX**.
2. With the proxy **off**, can you open `https://www.example.com` (your site
   name) in a browser?
   - Yes → the server is reachable; check the app (next steps).
   - No, but it works from outside China → the IP or name is blocked. Select
     the `CDN` route and move to a new IP ([backup.md](backup.md)).
3. Device clock: REALITY rejects clocks more than 2 minutes off. Turn on
   automatic time.
4. Update the subscription by hand in the app.
5. Only one VPN/proxy app may run at a time.

## Hysteria2 (HY2) slow, dead, or no latency number

- Shadowrocket never shows a latency for Hysteria2 nodes. Select it and load a
  website instead.
- Evening UDP throttling is common; `MEDIA` falls back to REALITY by itself.
- The provider firewall must allow UDP 443 **and** the hop range
  (`veil doctor` shows it).
- If UDP is always throttled, put HY2 last in your profile
  (`"media": ["REALITY", "HY2", "CDN"]`) or try `"hy2_obfs": true`
  ([profiling.md](profiling.md)) — obfuscation hides the QUIC look but makes the
  traffic opaque UDP, which some networks throttle even harder. Test both.

## CDN route: Cloudflare error codes

`veil doctor` reads them for you. In short:

| Code / symptom | Meaning | Fix |
|---|---|---|
| redirect loop | SSL mode is **Flexible** | SSL/TLS → **Full (strict)** |
| 520 | server refused Cloudflare's request — usually its client certificate | `veil origin-pull` (veil backs off if that is the cause) |
| 521 | server refused the connection | provider firewall must allow TCP 443; `veil apply --restart` |
| 522 / 523 | Cloudflare cannot reach the server | check the A record's IP and the firewall |
| 525 | TLS handshake failed | Authenticated Origin Pulls switched off in Cloudflare while veil requires it: switch it on, then `veil origin-pull` |
| 526 | Full (strict) but no valid origin certificate | create one and paste it: `veil` → **13** (same name) or `veil cdn-cert` |
| 403 from Cloudflare | a Cloudflare security rule | Security → turn **Bot Fight Mode** off, check WAF rules |
| WebSocket fails | WebSockets off | Network → **WebSockets: On** |

## Slow in the evening

Almost always the route between your ISP and the VPS. Test each of your lines
(`nexttrace` to the server at 21:00), use the best, lower video resolution, or
choose a VPS with a premium route (CN2 GIA, 9929, CMIN2) for your carrier.

## Subscription will not update

- If every route is down, the app cannot fetch through itself: turn the proxy
  off and update.
- The URLs use the CDN name; `veil doctor` must show the CDN route OK.
- After `veil reset-sub` or `veil cdn-host`, the old URLs stop — re-import.

## Alerts do not arrive

- `veil alert-test` — it says whether the service accepted the message.
- ntfy: the topic in the app must match exactly; outside the proxy ntfy.sh may
  be unreachable from China.
- Bark: re-copy the device URL from the app.

## Locked out of SSH

Five wrong passwords in 10 minutes ban your IP (an hour, longer if repeated).
Wait, use another network, or log in through the provider's web console and run
`fail2ban-client set sshd unbanip YOUR_IP`.

## Maintenance reported a held package

An automatic sing-box or Caddy upgrade failed its checks and was rolled back.
When a newer version is out:

```bash
apt-mark unhold sing-box    # or caddy
veil maint
```

## Asking for help

Share `veil doctor` output and `veil logs -n 100`. Before sharing anything,
remove your IP, domain names, UUIDs, passwords and the subscription token.
