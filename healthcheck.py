"""Container health check — exits 0 when the API health endpoint responds."""

import sys
import urllib.request

HEALTH_URL = "http://localhost:8000/api/health"


def main() -> int:
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=5) as response:
            return 0 if response.status == 200 else 1
    except Exception as exc:  # noqa: BLE001 - health check must not raise
        print(f"Health check failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
