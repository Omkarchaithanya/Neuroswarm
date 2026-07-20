from __future__ import annotations

from common import DEFAULT_RESULTS_DIR, evaluate_governor, write_json


def main() -> None:
    write_json(DEFAULT_RESULTS_DIR / "governor_tokens.json", evaluate_governor())


if __name__ == "__main__":
    main()
