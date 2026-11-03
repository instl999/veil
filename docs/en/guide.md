# veil — step-by-step guide for beginners

This guide assumes no technical background. Follow the parts in order. Text in
a grey box is something to type or paste — copy it rather than retyping it.
Words in **bold** are buttons or menu items.

Allow about an hour the first time, most of it waiting for Cloudflare and the
VPS provider. The installer itself guides you through every setting and checks
each one with you.

Throughout the guide, these made-up values stand for yours:

| Example in this guide | What it stands for |
|---|---|
| `203.0.113.10` | your server's IP address |
| `www.example.com` | your **site name** (first domain) |
| `static.example.net` | your **CDN name** (second domain) |
| `you@example.com` | your email address |

---

## What you will end up with

- A small rented server abroad (a "VPS") that carries your internet traffic.
- To anyone looking, it is a quiet photography blog with a real certificate.
- An app on each device (computer, phone, router) that you switch on and off
  like a VPN, with three routes that take over from each other automatically.
- Maintenance, security updates and backups that run by themselves every night,
  and an alert on your phone if something needs you.

---

## Part 1 — What you need

| Item | Where to get it | Cost |
|---|---|---|
| A VPS with **Debian 12** (or Ubuntu 22.04/24.04), KVM type, own public IPv4 | a VPS provider (Part 2) | about $5–11 / month |
| **Two** domain names that have nothing to do with each other | any registrar (Namecheap, Porkbun, Cloudflare…) | about $2–10 / year each |
| A free Cloudflare account | <https://dash.cloudflare.com/sign-up> | free |
| An email address | — | — |
| A Windows or Mac computer, and your phone | — | — |

