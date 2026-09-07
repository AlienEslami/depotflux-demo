from __future__ import annotations

import os


def main() -> int:
    import uvicorn

    uvicorn.run(
        "aggregator_demo.app:app",
        host=os.environ.get("DEMO_HOST", "127.0.0.1"),
        port=int(os.environ.get("DEMO_PORT", "8000")),
        reload=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
