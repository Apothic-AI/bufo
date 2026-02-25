"""Background version check utility."""

from __future__ import annotations

import httpx
from packaging.version import InvalidVersion, Version

from bufo.version import __version__


async def check_for_update(package_name: str = "bufo") -> str | None:
    url = f"https://pypi.org/pypi/{package_name}/json"
    try:
        async with httpx.AsyncClient(timeout=2.5) as client:
            response = await client.get(url)
            response.raise_for_status()
            latest = response.json().get("info", {}).get("version")
    except Exception:
        return None

    if not latest:
        return None

    try:
        if Version(latest) > Version(__version__):
            return str(latest)
    except InvalidVersion:
        return None

    return None