**Why two domains?** veil has a backup route through Cloudflare (the "CDN
route") that keeps working if your network blocks the server's IP. If both
routes used the same domain, anyone who sees both names could tell they belong
together. Cheap domains (`.xyz`, `.top`, `.click`) are fine. Avoid names with
*proxy*, *vpn* or *ss* in them.

One domain is enough to start: the CDN route is optional and you can add it
later (`veil` → **Change CDN domain**).

---

## Part 2 — Rent the VPS

1. Choose a plan with at least **1 GB RAM** and enough monthly traffic (1 TB is
   comfortable). If the provider mentions **CN2 GIA**, **9929** or **CMIN2**,
   those routes are faster from mainland China.
2. Operating system: **Debian 12**.
3. After paying you receive (by email or in the provider's panel):
   - the server's **IP address**, like `203.0.113.10`;
   - the **root password**.

   Write both down somewhere safe (a password manager is ideal).

If the provider's panel has a **firewall** or **security group**, leave it for
now — the installer tells you exactly which ports to open (step 9).

---

## Part 3 — Put your domains on Cloudflare

Do this for **each** domain.

1. Log in to Cloudflare → **Add a domain** → type the domain → choose the
   **Free** plan.
2. Cloudflare shows two **nameservers** (like `ada.ns.cloudflare.com`). At the
   registrar where you bought the domain, find **Nameservers**, choose
   *custom*, and replace the existing ones with these two.
3. Wait for Cloudflare's email saying the domain is **Active** (minutes to a few
   hours).

That is all for now. The DNS records and security settings come during the
installation, where the installer shows exactly what to click and then checks it.

---

## Part 4 — Log in to the server

### Windows

1. Press the **Windows key**, type `powershell`, press **Enter**.
2. Type (with your server's IP):

   ```
   ssh root@203.0.113.10
   ```

3. The first time it asks *Are you sure you want to continue connecting?* —
   type `yes` and press Enter.
4. Type the root password. **Nothing appears while you type — that is normal.**
   Press Enter.

The prompt changes to something like `root@server:~#`. You are now typing on
the server.

### Mac

Open **Terminal** (⌘ + Space, type `Terminal`, Enter) and do steps 2–4 above.

### Optional: log in with a key instead of the password

Password login stays on (Fail2ban blocks anyone guessing it). If you prefer a
key, download this repository as a ZIP from GitHub (**Code → Download ZIP**),
unzip it, and on Windows double-click **`tools\setup-ssh-key.cmd`**. It asks for
the server's IP, copies a new key to the server (you type the password once,
into ssh's own prompt), and afterwards `ssh veil-vps` logs you in without a
password.

If your provider gave you a non-root user, run `sudo -i` after logging in.

---

## Part 5 — Install veil

On the server, paste this one line and press Enter:

```
curl -fsSLO https://github.com/instl999/veil/releases/latest/download/veil-install.sh && bash veil-install.sh
```

Have the Cloudflare dashboard open in your browser, next to the terminal. The
installer now walks you through **11 steps**, in English and Chinese. At any
question you can press **Ctrl+C** to stop and run `bash veil-install.sh` again
later — nothing breaks.

| Step | What the installer asks or shows | What you do |
|---|---|---|
| **1. Before you start** | what you need, your server's IP | press Enter |
| **2. Site name** | the exact DNS record to create | in Cloudflare open the **first** domain → **DNS → Records → Add record**: type **A**, name **www**, IPv4 = your server IP, proxy status **DNS only (grey cloud)** → **Save**. Then type the full name (`www.example.com`). The installer checks it; if it is not visible yet, wait a minute and press **Enter** to check again |
| **3. Backup route** | whether to set up the CDN route, then four things to do in Cloudflare | press Enter (yes), then in the **second** domain: **a)** add record **A**, name **static**, your IP, **Proxied (orange cloud)**; **b)** **SSL/TLS → Overview → Configure → Full (strict)**; **c)** **SSL/TLS → Origin Server → Create Certificate** → keep defaults → **Create**, and leave that page open; **d)** **SSL/TLS → Origin Server → Authenticated Origin Pulls: On**. Type the CDN name (`static.example.net`). For the certificate choose **1**, paste the **Origin Certificate** box, then the **Private Key** box (on Windows, if it warns about pasting several lines, choose **Paste anyway**) |
| **4. Email** | an address for certificate notices | type your email |
| **5. Options** | Hysteria2 (fast UDP route), system updates first | press Enter twice (yes, yes) |
| **6. Alerts** | how to get problem alerts on your phone | choose **1** (ntfy): install the free **ntfy** app, tap **+**, subscribe to the topic name it shows, press Enter. iPhone users who want alerts that also work inside China can choose **2** (Bark) |
| **7. Review** | a summary and what is switched on automatically | press Enter to start; it takes 3–10 minutes |
| **8. Check everything** | every check with OK or a fix | if something is marked **XX**, do what it says and press Enter to check again. It also confirms Authenticated Origin Pulls and sends a test alert — answer whether it arrived |
| **9. Provider firewall** | the exact ports to allow | only if your provider has a firewall panel: allow those ports |
| **10. Devices** | each device's subscription link and how to import it | type a device name (e.g. `shadowrocket`) to show its QR code, or press Enter |
| **11. Backup** | a backup file and the command to copy it | copy it to your computer (below) |

If the installer says a restart is needed at the end, press Enter and log in
again after a minute.

### Copy the backup to your computer (step 11)

The installer prints a line like this. Run it **on your computer** — open a new
PowerShell or Terminal window; do not log in to the server:

```
scp root@203.0.113.10:/root/veil-backup-20260101-120000.tar.gz .
```

The file lands in the folder that window is in (usually your user folder). It
contains your keys: keep it private, e.g. in a password manager or on an
encrypted drive. With it you can move to a new server in 15 minutes without
touching your devices.

---

## Part 6 — Set up your devices

Install the app yourself from its official page, then import **that device's
subscription link** (each device has its own, because each imitates its own
browser). On the server, `veil` → **1** shows the links and **2** shows a QR
code.

