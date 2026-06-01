"""WarcraftLogs v2 GraphQL API client with rate limit awareness."""

import os
import sys
import time

import requests
from dotenv import load_dotenv

load_dotenv()

WCL_TOKEN_URL = "https://www.warcraftlogs.com/oauth/token"
WCL_API_URL = "https://www.warcraftlogs.com/api/v2/client"

_token_cache: dict = {}
_rate_state: dict = {
    "limit": 800,
    "remaining": 800,
    "retry_after": 0,
    "last_request": 0,
    "requests_this_window": 0,
}


def get_token() -> str:
    if _token_cache.get("token") and _token_cache.get("expires", 0) > time.time():
        return _token_cache["token"]

    cid = os.environ.get("WCL_CLIENT_ID")
    cs = os.environ.get("WCL_CLIENT_SECRET")
    if not cid or not cs:
        sys.exit("Error: WCL_CLIENT_ID and WCL_CLIENT_SECRET must be set in .env")

    r = requests.post(
        WCL_TOKEN_URL,
        data={"grant_type": "client_credentials"},
        auth=(cid, cs),
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()
    _token_cache["token"] = data["access_token"]
    _token_cache["expires"] = time.time() + data.get("expires_in", 3600) - 60
    return _token_cache["token"]


def _update_rate_state(resp):
    """Update rate limit state from response headers."""
    if "x-ratelimit-limit" in resp.headers:
        _rate_state["limit"] = int(resp.headers["x-ratelimit-limit"])
    if "x-ratelimit-remaining" in resp.headers:
        _rate_state["remaining"] = int(resp.headers["x-ratelimit-remaining"])
    if "retry-after" in resp.headers:
        _rate_state["retry_after"] = int(resp.headers["retry-after"])


def get_rate_info() -> dict:
    """Return current rate limit state for callers to inspect."""
    return dict(_rate_state)


def query(q: str, variables: dict | None = None) -> dict:
    token = get_token()
    payload = {"query": q}
    if variables:
        payload["variables"] = variables

    # Pre-request pacing: ensure minimum gap between requests
    elapsed = time.time() - _rate_state["last_request"]
    min_gap = 2.0  # minimum seconds between requests
    if elapsed < min_gap:
        time.sleep(min_gap - elapsed)

    resp = requests.post(
        WCL_API_URL,
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    _rate_state["last_request"] = time.time()
    _update_rate_state(resp)

    if resp.status_code == 429:
        retry_after = _rate_state["retry_after"]
        raise RateLimitError(retry_after)

    resp.raise_for_status()
    body = resp.json()
    if "errors" in body:
        print(f"WCL API errors: {body['errors']}", file=sys.stderr)
    return body.get("data", {})


class RateLimitError(Exception):
    """Raised on 429 with the retry-after duration."""
    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__(f"429 rate limited, retry after {retry_after}s")
