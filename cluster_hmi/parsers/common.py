from __future__ import annotations

import json


def parse_json_or_kv(payload: bytes) -> dict[str, object] | None:
    cleaned = payload.strip()
    if not cleaned:
        return None

    try:
        return json.loads(cleaned.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        pass

    try:
        text = cleaned.decode("ascii", errors="ignore")
    except UnicodeDecodeError:
        return None

    data: dict[str, object] = {}
    for token in text.replace(";", ",").split(","):
        token = token.strip()
        if not token:
            continue

        if "=" in token:
            key, raw_value = token.split("=", 1)
        elif ":" in token:
            key, raw_value = token.split(":", 1)
        else:
            continue

        key = key.strip().lower()
        raw_value = raw_value.strip()
        lower_value = raw_value.lower()

        if lower_value in {"true", "false"}:
            data[key] = lower_value == "true"
            continue

        try:
            data[key] = float(raw_value)
        except ValueError:
            data[key] = raw_value

    return data or None
