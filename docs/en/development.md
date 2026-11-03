# Development and releases

## Repository layout

```
install.sh              entry point for git installs (runs server/install.sh)
server/
  install.sh            the installer and setup wizard (bash)
  veil/                 the `veil` tool (Python 3.9+, standard library only)
    core.py             paths, state, secrets, rotation, profile validation
    render_server.py    sing-box, Caddyfile and nftables generation
    render_client.py    mihomo profiles, share links, subscription URLs
    system.py           apply, health, maintenance, upgrades, alerts, backups
    doctor.py           `veil doctor`: checks with explanations and fixes
    net.py              HTTP, DNS-over-HTTPS and WebSocket probes
    cli.py, menu.py     command line and interactive menu
  systemd/              service and timer units
  decoy/                the cover website
profiler/               runs on your own computer: capture, fit, self-test
tests/                  offline unit tests
tools/
  build.py              builds dist/veil-install.sh (single-file installer)
  validate_configs.sh   checks generated configs with real sing-box/Caddy/nft
  check_sanitized.py    refuses secrets and personal data (files and history)
  setup-ssh-key.*       optional SSH key setup from Windows
docs/en, docs/zh        documentation (keep both languages in step)
.github/workflows/      CI and releases
```

## Everyday commands

```bash
python -m unittest discover -s tests -v    # unit tests (any OS)
python tools/build.py                      # dist/veil-install.sh + .sha256
shellcheck -S warning server/install.sh install.sh tools/validate_configs.sh
sudo bash tools/validate_configs.sh        # on Debian with sing-box, caddy, nft
python tools/check_sanitized.py --history  # before every push
```

CI (`.github/workflows/ci.yml`) runs all of these on every push, including the
real sing-box/Caddy/nft validation.

## Keeping the repository clean

Never commit real IPs, domains, keys, certificates, subscription links, logs or
captures. Use these placeholders:

| Kind | Placeholder |
|---|---|
| server IP | `203.0.113.10` (also `198.51.100.x`, `192.0.2.x`) |
| site name / CDN name | `www.example.com` / `static.example.net` |
| email | `you@example.com` |
| token, UUID | `<token>`, `<uuid>` |

`tools/check_sanitized.py` blocks the generic cases. For your own details, create
`.sanitize-denylist` in the repository root with one item per line (server IPs,
domains, email, hostnames). It is in `.gitignore` and stays on your computer;
the check also fails if it is ever tracked. To run the check before every
commit:

```bash
printf '#!/bin/sh\nexec python tools/check_sanitized.py\n' > .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

If something sensitive was ever committed, deleting it in a new commit is not
enough: rewrite the history (e.g. `git filter-repo`), force-push, and rotate the
leaked secret.

## Releasing

1. Update `__version__` in `server/veil/__init__.py` and add a section to
   `CHANGELOG.md`.
2. Commit, then tag and push:

   ```bash
   git tag v0.3.0 && git push origin main v0.3.0
   ```

3. The release workflow checks that the tag matches the version, runs the tests
   and the leak check, builds `veil-install.sh` and its `.sha256`, and publishes
   them with the changelog section as release notes.

Servers learn about the release in their next nightly check and you update
with `veil update`.

## Using your own fork

Change `REPO` in `server/veil/__init__.py` (or set `VEIL_REPO=owner/name` in the
environment) and the release URLs in the docs. Everything else is
repository-independent.

## Conventions

- Every message a user sees is in English and Chinese.
- Generated files are never edited by hand; change the renderer and the state.
- New settings get a default in `core.py` and are filled in by `load_state`, so
  old installations keep working after `veil update`.
- Installer functions must not end with a failing test or `a && b` (with
  `set -e` that aborts the caller); use `if`.
