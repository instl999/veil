# Personalizing with the profiler

The profiler learns what *your* normal traffic looks like and tunes veil to
match it. It runs on your own computer, never on the server.

## Privacy

Recorded per connection: protocol, server port, whether the server is your VPS,
start time (minute), duration, byte/packet counts, packet-size and gap
histograms, the first 16 packet sizes, and the TLS ClientHello's JA4
fingerprint (lists of cipher and extension numbers).

**Never recorded:** IP addresses, hostnames/SNI, DNS names, URLs, cookies,
payload. Connections to your LAN are skipped. Files stay on your computer; only
the small `profile.json` goes to the server. Delete the `.jsonl` captures when
you are done.

## What it tunes

| Setting | Evidence used |
|---|---|
| TLS fingerprint per device | your browser's JA4 vs. the JA4 of your REALITY connections |
| Hysteria2 hop interval | how long your ordinary QUIC flows live (25th–75th percentile) |
| Video route order | QUIC's share of your normal traffic: ≥ 15 % → HY2 first, else REALITY first |

It also reports your busiest hours and what share of bytes went to the VPS.

## Requirements

- Python 3.9+
- Wireshark 4.2 or newer (for JA4). On Windows include Npcap and run the
  terminal **as Administrator**. On macOS run with `sudo`, or install
  Wireshark's ChmodBPF helper.
- Optional: `pip install scikit-learn` for the combined self-test score.

## Step 1 — baseline (proxy OFF), about a week

Turn the proxy off and use the device normally (Douyin, Bilibili, domestic
sites). Run on each computer:

```bash
python veil_profiler.py interfaces                  # find your Wi-Fi/Ethernet interface
python veil_profiler.py capture --device mac --mode baseline --hours 24 -i en0
```

Repeat on a few different days (morning, evening, weekend). Each run appends a
`flows-<device>-baseline-<time>.jsonl` file.

**iPhone:** connect it to the Mac by cable and create a mirror interface
with Apple's `rvictl -s <UDID>` (part of Xcode's command-line tools), then
capture on `rvi0` with `--device iphone`.
**Router:** run `tcpdump -i br-lan -w /tmp/lan.pcap` on OpenWrt for a while,
copy the file off, then
`python veil_profiler.py capture --device router --mode baseline --read lan.pcap`
and delete the pcap (it contains full packets).

## Step 2 — proxied sample (proxy ON), 1–2 hours

Turn the proxy on and use it the way you normally would (browsing, YouTube):

```bash
python veil_profiler.py capture --device mac --mode proxied --server www.example.com --hours 2 -i en0
```

## Step 3 — fit a profile

Get the current profile from the server first, so device names match:

```bash
ssh root@YOUR_VPS veil profile show > current.json
python veil_fit.py --baseline "flows-*-baseline-*.jsonl" --proxied "flows-*-proxied-*.jsonl" \
                   --current current.json --out profile.json --report profile-report.md
```

Read `profile-report.md`: every change comes with the reason for it.

## Step 4 — apply it

```bash
scp profile.json root@YOUR_VPS:/root/
ssh root@YOUR_VPS veil profile apply /root/profile.json
```

Or open `veil` on the server, choose **Apply personalization profile** and
paste the contents of `profile.json`.

Clients pick it up on their next subscription update. Refresh by hand if you
are impatient.

## Step 5 — self-test

```bash
python veil_selftest.py --baseline "flows-*-baseline-*.jsonl" --proxied "flows-*-proxied-*.jsonl"
```

Each feature gets an AUC: about 0.5 means it blends in with your normal HTTPS
traffic, near 1.0 means it stands out. Expect duration and bytes per flow to
stand out — that is inherent to any tunnel. What you can improve:

- **first_packets_mean / mean_pkt_up stands out:** the TLS fingerprint does not
  match; re-run steps 2–4 (the fitter tries the next preset each time).
- **bytes_down stands out strongly:** too much is going through the proxy;
  check that domestic and game traffic stays DIRECT.

Repeat steps 2–5 after any change, and every few months, because browsers and
your own habits change. The self-test compares against your own traffic only;
the GFW sees a whole country's traffic, so treat a good score as necessary, not
sufficient.
