# Setting up clients

Each device gets its **own subscription URL**, because each device imitates the
TLS fingerprint of its own browser (Safari on a Mac, Chrome on Windows, iOS on an
iPhone). You install the apps yourself; veil gives you the URLs. On the server:
`veil` → **1** (links) or **2** (QR code), or:

```bash
veil links              # all URLs and share links
veil links --qr mac     # QR code for one device: mac, windows, iphone, router, shadowrocket
```

With the CDN route set up, the URLs go through Cloudflare, so updates still
arrive if the server's IP is blocked. Keep them private — anyone holding one
can use your server. Apps refresh them every 12 hours, which is how credential
rotation and profile changes reach your devices.

Default devices: `mac` (Safari), `windows` (Chrome), `iphone` (iOS),
`router` (Chrome), plus the `shadowrocket` link for Shadowrocket.

## What you will see in the app

| Group | Purpose | Default |
|---|---|---|
| `PROXY` | everything foreign | `AUTO` |
| `AUTO` | fallback chain for browsing | REALITY → CDN → HY2 |
| `MEDIA` | YouTube | HY2 → REALITY → CDN (personalized by the profiler) |
| `GAMES` | Steam content servers | DIRECT |

Fallback groups switch automatically when a route stops working. Mainland sites
and apps always go DIRECT.

## Windows and macOS — Clash Verge Rev

1. Install Clash Verge Rev from its
   [GitHub releases](https://github.com/clash-verge-rev/clash-verge-rev/releases).
2. **Profiles** → paste the `windows` (or `mac`) URL → **Import** → click the
   profile to activate it.
3. **Settings → System Proxy: on** for browsers only, or **TUN Mode: on** for
   every app (recommended; allow the service it offers to install).
4. On first start it downloads rule databases; give it a minute.

Do not edit the downloaded profile — it is replaced on every update. Use Clash
Verge's own merge/rule editors for local additions.

## Android, Windows, macOS, Linux — FlClash

[FlClash](https://github.com/chen08209/FlClash) uses the same mihomo core and
the same profiles; it is the easiest choice on Android.

1. Install FlClash from its GitHub releases page.
2. On the server: `veil` → **3. Add a device**, fingerprint `android` (phone) or
   `chrome`/`safari` (computer), client `flclash`.
3. Scan the QR code it shows with the phone camera — FlClash opens and imports
   the profile in one step. Or in FlClash: **Profiles → + → URL** and paste.
4. Start it from the dashboard; allow the VPN prompt on Android.

## iPhone and iPad — Shadowrocket

Shadowrocket is a paid app in non-mainland App Stores (you need a non-China
Apple ID).

1. On the server: `veil` → **2** → `shadowrocket` (or `veil links --qr shadowrocket`).
2. In Shadowrocket tap the scan icon (top left) and scan it, or **+ → Type:
   Subscribe** and paste the `shadowrocket.txt` URL.
3. **Settings → Subscription → Auto update: on.** Required: credentials rotate
   every 30 days and the old ones stop after 7.
4. **Config → Rule** routing mode, so mainland apps stay direct.

Notes: Shadowrocket's latency test shows no number for `veil-HY2` — that is
normal; select it and open a website to test. Shadowrocket has no automatic
fallback between nodes: if REALITY fails, pick `veil-CDN`.

Alternative: **Stash** (also non-mainland App Store) takes the `iphone` URL
directly and keeps the same groups, rules and automatic fallback.

## OpenWrt — OpenClash

1. **Plugin Settings → Version update:** install the **Meta (mihomo)** core.
2. **Config Subscribe → Add:** the `router` URL, auto update on.
3. **Plugin Settings → Operation mode:** Fake-IP (TUN or mixed). Keep the DNS
   settings from the profile.
4. Start OpenClash; `PROXY`, `AUTO`, `MEDIA` and `GAMES` should appear.

Devices on your home Wi-Fi are then covered by the router; turn their own apps
off at home to avoid proxying twice.

## Adding or changing a device

`veil` → **3. Add a device** / **4. Remove a device**, or:

```bash
veil device add ipad --fingerprint ios --client shadowrocket
veil device rm windows
veil device list
```

Clients: clash-verge, flclash, openclash, shadowrocket, stash, other.
Fingerprints: chrome, safari, ios, firefox, edge, android, 360, qq, random. The
[profiler](profiling.md) can tell you which one really matches each device.
