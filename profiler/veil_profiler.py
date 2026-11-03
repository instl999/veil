#!/usr/bin/env python3
"""veil profiler - records flow-level traffic METADATA on your own device.

What is recorded, per connection ("flow"):
  protocol (tcp/udp), server port, whether the server is your veil VPS,
  start minute and hour, duration, byte and packet counts in each direction,
  histograms of packet sizes and gaps, the first 16 packet sizes, and the
  JA4 fingerprint of the TLS ClientHello (cipher/extension lists only).

What is NOT recorded: any IP address, hostname/SNI, DNS name, URL, cookie or
payload byte. Flows to LAN/private addresses are skipped entirely.

Requires Wireshark's `tshark` (Windows: Npcap + run as Administrator;
macOS: run with sudo or install Wireshark's ChmodBPF helper).

  python veil_profiler.py interfaces
  python veil_profiler.py capture --device mac --mode baseline --hours 24
  python veil_profiler.py capture --device mac --mode proxied --server www.example.com --hours 2
  python veil_profiler.py capture --device iphone --mode baseline --read iphone.pcap
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

SIZE_BINS = (100, 200, 400, 600, 800, 1000, 1200, 1400, 1500)      # bytes, last bin is ">"
GAP_BINS = (0.001, 0.005, 0.02, 0.05, 0.1, 0.5, 1.0, 5.0)           # seconds
IDLE_TIMEOUT = 60.0
FIRST_N = 16

BASE_FIELDS = ["frame.time_epoch", "frame.len", "ip.src", "ip.dst", "ipv6.src", "ipv6.dst",
               "tcp.srcport", "tcp.dstport", "udp.srcport", "udp.dstport"]
JA4_FIELD = "tls.handshake.ja4"


def find_tshark() -> str:
    found = shutil.which("tshark")
    if found:
        return found
    for cand in (r"C:\Program Files\Wireshark\tshark.exe",
                 "/Applications/Wireshark.app/Contents/MacOS/tshark"):
        if os.path.exists(cand):
            return cand
    sys.exit("tshark not found - install Wireshark (https://www.wireshark.org/download.html)")


def supports_ja4(tshark: str) -> bool:
    out = subprocess.run([tshark, "-G", "fields"], capture_output=True, text=True).stdout
    return f"\t{JA4_FIELD}\t" in out


def _bin(value: float, bins: tuple) -> int:
    for i, edge in enumerate(bins):
        if value <= edge:
            return i
    return len(bins)


class Flow:
    __slots__ = ("proto", "port", "proxy", "client", "start", "last", "up_b", "dn_b", "up_p",
                 "dn_p", "up_hist", "dn_hist", "gap_hist", "first", "ja4")

    def __init__(self, proto, port, proxy, client, ts):
        self.proto, self.port, self.proxy, self.client = proto, port, proxy, client
        self.start = self.last = ts
        self.up_b = self.dn_b = self.up_p = self.dn_p = 0
        self.up_hist = [0] * (len(SIZE_BINS) + 1)
        self.dn_hist = [0] * (len(SIZE_BINS) + 1)
        self.gap_hist = [0] * (len(GAP_BINS) + 1)
        self.first: list[int] = []
        self.ja4 = ""

    def add(self, ts: float, size: int, up: bool) -> None:
        if self.up_p + self.dn_p:
            self.gap_hist[_bin(max(0.0, ts - self.last), GAP_BINS)] += 1
        self.last = ts
        if up:
            self.up_b += size; self.up_p += 1
            self.up_hist[_bin(size, SIZE_BINS)] += 1
        else:
            self.dn_b += size; self.dn_p += 1
            self.dn_hist[_bin(size, SIZE_BINS)] += 1
        if len(self.first) < FIRST_N:
            self.first.append(size if up else -size)

    def record(self, device: str, mode: str) -> dict:
        lt = time.localtime(self.start)
        return {
            "v": 1, "device": device, "mode": mode, "proto": self.proto, "port": self.port,
            "proxy": self.proxy, "minute": int(self.start // 60) * 60, "hour": lt.tm_hour,
            "dur": round(self.last - self.start, 3), "up_b": self.up_b, "dn_b": self.dn_b,
            "up_p": self.up_p, "dn_p": self.dn_p, "up_hist": self.up_hist,
            "dn_hist": self.dn_hist, "gap_hist": self.gap_hist, "first": self.first,
            "ja4": self.ja4,
        }


def is_local(addr: str) -> bool:
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return True
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast


def resolve_servers(names: list[str]) -> set[str]:
    ips: set[str] = set()
    for name in names:
        for info in socket.getaddrinfo(name, 443, proto=socket.IPPROTO_TCP):
            ips.add(info[4][0])
    return ips


def capture(args) -> None:
    tshark = find_tshark()
    fields = list(BASE_FIELDS)
    ja4 = supports_ja4(tshark)
    if ja4:
        fields.append(JA4_FIELD)
    else:
        print("note: this Wireshark has no JA4 field (needs 4.2+); TLS fingerprints skipped")
    servers = resolve_servers(args.server) if args.server else set()
    if args.mode == "proxied" and not servers:
        sys.exit("--mode proxied needs --server (your site host or VPS IP)")

    cmd = [tshark, "-l", "-n", "-Q", "-T", "fields", "-E", "separator=/t", "-E", "occurrence=f"]
    if args.read:
        cmd += ["-r", args.read, "-Y", "tcp or udp"]
    else:
        cmd += ["-f", "tcp or udp"]
        if args.interface:
            cmd += ["-i", args.interface]
    for f in fields:
        cmd += ["-e", f]

    out_path = Path(args.out or f"flows-{args.device}-{args.mode}-{time.strftime('%Y%m%d-%H%M')}.jsonl")
    out = open(out_path, "a", encoding="utf-8")
    flows: dict[tuple, Flow] = {}
    written = 0
    deadline = time.time() + args.hours * 3600
    last_sweep = time.time()

    def flush(pred) -> None:
        nonlocal written
        for key in [k for k, f in flows.items() if pred(f)]:
            f = flows.pop(key)
            if f.up_p + f.dn_p >= 3:
                out.write(json.dumps(f.record(args.device, args.mode)) + "\n")
                written += 1
        out.flush()

    print(f"capturing to {out_path} for {args.hours}h - press Ctrl+C to stop early.")
    print("Only sizes, timings and TLS fingerprints are stored; no addresses or content.")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True, bufsize=1)
    signal.signal(signal.SIGINT, lambda *_: proc.terminate())
    try:
        for line in proc.stdout:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < len(BASE_FIELDS):
                continue
            ts, size = float(parts[0]), int(parts[1] or 0)
            src, dst = parts[2] or parts[4], parts[3] or parts[5]
            if parts[6]:
                proto, sport, dport = "tcp", int(parts[6]), int(parts[7])
            elif parts[8]:
                proto, sport, dport = "udp", int(parts[8]), int(parts[9])
            else:
                continue
            # The server side is the endpoint with the lower (service) port.
            if (sport, src) < (dport, dst):
                server, sport_s, client, up = src, sport, (dst, dport), False
            else:
                server, sport_s, client, up = dst, dport, (src, sport), True
            if is_local(server):
                continue
            key = (proto, server, sport_s, client)
            flow = flows.get(key)
            if flow is None:
                flow = flows[key] = Flow(proto, sport_s, server in servers, client, ts)
            flow.add(ts, size, up)
            if ja4 and len(parts) > 10 and parts[10] and not flow.ja4 and up:
                flow.ja4 = parts[10]
            now = time.time()
            if now - last_sweep > 10:
                flush(lambda f: ts - f.last > IDLE_TIMEOUT)
                last_sweep = now
            if now > deadline and not args.read:
                proc.terminate()
                break
    finally:
        flush(lambda f: True)
        out.close()
        proc.wait(timeout=10)
    print(f"done: {written} flows written to {out_path}")


def interfaces(_args) -> None:
    subprocess.run([find_tshark(), "-D"])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("interfaces", help="list capture interfaces").set_defaults(fn=interfaces)
    c = sub.add_parser("capture", help="record flow metadata")
    c.add_argument("--device", required=True, help="label, e.g. mac / windows / iphone / router")
    c.add_argument("--mode", required=True, choices=["baseline", "proxied"],
                   help="baseline = proxy OFF (normal use); proxied = proxy ON")
    c.add_argument("--server", action="append", default=[],
                   help="your site host or VPS IP (marks proxy flows); repeatable")
    c.add_argument("--interface", "-i", help="interface number or name from `interfaces`")
    c.add_argument("--read", "-r", metavar="PCAP",
                   help="read a capture file instead (e.g. from the router); delete the pcap afterwards")
    c.add_argument("--hours", type=float, default=24)
    c.add_argument("--out")
    c.set_defaults(fn=capture)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
