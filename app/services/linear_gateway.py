from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.core.config import get_settings


class LinearGatewayError(RuntimeError):
    pass


def _read_secret(path_value: str) -> str:
    if not path_value:
        raise LinearGatewayError("LINEAR_GATEWAY_SECRET_FILE is not configured")
    try:
        secret = Path(path_value).read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise LinearGatewayError("Linear gateway secret could not be read") from exc
    if not secret:
        raise LinearGatewayError("Linear gateway secret is empty")
    return secret


def call_linear_gateway(operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    if not settings.linear_gateway_url:
        raise LinearGatewayError("LINEAR_GATEWAY_URL is not configured")

    body = json.dumps(
        {
            "schemaVersion": "linear-action-v1",
            "requestId": str(uuid.uuid4()),
            "operation": operation,
            "arguments": arguments,
        },
        separators=(",", ":"),
    ).encode("utf-8")
    request = Request(
        settings.linear_gateway_url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Jarvis-Bridge-Secret": _read_secret(settings.linear_gateway_secret_file),
        },
    )

    try:
        with urlopen(request, timeout=settings.linear_gateway_timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise LinearGatewayError(f"Linear gateway HTTP {exc.code}: {detail}") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise LinearGatewayError(f"Linear gateway request failed: {exc}") from exc

    if not isinstance(payload, dict):
        raise LinearGatewayError("Linear gateway returned a non-object response")
    return payload
