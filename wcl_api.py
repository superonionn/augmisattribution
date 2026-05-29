"""WarcraftLogs v2 GraphQL API client."""

import os
import sys
import time

import requests
from dotenv import load_dotenv

load_dotenv()

WCL_TOKEN_URL = "https://www.warcraftlogs.com/oauth/token"
WCL_API_URL = "https://www.warcraftlogs.com/api/v2/client"

_token_cache: dict = {}


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


def query(q: str, variables: dict | None = None) -> dict:
    token = get_token()
    payload = {"query": q}
    if variables:
        payload["variables"] = variables
    r = requests.post(
        WCL_API_URL,
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    r.raise_for_status()
    body = r.json()
    if "errors" in body:
        print(f"WCL API errors: {body['errors']}", file=sys.stderr)
    return body.get("data", {})
