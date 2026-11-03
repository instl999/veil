#!/usr/bin/env python3
"""veil fit - turns profiler captures into a personalization profile.

  python veil_fit.py --baseline flows-mac-baseline-*.jsonl \
                     [--proxied flows-mac-proxied-*.jsonl] \
                     [--current profile.json] --out profile.json --report report.md

Then on the server:  veil profile apply profile.json

What it personalizes, and from which evidence:
  * TLS fingerprint per device - the browser JA4 seen in that device's baseline
    is compared with the JA4 of its REALITY connections in proxied captures.
  * Hysteria2 hop interval - matched to how long ordinary QUIC (UDP 443) flows
    live on your network, so each UDP 5-tuple has a typical lifetime.
  * Route order for video - Hysteria2 first only if QUIC is a normal share of
    your traffic; otherwise REALITY (TCP) first, so UDP volume stays in character.
"""
from __future__ import annotations

import argparse
import copy
import glob
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

DEFAULT_PROFILE = {
    "schema": "veil-profile/1",
    "devices": {
        "mac": {"fingerprint": "safari", "client": "clash-verge"},
        "windows": {"fingerprint": "chrome", "client": "clash-verge"},
        "iphone": {"fingerprint": "ios", "client": "shadowrocket"},
        "router": {"fingerprint": "chrome", "client": "openclash"},
    },
    "routes": {"browse": ["REALITY", "CDN", "HY2"], "media": ["HY2", "REALITY", "CDN"]},
    "hop_interval": "20-40",
    "healthcheck_interval": 900,
    "hy2_obfs": False,
}

# Fingerprints to try next when a device's REALITY JA4 does not match its browser.
NEXT_TRY = {
    "safari": ["safari", "ios", "chrome"],
    "ios": ["ios", "safari", "chrome"],
    "chrome": ["chrome", "edge", "random"],
    "edge": ["edge", "chrome", "random"],
    "firefox": ["firefox", "chrome", "random"],
}
QUIC_SHARE_FOR_HY2 = 0.15


def load(patterns: list[str]) -> list[dict]:
    flows = []
    for pattern in patterns:
        paths = glob.glob(pattern) or [pattern]
        for path in paths:
            with open(path, encoding="utf-8") as fh:
                flows += [json.loads(line) for line in fh if line.strip()]
    return flows


