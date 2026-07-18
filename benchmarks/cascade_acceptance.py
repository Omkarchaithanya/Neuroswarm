from __future__ import annotations

from common import DEFAULT_RESULTS_DIR, evaluate_cascade, write_json


def main() -> None:
    write_json(DEFAULT_RESULTS_DIR / "cascade_acceptance.json", evaluate_cascade())


if __name__ == "__main__":
    main()