| Device | App | Import |
|---|---|---|
| Windows, Mac | [Clash Verge Rev](https://github.com/clash-verge-rev/clash-verge-rev/releases) | **Profiles** → paste the `windows` or `mac` link → **Import** → click the profile. Then **Settings → System Proxy** (browsers) or **TUN Mode** (all apps) |
| Android (also Windows/Mac/Linux) | [FlClash](https://github.com/chen08209/FlClash/releases) | `veil` → **3. Add a device** → fingerprint **android**, client **flclash** → scan the QR code with the phone camera |
| iPhone, iPad | Shadowrocket (paid, non-China App Store) | `veil` → **2** → `shadowrocket` → scan it in Shadowrocket. Then **Settings → Subscription → Auto update: On** — needed, because the passwords change every month |
| Router (OpenWrt) | OpenClash | **Config Subscribe → Add** → the `router` link, auto update on; Meta core; Fake-IP mode |

Details for each app: [clients.md](clients.md).

**Run only one proxy or VPN app at a time** on a device.

---

## Part 7 — Everyday use

- Switch the app on when you need it. Chinese websites never go through the
  server, so leaving it on is fine too.
- Apps refresh their subscription every 12 hours; credential changes and
  improvements arrive by themselves.
- Every night the server renews certificates, changes passwords monthly,
  installs updates (restarting at 06:00 China time if an update needs it),
  makes a backup and checks itself. If something is wrong, your phone gets an
  alert.

### The `veil` menu

Log in to the server and type `veil`:

| You want to… | Choose |
|---|---|
| See the subscription links / a QR code | **1** / **2** |
| Add or remove a phone, tablet or laptop | **3** / **4** |
| A link leaked — make new ones | **5** |
| Check that everything is fine | **6. Check everything** |
| Change alerts, rotation, upgrades | **8. Settings** |
| Make a backup to copy to your computer | **11. Backups** |
| Update veil | **15** |
| Leave | **0**, then `exit` to log out |

All menu items and commands: [operations.md](operations.md).

---

## Part 8 — When something goes wrong

First log in and run:

```
veil doctor
```

It checks everything and, for every problem, says what to do. Common cases:

| What you see | What to do |
|---|---|
| `HY2` shows no number in **Shadowrocket**, but works when selected | Normal — Shadowrocket's latency test does not measure Hysteria2. If websites load, it works. |
| `HY2` shows no number or times out | Normal on some networks in the evening (UDP is throttled). The app switches to `REALITY` or `CDN` by itself. |
| Nothing works at home, but works on mobile data | Your home line may block the server's IP. The `CDN` route still works; make sure the app uses it. Then plan a move ([backup.md](backup.md)). |
| `ssh` does not connect | Try from mobile data. Five wrong passwords block your IP for an hour — wait, or use the provider's web console. |
| The installer stopped with an error | Read the message, fix the cause, run `bash veil-install.sh` again. It is safe to repeat. |

Everything else: [troubleshooting.md](troubleshooting.md).

---

## Part 9 — Keep it safe

These are the things only you can do; everything else is automatic (see
[security.md](security.md)):

- Keep the subscription links private. If one leaks: `veil` → **5**.
- Keep the backup file on your computer, privately. Make a new one after big
  changes (`veil` → **11**).
- Keep alerts on (`veil` → **8**) and auto update on in Shadowrocket.
- Keep the Cloudflare settings from step 3: grey cloud for the site name;
  orange cloud, Full (strict) and Authenticated Origin Pulls for the CDN name.
- If the provider has a firewall panel, allow only the ports from step 9.

---

## Words you may meet

| Word | Meaning |
|---|---|
| VPS | a small rented server in a data centre |
| SSH | the secure way to type commands on the server |
| DNS record | tells the internet which IP a name belongs to |
| Grey / orange cloud | in Cloudflare: the name points straight at your server / goes through Cloudflare |
| Subscription link | a secret web address your app reads its settings from |
| REALITY / HY2 / CDN | the three routes: main (TCP), fast (UDP), backup (via Cloudflare) |
| Fail2ban | blocks computers that keep guessing the SSH password |
| BBR | a speed setting for the server's connections |
| Origin certificate | a certificate from Cloudflare that proves your server to Cloudflare |
| Authenticated Origin Pulls | Cloudflare proves itself to your server, so the server answers nobody else on the CDN name |
