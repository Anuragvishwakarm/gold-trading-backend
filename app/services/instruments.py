from __future__ import annotations

import gzip
import json
from datetime import datetime, timezone
from typing import Any


def download_mcx_instruments(url: str) -> list[dict[str, Any]]:
    import requests

    response = requests.get(url, timeout=30)
    response.raise_for_status()
    payload = response.content
    if payload[:2] == b"\x1f\x8b":
        payload = gzip.decompress(payload)
    result = json.loads(payload.decode("utf-8"))
    if not isinstance(result, list):
        raise ValueError("Unexpected MCX instrument file format")
    return result


def expiry_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        numeric = float(value)
        if numeric > 10_000_000_000:
            numeric /= 1000
        return datetime.fromtimestamp(numeric, tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        pass

    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def select_gold_futures(
    instruments: list[dict[str, Any]],
    underlying_symbol: str = "GOLD",
    count: int = 3,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """The ``count`` nearest non-expired futures (e.g. Oct, Dec, Feb), nearest first."""
    now = now or datetime.now(timezone.utc)
    wanted = underlying_symbol.upper()
    matches: list[tuple[datetime, dict[str, Any]]] = []

    for item in instruments:
        symbol = str(item.get("underlying_symbol") or item.get("name") or "").upper()
        expiry = expiry_datetime(item.get("expiry"))
        if (
            item.get("segment") == "MCX_FO"
            and item.get("instrument_type") == "FUT"
            and symbol == wanted
            and expiry is not None
            and expiry >= now
            and item.get("instrument_key")
        ):
            matches.append((expiry, item))

    if not matches:
        raise LookupError(f"No active MCX {wanted} future found")

    matches.sort(key=lambda pair: pair[0])
    selected: list[dict[str, Any]] = []
    for expiry, item in matches[: max(1, count)]:
        contract = dict(item)
        contract["expiry"] = expiry
        selected.append(contract)
    return selected