def pct(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    return values[min(len(values) - 1, int(q * len(values)))]


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def fit(baseline: list[dict], proxied: list[dict], current: dict) -> tuple[dict, list[str]]:
    profile = copy.deepcopy(current)
    notes: list[str] = []
    base = [f for f in baseline if not f["proxy"]]
    if not base:
        sys.exit("no baseline flows - capture with --mode baseline first")

    total = sum(f["up_b"] + f["dn_b"] for f in base)
    quic = [f for f in base if f["proto"] == "udp" and f["port"] == 443]
    quic_bytes = sum(f["up_b"] + f["dn_b"] for f in quic)
    quic_share = quic_bytes / total if total else 0.0
    notes.append(f"Baseline: {len(base)} flows, {human(total)}; QUIC (UDP 443) share "
                 f"{quic_share:.0%} ({human(quic_bytes)}).")

    # --- hop interval from QUIC flow lifetimes
    lifetimes = [f["dur"] for f in quic if f["dur"] >= 2 and f["up_b"] + f["dn_b"] > 50_000]
    if len(lifetimes) >= 20:
        lo = int(min(max(pct(lifetimes, 0.25), 10), 120))
        hi = int(min(max(pct(lifetimes, 0.75), lo + 5), 180))
        profile["hop_interval"] = f"{lo}-{hi}"
        notes.append(f"Hop interval {lo}-{hi}s: the middle half of your {len(lifetimes)} "
                     f"substantial QUIC flows lasted that long.")
    else:
        notes.append(f"Only {len(lifetimes)} substantial QUIC flows - kept hop interval "
                     f"{profile['hop_interval']}s. Capture longer for a fitted value.")

    # --- route order for video
    if quic_share >= QUIC_SHARE_FOR_HY2:
        profile["routes"]["media"] = ["HY2", "REALITY", "CDN"]
        notes.append(f"QUIC is {quic_share:.0%} of your normal traffic (>= {QUIC_SHARE_FOR_HY2:.0%}), "
                     "so video goes over Hysteria2 first; heavy UDP is normal on your line.")
    else:
        profile["routes"]["media"] = ["REALITY", "HY2", "CDN"]
        notes.append(f"QUIC is only {quic_share:.0%} of your normal traffic, so video goes over "
                     "REALITY (TCP) first and Hysteria2 is a fallback.")

    # --- per-device TLS fingerprint
    base_ja4 = defaultdict(Counter)
    for f in base:
        if f["proto"] == "tcp" and f["port"] == 443 and f.get("ja4"):
            base_ja4[f["device"]][f["ja4"]] += 1
    prox_ja4 = defaultdict(Counter)
    for f in proxied:
        if f["proxy"] and f["proto"] == "tcp" and f.get("ja4"):
            prox_ja4[f["device"]][f["ja4"]] += 1

    for device in sorted(set(base_ja4) | set(prox_ja4)):
        dev = profile["devices"].get(device)
        if dev is None:
            notes.append(f"Device '{device}' is not in the profile; add it with "
                         f"`veil device add {device} --fingerprint chrome` and re-run.")
            continue
        top = [j for j, _ in base_ja4[device].most_common(3)]
        mine = prox_ja4[device].most_common(1)
        if not top:
            notes.append(f"{device}: no browser TLS handshakes captured (Wireshark 4.2+ needed for JA4).")
            continue
        if not mine:
            notes.append(f"{device}: browser JA4 {top[0]}. Run a short --mode proxied capture to "
                         f"verify the '{dev['fingerprint']}' preset matches.")
            continue
        got = mine[0][0]
        if got in top:
            notes.append(f"{device}: REALITY handshake matches one of your browser's own "
                         f"fingerprints ({got}). Keeping '{dev['fingerprint']}'.")
        else:
            options = [o for o in NEXT_TRY.get(dev["fingerprint"], ["chrome"]) if o != dev["fingerprint"]]
            nxt = options[0] if options else "chrome"
            notes.append(f"{device}: REALITY handshake {got} does not match your browser "
                         f"({', '.join(top)}). Switching '{dev['fingerprint']}' -> '{nxt}'; "
                         "capture --mode proxied again to confirm.")
            dev["fingerprint"] = nxt

    # --- context for the report
    by_hour = Counter()
    for f in base:
        by_hour[f["hour"]] += f["up_b"] + f["dn_b"]
    busy = [h for h, _ in by_hour.most_common(5)]
    notes.append(f"Busiest hours (local): {', '.join(f'{h:02d}:00' for h in sorted(busy))}.")
    if proxied:
        pb = sum(f["up_b"] + f["dn_b"] for f in proxied if f["proxy"])
        pt = sum(f["up_b"] + f["dn_b"] for f in proxied) or 1
        notes.append(f"Proxied capture: {pb / pt:.0%} of bytes went to the VPS. Lower is "
                     "stealthier - keep domestic sites and Steam downloads DIRECT.")
    return profile, notes


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--baseline", nargs="+", required=True)
    ap.add_argument("--proxied", nargs="*", default=[])
    ap.add_argument("--current", help="current profile (from `veil profile show`)")
    ap.add_argument("--out", default="profile.json")
    ap.add_argument("--report", default="profile-report.md")
    a = ap.parse_args()

    current = DEFAULT_PROFILE
    if a.current:
        current = {**DEFAULT_PROFILE, **json.loads(Path(a.current).read_text(encoding="utf-8"))}
    profile, notes = fit(load(a.baseline), load(a.proxied), current)
    Path(a.out).write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
    report = ["# veil profile report", "", *[f"- {n}" for n in notes], "",
              "## Resulting profile", "", "```json", json.dumps(profile, indent=2), "```", ""]
    Path(a.report).write_text("\n".join(report), encoding="utf-8")
    print("\n".join(f"- {n}" for n in notes))
    print(f"\nwrote {a.out} and {a.report}. Apply on the server with: veil profile apply {a.out}")


if __name__ == "__main__":
    main()
