#!/usr/bin/env python3
"""veil self-test - how distinguishable are your proxy flows from your own
ordinary HTTPS/QUIC flows, using the same flow metadata a censor could see?

  python veil_selftest.py --baseline flows-*-baseline-*.jsonl --proxied flows-*-proxied-*.jsonl

For each feature it reports an AUC: 0.5 means the feature cannot tell the two
apart, 1.0 (or 0.0) means it separates them perfectly. With scikit-learn
installed it also trains a random forest on all features combined.

This is a rough self-check against YOUR traffic only. The GFW compares against
a whole country's traffic plus IP reputation, so a good score here is
necessary, not sufficient.
"""
from __future__ import annotations

import argparse
import glob
import json
import math

FEATURES = {
    "duration": lambda f: math.log1p(f["dur"]),
    "bytes_down": lambda f: math.log1p(f["dn_b"]),
    "bytes_up": lambda f: math.log1p(f["up_b"]),
    "up_down_ratio": lambda f: math.log1p(f["up_b"]) - math.log1p(f["dn_b"]),
    "mean_pkt_up": lambda f: f["up_b"] / max(f["up_p"], 1),
    "mean_pkt_down": lambda f: f["dn_b"] / max(f["dn_p"], 1),
    "share_full_size_down": lambda f: sum(f["dn_hist"][-2:]) / max(f["dn_p"], 1),
    "share_tiny_up": lambda f: f["up_hist"][0] / max(f["up_p"], 1),
    "share_gaps_under_5ms": lambda f: sum(f["gap_hist"][:2]) / max(sum(f["gap_hist"]), 1),
    "share_gaps_over_1s": lambda f: sum(f["gap_hist"][-2:]) / max(sum(f["gap_hist"]), 1),
    "first_packets_mean": lambda f: sum(abs(x) for x in f["first"]) / max(len(f["first"]), 1),
}

ADVICE = {
    "duration": "Tunnels live far longer than page loads. Inherent to proxies; keeping only "
                "blocked sites on the proxy (and rotating via hop interval for HY2) limits it.",
    "bytes_down": "Each proxy flow carries much more data than a typical site visit. Splitting "
                  "video onto HY2 and keeping Steam/domestic traffic DIRECT reduces it.",
    "bytes_up": "Upload volume per flow differs - often from video calls or uploads via proxy.",
    "up_down_ratio": "Upload/download balance differs from your normal browsing.",
    "mean_pkt_up": "Packet sizes differ. Vision padding helps on REALITY; check the fingerprint.",
    "mean_pkt_down": "Packet sizes differ. Usually driven by what you watch, not the protocol.",
    "share_full_size_down": "Proportion of full-size packets differs (bulk transfer pattern).",
    "share_tiny_up": "Proportion of tiny upstream packets (ACK/keepalive pattern) differs.",
    "share_gaps_under_5ms": "Packet timing differs at short scales.",
    "share_gaps_over_1s": "Idle-gap pattern differs (long idle tunnels).",
    "first_packets_mean": "The opening packet sizes differ - check the TLS fingerprint match.",
}


def load(patterns):
    flows = []
    for pattern in patterns:
        for path in glob.glob(pattern) or [pattern]:
            with open(path, encoding="utf-8") as fh:
                flows += [json.loads(l) for l in fh if l.strip()]
    return flows


def auc(pos: list[float], neg: list[float]) -> float:
    """Mann-Whitney U based ROC AUC, ties counted half."""
    ranked = sorted([(v, 1) for v in pos] + [(v, 0) for v in neg])
    rank_sum, i = 0.0, 0
    while i < len(ranked):
        j = i
        while j < len(ranked) and ranked[j][0] == ranked[i][0]:
            j += 1
        avg = (i + j + 1) / 2
        rank_sum += avg * sum(1 for k in range(i, j) if ranked[k][1])
        i = j
    n1, n0 = len(pos), len(neg)
    return (rank_sum - n1 * (n1 + 1) / 2) / (n1 * n0)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--baseline", nargs="+", required=True)
    ap.add_argument("--proxied", nargs="+", required=True)
    ap.add_argument("--min-bytes", type=int, default=20_000,
                    help="ignore flows smaller than this (default 20 kB)")
    a = ap.parse_args()

    big = lambda f: f["up_b"] + f["dn_b"] >= a.min_bytes
    normal = [f for f in load(a.baseline) if not f["proxy"] and f["port"] == 443 and big(f)]
    tunnel = [f for f in load(a.proxied) if f["proxy"] and big(f)]
    if len(normal) < 30 or len(tunnel) < 10:
        raise SystemExit(f"need >=30 baseline and >=10 proxy flows; have {len(normal)} and {len(tunnel)}")

    print(f"Comparing {len(tunnel)} proxy flows with {len(normal)} ordinary HTTPS/QUIC flows.\n")
    rows = []
    for name, fn in FEATURES.items():
        score = auc([fn(f) for f in tunnel], [fn(f) for f in normal])
        rows.append((abs(score - 0.5), name, score))
    rows.sort(reverse=True)
    print(f"{'feature':<24} {'AUC':>5}  verdict")
    for dist, name, score in rows:
        verdict = "blends in" if dist < 0.1 else "noticeable" if dist < 0.25 else "stands out"
        print(f"{name:<24} {score:5.2f}  {verdict}")

    print("\nWhat the top differences mean:")
    for dist, name, _ in rows[:3]:
        if dist >= 0.1:
            print(f"- {name}: {ADVICE[name]}")

    try:
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.model_selection import cross_val_score
    except ImportError:
        print("\n(pip install scikit-learn for a combined multi-feature score)")
        return
    X = [[fn(f) for fn in FEATURES.values()] for f in tunnel + normal]
    y = [1] * len(tunnel) + [0] * len(normal)
    clf = RandomForestClassifier(n_estimators=200, class_weight="balanced", random_state=1)
    scores = cross_val_score(clf, X, y, cv=5, scoring="roc_auc")
    print(f"\nCombined random-forest AUC (5-fold): {scores.mean():.2f} "
          "- expect this to be high; a single machine-learning model on flow metadata "
          "can usually spot long-lived tunnels. Use it to compare settings over time, "
          "not as a pass/fail grade.")


if __name__ == "__main__":
    main()
