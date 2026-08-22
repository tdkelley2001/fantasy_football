from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import Config
from .pipeline import ProjectionResult


def timestamped_run_dir(
    output_root: Path,
    run_name: str,
    *,
    now: datetime | None = None,
) -> Path:
    """Return a locally timestamped folder for one run."""
    moment = now or datetime.now().astimezone()
    timestamp = moment.strftime("%y%m%d_%H%M%S")
    return output_root / f"{run_name}_{timestamp}"


def write_csv(
    path: Path,
    rows: list[dict[str, Any]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    if not rows:
        path.write_text("", encoding="utf-8")
        return

    fieldnames = []
    seen = set()

    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)

    with path.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            obj,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def save_outputs(
    config: Config,
    result: ProjectionResult,
) -> None:
    out = config.output_dir
    out.mkdir(parents=True, exist_ok=True)

    roster_csv = []
    for row in result.rosters:
        copy = dict(row)
        copy["eligible_slots"] = json.dumps(
            copy["eligible_slots"]
        )
        roster_csv.append(copy)

    write_csv(out / "teams.csv", result.teams)
    write_csv(out / "rosters.csv", roster_csv)
    write_csv(
        out / "weekly_player_projections.csv",
        result.player_projections,
    )
    write_csv(
        out / "optimal_lineups.csv",
        result.optimal_lineups,
    )
    write_csv(
        out / "weekly_team_projections.csv",
        result.weekly_team_projections,
    )
    write_csv(
        out / "regular_season_matchups.csv",
        result.regular_season_matchups,
    )
    write_csv(
        out / "projected_regular_season_standings.csv",
        result.projected_standings,
    )
    write_csv(
        out / "projected_postseason_matchups.csv",
        result.postseason_matchups,
    )
    write_csv(
        out / "projected_final_standings.csv",
        result.final_standings,
    )
    write_json(
        out / "projection_summary.json",
        result.summary,
    )


def print_summary(result: ProjectionResult) -> None:
    playoff_count = result.summary[
        "playoff_team_count"
    ]

    print()
    print("=" * 72)
    print("PROJECTED REGULAR-SEASON STANDINGS")
    print("=" * 72)

    for row in result.projected_standings:
        marker = (
            "*"
            if row["seed"] <= playoff_count
            else " "
        )
        print(
            f'{marker} {row["seed"]:>2}. '
            f'{row["team_name"]:<28} '
            f'{row["record"]:<7} '
            f'PF {row["points_for"]:>8.2f}'
        )

    print()
    print("=" * 72)
    print("PROJECTED FINAL STANDINGS")
    print("=" * 72)

    for row in result.final_standings:
        print(
            f'{row["final_place"]:>2}. '
            f'{row["team_name"]:<28} '
            f'(regular-season seed '
            f'{row["regular_season_seed"]})'
        )

    print()
    print(
        "Projected league champion: "
        f'{result.summary["champion_team"]}'
    )
    print()
    print("* = projected championship-playoff team")
