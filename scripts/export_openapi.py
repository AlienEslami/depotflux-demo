from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aggregator_demo.app import app


def rendered_openapi() -> str:
    return json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Export the versioned DepotFlux API contract.")
    parser.add_argument("--output", type=Path, default=Path("openapi/depotflux-v1.json"))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = rendered_openapi()
    if args.check:
        if not args.output.is_file() or args.output.read_text(encoding="utf-8") != rendered:
            print(f"OpenAPI contract is stale: {args.output}")
            return 1
        print(f"OpenAPI contract is current: {args.output}")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
