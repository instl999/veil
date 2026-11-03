"""Offline tests: render every config into a scratch prefix and check the results.

    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import tarfile
import sys
import tempfile
import time
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
TMP = tempfile.mkdtemp(prefix="veil-test-")
os.environ["VEIL_PREFIX"] = TMP
os.environ["VEIL_FAKE_KEYPAIR"] = "cHJpdmF0ZS1rZXktZm9yLXRlc3Rz:cHVibGljLWtleS1mb3ItdGVzdHM"
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "profiler"))

from veil import cli, core, doctor, menu, render_client, render_server, system, yamlout  # noqa: E402,F401
from veil.core import P  # noqa: E402

try:
    import yaml  # optional: verifies the hand-written emitter
except ImportError:
    yaml = None


def fresh_state(hy2_cert: bool = True) -> dict:
    for f in (P.SITE_CRT, P.SITE_KEY):
        if hy2_cert:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text("dummy")
        elif f.exists():
            f.unlink()
    return core.new_state("www.example.com", "assets.example.com", "me@example.com")


class RenderTests(unittest.TestCase):
    def test_singbox_layout(self):
        cfg = json.loads(render_server.render_singbox(fresh_state()))
        tags = {i["tag"]: i for i in cfg["inbounds"]}
        self.assertEqual(set(tags), {"reality-in", "hy2-in", "cdn-in"})
        reality = tags["reality-in"]["tls"]["reality"]
        self.assertEqual(reality["handshake"], {"server": "127.0.0.1", "server_port": 8443})
        self.assertTrue(tags["hy2-in"]["ignore_client_bandwidth"])
        self.assertEqual(tags["cdn-in"]["listen"], "127.0.0.1")
        self.assertNotIn("obfs", tags["hy2-in"])

    def test_abuse_rules(self):
        rules = json.loads(render_server.render_singbox(fresh_state()))["route"]["rules"]
        self.assertEqual(rules[0], {"action": "sniff"})
        self.assertIn({"protocol": "bittorrent", "action": "reject"}, rules)
        self.assertIn({"port": [25], "action": "reject"}, rules)

    def test_no_access_to_local_services(self):
        rules = json.loads(render_server.render_singbox(fresh_state()))["route"]["rules"]
        # Names are resolved before the private-IP check, so "localhost" and names
        # pointing at 127.0.0.1 cannot reach Caddy or other loopback services.
        resolve = rules.index({"action": "resolve"})
        self.assertLess(resolve, rules.index({"ip_is_private": True, "action": "reject"}))
        self.assertIn({"domain_suffix": ["localhost"], "action": "reject"}, rules[:resolve])
        text = render_server.render_caddyfile(fresh_state(), False)
        self.assertIn("\tadmin unix//var/lib/caddy/admin.sock\n", text)

    def test_cdn_host_not_on_port_80(self):
        state = fresh_state()
        text = render_server.render_caddyfile(state, True)
        self.assertIn("http://www.example.com {", text)
        self.assertNotIn(f"http://{state['cdn']['host']}", text)

    def test_origin_pull_modes(self):
        state = fresh_state()
        text = render_server.render_caddyfile(state, cdn_cert_present=True)
        self.assertIn("mode verify_if_given", text)
        self.assertIn(f"trust_pool file {P.PULL_CA.as_posix()}", text)
        self.assertIn(f"handle /{state['sub_token']}-origin-pull {{", text)
        self.assertEqual(text.count("{"), text.count("}"))
        state["cdn"]["origin_pull"] = True
        self.assertIn("mode require_and_verify", render_server.render_caddyfile(state, False))
        self.assertIn(P.PULL_CA, system.render_all(state))
        self.assertIn("BEGIN CERTIFICATE", system.PULL_CA_SRC.read_text())

    def test_origin_pull_check(self):
        state = fresh_state()
        seen = []

        def blocked(opener, req, timeout):
            seen.append(req.get_header("User-agent"))
            raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, None)

        with mock.patch("urllib.request.OpenerDirector.open", blocked):
            err = system.origin_pull(state)
        # Cloudflare blocks the default Python agent; a failed check is a problem, not "off".
        self.assertTrue(seen[0].startswith("Mozilla/"))
        self.assertIn("could not reach", err)
        self.assertFalse(state["cdn"]["origin_pull"])

    def test_origin_pull_reverts_when_requiring_breaks_cdn(self):
        state = fresh_state()
        state["cdn"]["origin_pull"] = True
        # Cloudflare's certificate stopped verifying: unreachable while required,
        # reachable again once veil stops requiring it.
        answers = iter([None, True])
        with mock.patch.object(system, "origin_pull_seen", lambda s: next(answers)), \
             mock.patch.object(system, "apply"), mock.patch.object(system.time, "sleep"):
            err = system.origin_pull(state)
        self.assertIn("stopped requiring", err)
        self.assertFalse(state["cdn"]["origin_pull"])
        # Unreachable either way: not the cause, so the protection stays on.
        state["cdn"]["origin_pull"] = True
        with mock.patch.object(system, "origin_pull_seen", lambda s: None), \
             mock.patch.object(system, "apply"), mock.patch.object(system.time, "sleep"):
            err = system.origin_pull(state)
        self.assertIn("not reachable", err)
        self.assertTrue(state["cdn"]["origin_pull"])

    def test_upgrade_not_held_when_apt_is_busy(self):
        calls = []

        def fake_run(cmd, check=True, capture=True):
            calls.append(cmd)
            out = {"dpkg-query": "1.0", "apt-cache": "  Candidate: 1.1\n"}.get(cmd[0], "")
            failed = cmd[0] == "apt-get"
            return subprocess.CompletedProcess(cmd, 100 if failed else 0, out,
                                               "E: Could not get lock" if failed else "")

        with mock.patch.object(system, "run", fake_run), \
             mock.patch.object(system.shutil, "which", lambda b: "/bin/true"), \
             mock.patch.object(system.shutil, "copy2"):
            err = system.safe_upgrade(fresh_state(), "caddy", "caddy", "caddy")
        self.assertIn("will retry", err)
        self.assertIn("DPkg::Lock::Timeout=900", next(c for c in calls if c[0] == "apt-get"))
        self.assertFalse(any(c[:2] == ["apt-mark", "hold"] for c in calls))

    def test_hy2_waits_for_certificate(self):
        state = fresh_state(hy2_cert=False)
        cfg = json.loads(render_server.render_singbox(state))
        self.assertNotIn("hy2-in", {i["tag"] for i in cfg["inbounds"]})
        self.assertNotIn("Alt-Svc", render_server.render_caddyfile(state, False))
        self.assertNotIn("HY2", render_client.share_links(state))

    def test_caddyfile(self):
        state = fresh_state()
        text = render_server.render_caddyfile(state, cdn_cert_present=False)
        self.assertIn("https_port 8443", text)
        self.assertIn("https://www.example.com {", text)
        self.assertIn(f"handle_path /{state['sub_token']}/*", text)
        # Subscriptions are served on both hosts and handed out via the CDN host.
        self.assertEqual(text.count("import subscription"), 2)
        self.assertTrue(render_client.subscription_urls(state)["mac"].startswith(
            f"https://{state['cdn']['host']}/{state['sub_token']}/"))
        self.assertIn(f"@tunnel path {state['cdn']['path']}", text)
        self.assertIn("tls internal", text)
        self.assertIn('Alt-Svc `h3=":443"; ma=86400`', text)
        self.assertEqual(text.count("{"), text.count("}"))
        with_cert = render_server.render_caddyfile(state, cdn_cert_present=True)
        self.assertIn("veil-cdn.crt", with_cert)

    def test_nft(self):
        state = fresh_state()
        text = render_server.render_nft(state)
        self.assertIn(f"udp dport {state['hy2']['hop']} redirect to :443", text)

    def test_mihomo_profiles(self):
        state = fresh_state()
        text = render_client.render_mihomo(state, "mac")
        self.assertIn('client-fingerprint: "safari"', text)
        self.assertIn('hop-interval: "20-40"', text)
        if yaml:
            cfg = yaml.safe_load(text)
            names = [p["name"] for p in cfg["proxies"]]
            self.assertEqual(names, ["REALITY", "HY2", "CDN"])
            groups = {g["name"]: g for g in cfg["proxy-groups"]}
            self.assertEqual(groups["MEDIA"]["proxies"], ["HY2", "REALITY", "CDN"])
            self.assertEqual(cfg["proxies"][0]["reality-opts"]["short-id"],
                             state["reality"]["short_ids"][0])
            self.assertTrue(cfg["dns"]["respect-rules"])

    def test_share_links(self):
        state = fresh_state()
        links = render_client.share_links(state)
        self.assertTrue(links["REALITY"].startswith(f"vless://{state['reality']['uuid']}@www.example.com:443?"))
        self.assertIn("security=reality", links["REALITY"])
        self.assertIn("mport=", links["HY2"])
        self.assertIn("type=ws", links["CDN"])
        sub = base64.b64decode(render_client.shadowrocket_subscription(state)).decode()
        self.assertEqual(len(sub.strip().splitlines()), 3)

    def test_flclash_import_links(self):
        state = fresh_state()
        self.assertEqual(render_client.import_links(state), {})
        state["profile"]["devices"]["pixel"] = {"fingerprint": "android", "client": "flclash"}
        links = render_client.import_links(state)
        self.assertEqual(list(links), ["pixel"])
        url = render_client.subscription_urls(state)["pixel"]
        self.assertEqual(links["pixel"],
                         "flclash://install-config?url=" + url.replace(":", "%3A").replace("/", "%2F"))

    def test_write_configs_and_stale_cleanup(self):
        state = fresh_state()
        changed = system.write_configs(state, validate=False)
        self.assertIn(P.SINGBOX, changed)
        self.assertTrue((P.SUB / "mihomo-router.yaml").exists())
        del state["profile"]["devices"]["router"]
        system.write_configs(state, validate=False)
        self.assertFalse((P.SUB / "mihomo-router.yaml").exists())
        self.assertEqual(system.write_configs(state, validate=False), set())


class RotationTests(unittest.TestCase):
    def test_rotation_keeps_old_values_during_grace(self):
        state = fresh_state()
        old_uuid, old_path = state["reality"]["uuid"], state["cdn"]["path"]
        core.rotate(state, ["creds", "path", "short_id", "hop"], grace_days=1)
        self.assertNotEqual(state["reality"]["uuid"], old_uuid)
        self.assertEqual(len(state["reality"]["short_ids"]), 2)
        cfg = json.loads(render_server.render_singbox(state))
        reality_users = [u["uuid"] for u in cfg["inbounds"][0]["users"]]
        self.assertEqual(reality_users, [state["reality"]["uuid"], old_uuid])
        caddy = render_server.render_caddyfile(state, False)
        self.assertIn(f"@retired path {old_path}", caddy)
        self.assertEqual(render_server.render_nft(state).count("redirect"), 2)

        later = time.time() + 2 * 86400
        removed = core.expire_retired(state, now=later)
        self.assertEqual(removed, 6)
        self.assertEqual(len(state["reality"]["short_ids"]), 1)

    def test_profile_validation(self):
        good = core.validate_profile({"hop_interval": "15-30",
                                      "devices": {"mac": {"fingerprint": "safari"}}})
        self.assertEqual(good["hop_interval"], "15-30")
        self.assertEqual(good["devices"]["mac"]["client"], "clash-verge")
        for bad in ({"hop_interval": "fast"},
                    {"devices": {"Mac Book": {"fingerprint": "safari"}}},
                    {"devices": {"mac": {"fingerprint": "netscape"}}},
                    {"routes": {"browse": ["REALITY", "REALITY"], "media": ["HY2"]}},
                    {"healthcheck_interval": 5}):
            with self.assertRaises(core.VeilError):
                core.validate_profile(bad)


class OperationsTests(unittest.TestCase):
    def test_alerts_ntfy_and_bark(self):
        state = fresh_state()
        sent = []

        def fake_fetch(url, timeout=15, redirects=True, data=None, headers=None):
            sent.append((url, data, headers))
            return 200, {}, b"", ""

        with mock.patch.object(system.net, "fetch", fake_fetch):
            self.assertFalse(system.notify(state, "x"))  # no URL set: nothing sent
            self.assertTrue(system.notify(state, "hello", "https://ntfy.sh/veil-abc"))
            self.assertTrue(system.notify(state, "hello", "https://api.day.app/Key123/"))
        (url1, body1, h1), (url2, body2, h2) = sent
        self.assertEqual(body1, b"hello")
        self.assertIn("www.example.com", h1["Title"])
        self.assertEqual(url2, "https://api.day.app/Key123")
        self.assertEqual(json.loads(body2)["body"], "hello")

    def test_notify_url_must_be_https(self):
        fresh_state()
        core.save_state(fresh_state())
        self.assertEqual(cli.main(["set", "notify_url", "http://ntfy.sh/x"]), 1)
        self.assertEqual(cli.main(["set", "notify_url", "https://ntfy.sh/x"]), 0)
        self.assertEqual(core.load_state()["maint"]["notify_url"], "https://ntfy.sh/x")

    def test_auto_backup_keeps_fourteen(self):
        core.save_state(fresh_state())
        for day in range(20):
            system.auto_backup(now=1_700_000_000 + day * 86400)
        backups = system.list_backups()
        self.assertEqual(len(backups), system.AUTO_BACKUP_KEEP)
        with tarfile.open(backups[-1]) as tar:
            self.assertIn("etc/veil/state.json", tar.getnames())

    def test_versions_and_update_check(self):
        self.assertGreater(system._vtuple("0.10.0"), system._vtuple("0.9.9"))
        with mock.patch.object(system, "latest_release", lambda: "99.0.0"):
            self.assertEqual(system.update_available(), "99.0.0")
        with mock.patch.object(system, "latest_release", lambda: None):
            self.assertIsNone(system.update_available())

    def test_doctor_explains_cloudflare_errors(self):
        state = fresh_state()

        def run_cdn(status, headers=None):
            with mock.patch.object(doctor.net, "behind_cloudflare", lambda h: True), \
                 mock.patch.object(doctor.net, "fetch",
                                   lambda *a, **k: (status, headers or {}, b"", "")):
                return doctor.check_cdn(state, "203.0.113.10")

        self.assertIn("526", run_cdn(526)[1].en)
        flexible = run_cdn(308, {"Location": f"https://{state['cdn']['host']}/"})[1]
        self.assertIn("Flexible", flexible.en)
        self.assertEqual(flexible.level, doctor.FAIL)
        text = doctor.render({"cdn": run_cdn(521)}, color=False)
        self.assertIn("1 problem(s)", text)

    def test_caddy_never_touches_system_trust(self):
        self.assertIn("\tskip_install_trust\n", render_server.render_caddyfile(fresh_state(), False))


class YamlTests(unittest.TestCase):
    def test_emitter_shapes(self):
        text = yamlout.dump({"a": [{"b": 1, "c": {"d": ["x", True]}}], "e": {}, "f": []})
        expected = 'a:\n  - b: 1\n    c:\n      d:\n        - "x"\n        - true\ne: {}\nf: []\n'
        self.assertEqual(text, expected)


def synthetic_flow(device, mode, proxy, proto="tcp", dur=5.0, dn=200_000, ja4="t13d1516h2_aaa_bbb"):
    return {"v": 1, "device": device, "mode": mode, "proto": proto, "port": 443, "proxy": proxy,
            "minute": 0, "hour": 21, "dur": dur, "up_b": dn // 20, "dn_b": dn, "up_p": 40,
            "dn_p": 150, "up_hist": [30, 5, 5, 0, 0, 0, 0, 0, 0, 0],
            "dn_hist": [10, 0, 0, 0, 0, 0, 0, 20, 120, 0], "gap_hist": [50, 50, 40, 20, 10, 10, 5, 3, 1],
            "first": [517, -1400, -1400, 80], "ja4": ja4}


class ProfilerToolTests(unittest.TestCase):
    def test_fit_and_selftest_run(self):
        work = Path(tempfile.mkdtemp(prefix="veil-fit-"))
        base = [synthetic_flow("mac", "baseline", False, dur=3 + i % 7) for i in range(60)]
        base += [synthetic_flow("mac", "baseline", False, proto="udp", dur=20 + i, dn=2_000_000, ja4="")
                 for i in range(40)]
        prox = [synthetic_flow("mac", "proxied", True, dur=600 + i, dn=50_000_000, ja4="t13d1517h2_ccc_ddd")
                for i in range(15)]
        (work / "b.jsonl").write_text("\n".join(json.dumps(f) for f in base))
        (work / "p.jsonl").write_text("\n".join(json.dumps(f) for f in prox))

        out = subprocess.run([sys.executable, str(ROOT / "profiler" / "veil_fit.py"),
                              "--baseline", str(work / "b.jsonl"), "--proxied", str(work / "p.jsonl"),
                              "--out", str(work / "profile.json"), "--report", str(work / "r.md")],
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        profile = json.loads((work / "profile.json").read_text())
        self.assertEqual(profile["routes"]["media"][0], "HY2")
        self.assertEqual(profile["devices"]["mac"]["fingerprint"], "ios")  # mismatch -> next try
        lo, hi = map(int, profile["hop_interval"].split("-"))
        self.assertTrue(10 <= lo < hi <= 180)
        core.validate_profile(profile)  # the server must accept what the fitter writes

        out = subprocess.run([sys.executable, str(ROOT / "profiler" / "veil_selftest.py"),
                              "--baseline", str(work / "b.jsonl"), "--proxied", str(work / "p.jsonl")],
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("duration", out.stdout)


if __name__ == "__main__":
    unittest.main()
