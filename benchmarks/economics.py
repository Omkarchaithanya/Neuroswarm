from __future__ import annotations

from common import DEFAULT_RESULTS_DIR, evaluate_cascade, evaluate_governor, estimate_economics, evaluate_router, write_json


def main() -> None:
    router = evaluate_router()
    governor = evaluate_governor()
    cascade = evaluate_cascade()
    write_json(DEFAULT_RESULTS_DIR / "economics.json", estimate_economics(router, governor, cascade))


if __name__ == "__main__":
    main()

