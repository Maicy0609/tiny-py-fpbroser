"""Chrome discovery, WebRTC policy and the Playwright browser session."""

import json
import os
import shutil
import urllib.request
from pathlib import Path
from typing import Any

from config import DATA_DIR, IPINFO_URL, WEBRTC_POLICY_DIRECT, WEBRTC_POLICY_PROXIED
from console import CTRL_C, confirm, info, is_closing, ok, poll_key, warn
from dnscheck import describe, query_probe
from fingerprint import build_init_script, hidden_fonts
from profiles import mask_ip


def find_browser() -> Path:
    import winreg

    candidates: list[Path] = []
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(
                root, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"
            ) as key:
                candidates.append(Path(winreg.QueryValueEx(key, "")[0]))
        except OSError:
            pass
    for var in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        base = os.environ.get(var)
        if base:
            for vendor in (r"Google\Chrome", "Chromium"):
                candidates.append(Path(base) / vendor / "Application" / "chrome.exe")
    found = shutil.which("chrome")
    if found:
        candidates.append(Path(found))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise RuntimeError("No Chrome or Chromium installation found.")


def accept_language(languages: list[str]) -> str:
    return ",".join(
        lang if i == 0 else f"{lang};q={1 - i / 10:.1f}" for i, lang in enumerate(languages)
    )


def system_proxy() -> str | None:
    """Proxy in effect for this user (env vars or Windows system settings), if any."""
    proxies = urllib.request.getproxies()
    return proxies.get("https") or proxies.get("http") or proxies.get("all")


def system_pac() -> str | None:
    """PAC script URL from the Windows Internet Settings, if one is configured."""
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
        ) as key:
            return str(winreg.QueryValueEx(key, "AutoConfigURL")[0]) or None
    except OSError:
        return None


def webrtc_policy(proxy: str | None, pac: str | None) -> str:
    """WebRTC IP-handling policy: keep UDP inside the proxy whenever one may be in use.

    This never redirects traffic. Chrome follows the system proxy settings on its own;
    this only decides how tightly WebRTC has to hold on to the exit IP, so that STUN
    cannot reveal the real address behind a proxy or VPN.
    """
    if proxy or pac:
        kinds = [f"manual ({proxy.partition('://')[0] if '://' in proxy else 'http'})"] if proxy else []
        if pac:
            kinds.append("PAC script")
        info(f"System proxy detected: {' + '.join(kinds)}. WebRTC UDP is restricted to the proxy.")
        return WEBRTC_POLICY_PROXIED
    # VPN/TUN and app-level proxies are invisible here, so ask instead of guessing.
    if confirm("No system proxy detected. Is this connection direct (no VPN or other proxy)?"):
        info("Direct connection: WebRTC limited to the public interface, local IPs hidden.")
        return WEBRTC_POLICY_DIRECT
    warn("Assuming a proxy or VPN may be in use: WebRTC UDP is restricted (WebRTC calls may not connect).")
    return WEBRTC_POLICY_PROXIED


def check_exit(context: Any, profile: dict[str, Any]) -> None:
    """Ask ipinfo.io through the browser itself, so PAC, VPN and TUN exits are seen as well."""
    from playwright.sync_api import Error as PlaywrightError

    page = context.new_page()
    try:
        page.goto(IPINFO_URL, timeout=10000)
        seen = json.loads(page.inner_text("body"))
    except (PlaywrightError, ValueError) as exc:
        warn(f"Could not verify the browser's exit IP: {exc}")
        return
    finally:
        page.close()
    country, timezone = profile["network"]["country"], profile["browser"]["timezone_id"]
    if seen.get("country") != country or seen.get("timezone") != timezone:
        warn(
            f"Browser exit is {mask_ip(str(seen.get('ip', '')))} ({seen.get('country')}, "
            f"{seen.get('timezone')}) but the profile expects ({country}, {timezone})."
        )
        warn("Use a matching proxy, or create a new profile.")
    else:
        ok("Browser exit matches the profile region.")


def check_dns() -> None:
    """Report which resolver the outside world sees, and warn about leaks.

    A local proxy client usually answers A/AAAA queries itself, but TXT and
    friends are forwarded upstream. If that upstream is on the local network,
    the resolver discloses the real subnet through an EDNS client subnet and
    the profile's exit region no longer holds for DNS.
    """
    result = query_probe()
    if result.resolver is None and "failed" in result.raw:
        warn(f"Could not check the DNS path: {result.raw}")
        return
    if result.leaked:
        warn(f"DNS leak: {describe(result)}")
        warn(
            "The resolver disclosed your real network. Point the proxy client's DNS "
            "upstream at the proxy (mihomo: bind nameserver with '#<node>'), or the "
            "profile's region is not consistent across DNS and HTTP."
        )
    elif result.resolved_remotely:
        ok(f"DNS path is clean: {describe(result)}")
    else:
        warn(f"DNS resolved by a local resolver: {describe(result)}")
        warn("No client subnet was attached, but confirm the resolver leaves through the proxy.")


def run_browser(profile: dict[str, Any], exe: Path) -> None:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeout
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright is missing. Run: pip install playwright") from exc

    browser = profile["browser"]
    data_dir = DATA_DIR / profile["name"]
    data_dir.mkdir(parents=True, exist_ok=True)
    hidden = hidden_fonts(browser["locale"])
    info(f"Fonts: hiding {len(hidden)} installed fonts that a stock {browser['locale']} Windows lacks.")
    policy = webrtc_policy(system_proxy(), system_pac())
    args = [
        f"--lang={browser['locale']}",
        "--start-maximized",
        f"--force-webrtc-ip-handling-policy={policy}",
        "--disable-blink-features=AutomationControlled",
        "--use-fake-device-for-media-stream",
    ]
    with sync_playwright() as pw:
        try:
            context = pw.chromium.launch_persistent_context(
                str(data_dir),
                executable_path=str(exe),
                headless=False,
                no_viewport=True,
                locale=browser["locale"],
                timezone_id=browser["timezone_id"],
                geolocation=browser["geolocation"],
                extra_http_headers={"Accept-Language": accept_language(browser["languages"])},
                args=args,
                ignore_default_args=["--enable-automation"],
                handle_sigint=False,
                handle_sigterm=False,
                handle_sighup=False,
            )
        except PlaywrightError as exc:
            raise RuntimeError(f"Browser failed to start (profile already running?): {exc}") from exc
        try:
            context.add_init_script(build_init_script(profile, hidden))
            ok(f"Browser started, profile data: {data_dir}")
            check_exit(context, profile)
            check_dns()
            info("Press Ctrl+C in this console to close the browser and exit.")
            while not is_closing():
                if poll_key() == CTRL_C and confirm("Close the browser and exit?"):
                    return
                try:
                    context.wait_for_event("close", timeout=200)
                except PlaywrightTimeout:
                    continue
                info("Browser was closed.")
                return
        finally:
            try:
                context.close()  # graceful close flushes cookies to disk
            except PlaywrightError:
                pass

