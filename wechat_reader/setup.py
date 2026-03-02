"""Environment diagnostics and setup guidance."""

from __future__ import annotations

import platform
from pathlib import Path
from typing import Any

from .browser_bridge import (
    COMMON_CDP_URLS,
    browser_executable_candidates,
    default_profile_root,
    discover_running_bridge_cdp_url,
    discover_managed_cdp_urls,
    probe_cdp_endpoint,
    read_bridge_metadata,
)


def recommended_launch_command() -> str:
    system = platform.system().lower()
    profile_path = default_profile_root()
    if system == "darwin":
        chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        return f"\"{chrome}\" --remote-debugging-port=9222 --user-data-dir=\"{profile_path}\""
    if system == "windows":
        return f"chrome.exe --remote-debugging-port=9222 --user-data-dir=\"{profile_path}\""
    return f"google-chrome --remote-debugging-port=9222 --user-data-dir=\"{profile_path}\""


def run_setup_diagnostics() -> dict[str, Any]:
    default_profile = default_profile_root()
    reachable = []
    for url in COMMON_CDP_URLS:
        info = probe_cdp_endpoint(url)
        if info:
            reachable.append({"url": url, "browser": info.get("Browser", ""), "web_socket": info.get("webSocketDebuggerUrl", "")})

    return {
        "chrome_candidates": browser_executable_candidates(),
        "reachable_cdp": reachable,
        "managed_cdp_candidates": discover_managed_cdp_urls(),
        "default_profile_dir": str(default_profile),
        "recommended_launch_command": recommended_launch_command(),
        "has_existing_profile": Path(default_profile).exists(),
        "bridge_metadata": read_bridge_metadata(default_profile),
        "active_bridge_cdp": discover_running_bridge_cdp_url(default_profile),
    }


def format_setup_report(report: dict[str, Any]) -> str:
    lines = ["wechat-reader setup", ""]
    chrome_candidates = report.get("chrome_candidates", [])
    lines.append("Detected browsers:")
    if chrome_candidates:
        lines.extend(f"- {candidate}" for candidate in chrome_candidates)
    else:
        lines.append("- none found")

    lines.extend(["", "Reachable CDP endpoints:"])
    reachable = report.get("reachable_cdp", [])
    if reachable:
        for item in reachable:
            lines.append(f"- {item['url']} ({item.get('browser') or 'unknown browser'})")
    else:
        lines.append("- none")
    managed_candidates = report.get("managed_cdp_candidates", [])
    if managed_candidates:
        lines.extend(["", "Managed bridge CDP candidates:"])
        lines.extend(f"- {candidate}" for candidate in managed_candidates)

    lines.extend(
        [
            "",
            f"Default bridge profile: {report['default_profile_dir']}",
            f"Existing bridge profile: {'yes' if report['has_existing_profile'] else 'no'}",
        ]
    )
    bridge_metadata = report.get("bridge_metadata")
    if bridge_metadata:
        lines.append(f"Stored bridge CDP URL: {bridge_metadata.get('cdp_url', 'unknown')}")
    active_bridge_cdp = report.get("active_bridge_cdp")
    if active_bridge_cdp:
        lines.append(f"Active bridge CDP URL: {active_bridge_cdp}")
    lines.extend(
        [
            "",
            "Recommended launch command:",
            report["recommended_launch_command"],
        ]
    )
    return "\n".join(lines) + "\n"
