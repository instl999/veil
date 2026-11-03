# Backup and recovery

## What a backup contains

`/etc/veil/state.json` (every key, password and setting), the Cloudflare origin
certificate and key, and the cover website. That is everything needed to
rebuild the server with the **same** subscription links, so your devices need no
changes. Treat backups like passwords.

## Automatic backups (on the server)

Every night veil writes `/var/lib/veil/backups/veil-YYYYMMDD.tar.gz`
(root-only) and keeps the last 14. They let you undo a bad change, but they
disappear with the server, so also keep a copy on your computer.

```bash
veil backup --list
```

## A copy on your computer

On the server: `veil` → **11. Backups → Make a backup** (or `veil backup`). It
prints the command to run **on your computer**, for example:

```bash
scp root@203.0.113.10:/root/veil-backup-20260101-120000.tar.gz .
```

Store it privately (password manager attachment, encrypted drive). Make a new
one after changing the CDN domain, resetting links or rotating `all`. Then delete
the copy on the server: `rm /root/veil-backup-*.tar.gz`.

## Undo a change on the same server

```bash
veil backup --list
veil restore /var/lib/veil/backups/veil-20260101.tar.gz
veil apply --restart
```

## Move to a new server (or a new IP)

Use this when the server's IP is blocked, the provider fails, or you change
provider. While you move, apps keep working through the CDN route.

1. Rent a new VPS (Debian 12) and log in.
2. Copy your backup to it from your computer:

   ```bash
   scp veil-backup-20260101-120000.tar.gz root@198.51.100.20:/root/
   ```

3. On the new server:

   ```bash
   curl -fsSLO https://github.com/instl999/veil/releases/latest/download/veil-install.sh
   bash veil-install.sh --restore veil-backup-20260101-120000.tar.gz
   ```

4. In Cloudflare, change **both** A records to the new IP (site name stays grey,
   CDN name stays orange). The settings in Cloudflare stay as they are.
5. Wait a few minutes, then run `veil doctor` on the new server. Apps reconnect
   by themselves: every profile uses names, not IPs.
6. Optional: `veil rotate all`, then cancel the old VPS.

## No backup?

Install fresh (`bash veil-install.sh`), with the same or new domains, then
import the new subscription links on every device. Nothing else is lost: veil
keeps no other data.
