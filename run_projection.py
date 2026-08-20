from __future__ import annotations

import sys

import requests

from fantasy_projection.config import load_config
from fantasy_projection.outputs import (
    print_summary,
    save_outputs,
)
from fantasy_projection.pipeline import run_projection


def main() -> int:
    try:
        config = load_config()

        print(
            f"ESPN league {config.league_id} | "
            f"season {config.season}"
        )
        print(
            f"Output directory: {config.output_dir}"
        )
        print(
            "Private-league cookies supplied: "
            f'{"yes" if config.espn_s2 and config.swid else "no"}'
        )
        print()

        result = run_projection(config)
        save_outputs(config, result)
        print_summary(result)

        print()
        print(
            f"Saved outputs to: "
            f"{config.output_dir.resolve()}"
        )
        return 0

    except requests.HTTPError as exc:
        print(
            f"ESPN HTTP error: {exc}",
            file=sys.stderr,
        )
        return 1
    except Exception as exc:
        print(
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
