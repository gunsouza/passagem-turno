import hmac
import hashlib
import time
from typing import Mapping


def _compute_slack_signature(signing_secret: str, timestamp: str, body: bytes) -> str:
    basestring = f"v0:{timestamp}:".encode("utf-8") + body
    digest = hmac.new(signing_secret.encode("utf-8"), basestring, hashlib.sha256).hexdigest()
    return f"v0={digest}"


def verify_slack_signature(
    signing_secret: str,
    headers: Mapping[str, str],
    body: bytes,
    tolerance_seconds: int = 60 * 5,
) -> bool:
    received_signature = headers.get("X-Slack-Signature")
    received_ts = headers.get("X-Slack-Request-Timestamp")
    if not received_signature or not received_ts:
        return False

    try:
        ts_int = int(received_ts)
    except ValueError:
        return False

    if abs(time.time() - ts_int) > tolerance_seconds:
        return False

    expected = _compute_slack_signature(signing_secret, received_ts, body)
    return hmac.compare_digest(expected, received_signature)
