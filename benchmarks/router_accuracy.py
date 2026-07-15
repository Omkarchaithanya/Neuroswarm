from __future__ import annotations

from common import DEFAULT_RESULTS_DIR, evaluate_router, write_json


def main() -> None:
    write_json(DEFAULT_RESULTS_DIR / "router_accuracy.json", evaluate_router())


if __name__ == "__main__":
    main()

