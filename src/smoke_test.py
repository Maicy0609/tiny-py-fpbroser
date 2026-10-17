"""Smoke tests for the launcher's platform-independent logic.

Run: python src/smoke_test.py
Windows-only paths (console, registry, Playwright) are exercised on a real
Windows run; everything here works on any platform.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

import browser
import fingerprint
import profiles

FAKE_IPINFO = {
    "ip": "203.0.113.42",
    "country": "US",
    "timezone": "America/New_York",
    "loc": "40.7128,-74.0060",
    "city": "New York",
    "region": "NY",
    "org": "AS64500 Example",
}
SRC_DIR = Path(__file__).resolve().parent


class DisplayHelpersTest(unittest.TestCase):
    def test_mask_ip(self) -> None:
        self.assertEqual(profiles.mask_ip("203.0.113.42"), "203.0.*.*")
        self.assertEqual(profiles.mask_ip("2001:db8:1234::1"), "2001:db8:*")
        self.assertEqual(profiles.mask_ip(profiles.mask_ip("203.0.113.42")), "203.0.*.*")

    def test_safe_name(self) -> None:
        self.assertEqual(profiles.safe_name("US-New York/1"), "US-New-York-1")
        self.assertEqual(profiles.safe_name("--"), "")

    def test_accept_language(self) -> None:
        self.assertEqual(browser.accept_language(["de-DE", "de", "en-US"]), "de-DE,de;q=0.9,en-US;q=0.8")
        self.assertEqual(browser.accept_language(["en-US"]), "en-US")


class FingerprintTest(unittest.TestCase):
    def test_font_names(self) -> None:
        self.assertEqual(
            fingerprint.font_names("Arial Bold Italic (TrueType)"),
            ["Arial Bold Italic", "Arial Bold", "Arial"],
        )
        self.assertEqual(fingerprint.font_names("A & B (TrueType)"), ["A", "B"])
        self.assertEqual(fingerprint.font_names("Yu Gothic UI"), ["Yu Gothic UI"])

    def test_font_allowed(self) -> None:
        allowed = {"segoe ui", "arial"}
        self.assertTrue(fingerprint.font_allowed("Segoe UI Semibold", allowed))
        self.assertFalse(fingerprint.font_allowed("Comic Sans MS", allowed))

    def test_speech_voices(self) -> None:
        voices = fingerprint.build_speech_voices("de-DE")
        self.assertEqual([v["lang"] for v in voices], ["de-DE", "de-DE", "en-US", "en-US", "en-US"])
        self.assertEqual([v["lang"] for v in fingerprint.build_speech_voices("xx-XX")], ["en-US"] * 3)

    def test_media_devices_shape(self) -> None:
        devices = fingerprint.build_media_devices()
        self.assertEqual(len(devices), 7)
        self.assertEqual(
            [d["kind"] for d in devices],
            ["audioinput"] * 3 + ["audiooutput"] * 3 + ["videoinput"],
        )
        self.assertEqual(len({d["device_id"] for d in devices}), 5)  # default/communications repeat
        audio_groups = {d["group_id"] for d in devices if d["kind"] != "videoinput"}
        self.assertEqual(len(audio_groups), 1)

    def test_build_init_script_embeds_config(self) -> None:
        profile = profiles.build_profile(FAKE_IPINFO)
        script = fingerprint.build_init_script(profile, ["Comic Sans MS"])
        self.assertNotIn("__CFG__", script)
        match = re.search(r"const cfg = (\{.*?\});\n", script, re.DOTALL)
        self.assertIsNotNone(match)
        assert match is not None
        cfg = json.loads(match.group(1))
        self.assertEqual(cfg["languages"], profile["browser"]["languages"])
        self.assertEqual(cfg["hidden_fonts"], ["Comic Sans MS"])
        self.assertEqual(cfg["canvas_seed"], profile["fingerprint"]["canvas_seed"])


class ProfileTest(unittest.TestCase):
    def test_build_profile(self) -> None:
        profile = profiles.build_profile(FAKE_IPINFO)
        self.assertEqual(profile["network"]["ip"], "203.0.*.*")
        self.assertEqual(profile["network"]["country"], "US")
        self.assertEqual(profile["browser"]["locale"], "en-US")
        self.assertEqual(profile["browser"]["languages"], ["en-US", "en"])
        self.assertEqual(profile["browser"]["timezone_id"], "America/New_York")
        self.assertEqual(profile["browser"]["geolocation"], {"latitude": 40.7128, "longitude": -74.006, "accuracy": 100})
        self.assertIn("canvas_seed", profile["fingerprint"])
        self.assertEqual(len(profile["fingerprint"]["media_devices"]), 7)
        datetime.fromisoformat(profile["created_at"])

    def test_save_and_upgrade_profile(self) -> None:
        profile = profiles.build_profile(FAKE_IPINFO)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "profile.json"
            profiles.save_profile(path, profile)
            loaded = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(loaded, profile)

            del loaded["fingerprint"]["media_devices"]
            del loaded["fingerprint"]["audio_seed"]
            del loaded["fingerprint"]["speech_voices"]
            profiles.save_profile(path, loaded)
            profiles.upgrade_profile(path, loaded)
            upgraded = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(len(upgraded["fingerprint"]["media_devices"]), 7)
            self.assertIsInstance(upgraded["fingerprint"]["audio_seed"], int)
            self.assertTrue(upgraded["fingerprint"]["speech_voices"])

    def test_list_profiles_skips_invalid_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            valid = profiles.build_profile(FAKE_IPINFO)
            profiles.save_profile(root / "valid.json", valid)
            (root / "broken.json").write_text("{", encoding="utf-8")
            (root / "incomplete.json").write_text('{"name": "x"}', encoding="utf-8")
            with patch.object(profiles, "PROFILE_DIR", root):
                listed = profiles.list_profiles()
            self.assertEqual([path.name for path, _ in listed], ["valid.json"])

    def test_create_profile_writes_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                patch.object(profiles, "PROFILE_DIR", root),
                patch.object(profiles, "fetch_ip_info", return_value=FAKE_IPINFO),
            ):
                path, profile = profiles.create_profile()
            self.assertTrue(path.is_file())
            self.assertEqual(path.parent, root)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), profile)

    def test_decide_network(self) -> None:
        with patch.object(browser, "confirm", return_value=True):
            self.assertEqual(browser.decide_network(None, None), (None, False))
            self.assertEqual(browser.decide_network("http://127.0.0.1:8080", None), ("http://127.0.0.1:8080", True))
            self.assertEqual(browser.decide_network(None, "http://pac/proxy.pac"), (None, True))
        with patch.object(browser, "confirm", return_value=False):
            self.assertEqual(browser.decide_network(None, None), (None, True))
            self.assertEqual(browser.decide_network("http://127.0.0.1:8080", None), (None, True))


class RealChromeTest(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "win32", "real Chrome integration test requires Windows")
    @unittest.skipUnless(os.environ.get("FPBROWSER_E2E") == "1", "set FPBROWSER_E2E=1 to run")
    def test_real_chrome_fingerprint(self) -> None:
        from playwright.sync_api import sync_playwright

        exe = browser.find_browser()
        self.assertTrue(exe.is_file(), exe)
        self.assertTrue(fingerprint.installed_fonts(), "no fonts read from the Windows registry")

        profile = profiles.build_profile(FAKE_IPINFO)
        hidden = fingerprint.hidden_fonts(profile["browser"]["locale"])
        init_script = fingerprint.build_init_script(profile, hidden)

        with tempfile.TemporaryDirectory() as tmp, sync_playwright() as pw:
            context = pw.chromium.launch_persistent_context(
                str(Path(tmp) / "data"),
                executable_path=str(exe),
                headless=True,
                no_viewport=True,
                locale=profile["browser"]["locale"],
                timezone_id=profile["browser"]["timezone_id"],
                geolocation=profile["browser"]["geolocation"],
                args=[
                    f"--lang={profile['browser']['locale']}",
                    "--use-fake-device-for-media-stream",
                    "--force-webrtc-ip-handling-policy=default_public_interface_only",
                    "--disable-blink-features=AutomationControlled",
                ],
                ignore_default_args=["--enable-automation"],
                handle_sigint=False,
                handle_sigterm=False,
                handle_sighup=False,
            )
            errors: list[str] = []

            def record_error(exc: object) -> None:
                errors.append(str(exc))

            try:
                context.add_init_script(init_script)
                page = context.new_page()
                page.on("pageerror", record_error)
                page.goto("about:blank")
                page.set_content("<html><body>smoke</body></html>")
                state: Any = page.evaluate(
                    """async () => {
                      const devices = await navigator.mediaDevices.enumerateDevices();
                      const canvas = document.createElement('canvas');
                      canvas.width = 64;
                      canvas.height = 64;
                      const ctx = canvas.getContext('2d');
                      ctx.fillStyle = '#123456';
                      ctx.fillRect(0, 0, 64, 64);
                      const first = canvas.toDataURL();
                      const second = canvas.toDataURL();
                      const offline = new OfflineAudioContext(1, 1024, 44100);
                      const samples = offline.createBuffer(1, 1024, 44100).getChannelData(0);
                      const gl = document.createElement('canvas').getContext('webgl');
                      let pixels = null;
                      if (gl) {
                        pixels = new Uint8Array(4);
                        gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, pixels);
                      }
                      return {
                        languages: navigator.languages.slice(),
                        language: navigator.language,
                        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
                        voices: speechSynthesis.getVoices().map(v => ({name: v.name, lang: v.lang})),
                        devices: devices.map(d => ({kind: d.kind, label: d.label, deviceId: d.deviceId})),
                        canvasStable: first === second && first.startsWith('data:image/png'),
                        audioNoisy: samples.some(v => v !== 0),
                        webgl: gl !== null,
                        pixels: pixels ? Array.from(pixels) : null,
                      };
                    }"""
                )
                self.assertEqual(errors, [])
                self.assertEqual(state["languages"], profile["browser"]["languages"])
                self.assertEqual(state["language"], profile["browser"]["locale"])
                self.assertEqual(state["timezone"], profile["browser"]["timezone_id"])
                self.assertEqual(state["voices"], profile["fingerprint"]["speech_voices"])
                self.assertEqual(
                    [d["kind"] for d in state["devices"]],
                    ["audioinput", "audiooutput", "videoinput"],
                )
                self.assertTrue(all(d["label"] == "" and d["deviceId"] == "" for d in state["devices"]))
                self.assertTrue(state["canvasStable"])
                self.assertTrue(state["audioNoisy"])
                if state["webgl"]:
                    self.assertEqual(len(state["pixels"]), 4)

                font_state: Any = page.evaluate(
                    """(name) => ({
                      allowed: document.fonts.check('12px "Arial"'),
                      hidden: document.fonts.check('12px ' + JSON.stringify(name)),
                      size: document.fonts.size,
                    })""",
                    hidden[0] if hidden else "Arial",
                )
                self.assertTrue(font_state["allowed"])
                if hidden:
                    self.assertTrue(font_state["hidden"])
                    self.assertEqual(font_state["size"], 0)
            finally:
                context.close()


class EntryPointTest(unittest.TestCase):
    @unittest.skipIf(sys.platform == "win32", "the platform guard exits early only off Windows")
    def test_platform_guard(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SRC_DIR / "fpbrowser.py")],
            cwd=SRC_DIR,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("Windows x64 only", result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
