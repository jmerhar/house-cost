"""The container's health probe: ``python -m house_cost.healthcheck``.

Exits non-zero unless the API answers and reports its database reachable. A probe that only
checked the port would call a container healthy while every request it served failed.
"""

import json
import sys
import urllib.error
import urllib.request

URL = "http://127.0.0.1:8000/api/health"
TIMEOUT_SECONDS = 5


def main(url: str = URL) -> int:
    """Report whether the application at ``url`` is serving, as an exit status."""
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
            body = json.load(response)
    except urllib.error.HTTPError as exc:
        # Closed explicitly: an HTTPError carries the response it was raised from.
        with exc:
            print(f"unhealthy: HTTP {exc.code}", file=sys.stderr)
        return 1
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"unhealthy: {exc}", file=sys.stderr)
        return 1
    if body.get("database") != "connected":
        print(f"unhealthy: database {body.get('database')!r}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
