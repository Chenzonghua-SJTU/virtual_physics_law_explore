"""Restricted JSON-lines observation RPC. stdout is protocol only."""
import json
import os
import sys


def main():
    # Defense in depth: even direct launches do not retain the model credential.
    os.environ.pop("DEEPSEEK_API_KEY", None)
    from .simulator import Simulator
    try:
        config = json.loads(sys.argv[1]) if len(sys.argv) == 2 else {}
        simulator = Simulator(config)
    except Exception:
        print(json.dumps({"ok": False, "data": None, "error": {"code": "startup_failed", "message": "Invalid local environment configuration"}, "budget": None}), flush=True)
        return 2
    for line in sys.stdin:
        try:
            if len(line) > 1_000_000:
                raise ValueError("Request exceeds size limit")
            request = json.loads(line)
            if not isinstance(request, dict) or set(request) != {"method", "kwargs"}:
                raise ValueError("Request must contain exactly method and kwargs")
            if not isinstance(request["method"], str) or not isinstance(request["kwargs"], dict):
                raise ValueError("method must be a string and kwargs an object")
            result = simulator.request(request["method"], **request["kwargs"])
        except (ValueError, TypeError):
            result = {"ok": False, "data": None, "error": {"code": "invalid_request", "message": "Invalid JSON RPC request"}, "budget": simulator.budget()}
        print(json.dumps(result, allow_nan=False, separators=(",", ":")), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
