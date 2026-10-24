"""Browser profile creation, upgrade, storage and selection."""

import json
import re
import secrets
import urllib.request
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from config import COUNTRY_LOCALE, IPINFO_URL, PROFILE_DIR, REQUIRED_KEYS
from console import info, ok, read_line, warn
from fingerprint import build_media_devices, build_speech_voices


def mask_ip(ip: str) -> str:
    """Hide the host part of an IP for display and storage (idempotent)."""
    if ":" in ip:
        return ":".join(ip.split(":")[:2]) + ":*"
    return ".".join(ip.split(".")[:2] + ["*", "*"])


def safe_name(text: str) -> str:
    """File/directory-safe name: only letters, digits, '.', '_' and '-' (no spaces)."""
    return re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-")


def fetch_ip_info() -> dict[str, str]:
    request = urllib.request.Request(IPINFO_URL, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.load(response)
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"ipinfo.io request failed: {exc}") from exc
    missing = [k for k in ("ip", "country", "timezone", "loc") if k not in data]
    if missing:
        raise RuntimeError(f"ipinfo.io response lacks fields: {', '.join(missing)}")
    return {k: str(v) for k, v in data.items()}




def build_profile(ipinfo: dict[str, str]) -> dict[str, Any]:
    country = ipinfo["country"]
    locale = COUNTRY_LOCALE.get(country, "en-US")
    base = locale.split("-")[0]
    languages = [locale, base]
    if base != "en":
        languages += ["en-US", "en"]
    latitude, longitude = (float(v) for v in ipinfo["loc"].split(","))
    timezone = ipinfo["timezone"]
    return {
        "name": safe_name(f"{country}-{timezone}-{secrets.token_hex(3)}"),
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "network": {
            "ip": mask_ip(ipinfo["ip"]),
            "city": ipinfo.get("city", ""),
            "region": ipinfo.get("region", ""),
            "country": country,
            "org": ipinfo.get("org", ""),
        },
        "browser": {
            "timezone_id": timezone,
            "locale": locale,
            "languages": languages,
            "geolocation": {"latitude": latitude, "longitude": longitude, "accuracy": 100},
        },
        "fingerprint": {
            "canvas_seed": secrets.randbits(32),
            "audio_seed": secrets.randbits(32),
            "media_devices": build_media_devices(),
            "speech_voices": build_speech_voices(locale),
        },
    }


def save_profile(path: Path, profile: dict[str, Any]) -> None:
    path.write_text(json.dumps(profile, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def upgrade_profile(path: Path, profile: dict[str, Any]) -> None:
    """Fill fingerprint fields added after the profile was created, and save them."""
    fingerprint = profile["fingerprint"]
    defaults: dict[str, Callable[[], Any]] = {
        "canvas_seed": lambda: secrets.randbits(32),
        "audio_seed": lambda: secrets.randbits(32),
        "media_devices": build_media_devices,
        "speech_voices": lambda: build_speech_voices(profile["browser"]["locale"]),
    }
    missing = [key for key in defaults if key not in fingerprint]
    for key in missing:
        fingerprint[key] = defaults[key]()
    if missing:
        save_profile(path, profile)
        info(f"Profile upgraded with new fingerprint fields: {', '.join(missing)}")


def create_profile() -> tuple[Path, dict[str, Any]]:
    info("Querying ipinfo.io for the current exit IP ...")
    ipinfo = fetch_ip_info()
    info(
        f"Exit IP {mask_ip(ipinfo['ip'])}: {ipinfo.get('city', '?')}, {ipinfo.get('region', '?')}, "
        f"{ipinfo['country']}, timezone {ipinfo['timezone']}"
    )
    profile = build_profile(ipinfo)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    path = PROFILE_DIR / f"{profile['name']}.json"
    save_profile(path, profile)
    ok(f"Profile saved: {path}")
    return path, profile


def list_profiles() -> list[tuple[Path, dict[str, Any]]]:
    profiles: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(PROFILE_DIR.glob("*.json")):
        try:
            profile = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            profile = None
        if not isinstance(profile, dict) or not REQUIRED_KEYS <= profile.keys():
            warn(f"Skipping invalid profile file: {path.name}")
            continue
        profiles.append((path, profile))
    return profiles


def choose_profile() -> tuple[Path, dict[str, Any]]:
    while True:
        profiles = list_profiles()
        info("Select a browser profile:")
        for i, (_, p) in enumerate(profiles, 1):
            net = p["network"]
            print(
                f"  {i}. {p['name']}  {mask_ip(net['ip'])}  {net['city']}, {net['country']}  "
                f"{p['browser']['timezone_id']}  created {p['created_at']}"
            )
        print("  n. Create a new profile from the current exit IP")
        print("  q. Quit")
        answer = read_line("> ").lower()
        if answer == "q":
            raise SystemExit(0)
        if answer == "n":
            return create_profile()
        if answer.isdigit() and 1 <= int(answer) <= len(profiles):
            path, profile = profiles[int(answer) - 1]
            return path, profile
        warn("Invalid choice.")

