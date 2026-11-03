#!/usr/bin/env bash
# Render every server config into a scratch directory and check it with the
# real sing-box, Caddy and nft. CI runs this; locally it needs those three
# installed (any Debian/Ubuntu machine, as root for nft).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export VEIL_PREFIX PYTHONPATH="$ROOT/server"
VEIL_PREFIX="$(mktemp -d)"
trap 'rm -rf "$VEIL_PREFIX"' EXIT

mkdir -p "$VEIL_PREFIX/opt/veil" "$VEIL_PREFIX/etc/veil/tls"
cp -r "$ROOT/server/decoy" "$VEIL_PREFIX/opt/veil/"
# A throwaway certificate stands in for Let's Encrypt, so Hysteria2 is rendered too.
openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes -days 1 \
  -subj /CN=www.example.com -keyout "$VEIL_PREFIX/etc/veil/tls/site.key" \
  -out "$VEIL_PREFIX/etc/veil/tls/site.crt" 2>/dev/null

python3 -m veil init --site-host www.example.com --cdn-host cdn.example.net --email admin@example.com
python3 -m veil apply --no-system >/dev/null
grep -q '"hy2-in"' "$VEIL_PREFIX/etc/veil/sing-box.json"

sing-box check -c "$VEIL_PREFIX/etc/veil/sing-box.json"
echo "sing-box config OK"
caddy validate --adapter caddyfile --config "$VEIL_PREFIX/etc/caddy/Caddyfile" >/dev/null 2>&1 \
  || caddy validate --adapter caddyfile --config "$VEIL_PREFIX/etc/caddy/Caddyfile"
echo "Caddyfile OK"
nft -c -f "$VEIL_PREFIX/etc/veil/veil.nft"
echo "nftables rules OK"
