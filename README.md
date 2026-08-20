# ESPN Fantasy Deterministic Projection MVP

## Run

Keep your credentials in `.env` in the project root:

```text
ESPN_LEAGUE_ID=...
ESPN_SEASON=2026
ESPN_S2=...
ESPN_SWID={...}
ESPN_OUTPUT_DIR=league_projection_output
```

Install:

```bash
pip install -r requirements.txt
```

Run:

```bash
python run_projection.py
```

## Module layout

- `config.py` — `.env` configuration only.
- `espn.py` — ESPN HTTP access and player projection pulls.
- `league_data.py` — normalization of teams, rosters, schedules, and settings.
- `lineup.py` — exact weekly lineup optimization.
- `regular_season.py` — projected H2H matchups and final regular-season standings.
- `postseason.py` — championship bracket, consolation ladder, and final 1-N placements.
- `pipeline.py` — orchestrates the full league projection.
- `outputs.py` — CSV/JSON output and console reporting.

This separation is intentional: the later trade engine can alter only the roster
input and rerun the same projection pipeline.

## Postseason model

For the current league settings:

- 6 championship-playoff teams.
- Round 1 = Week 15.
- Round 2 = Week 16.
- Round 3 = Weeks 17-18.
- No playoff reseeding.
- Consolation ladder enabled.

The championship bracket produces places 1-6:

- Round 1: seeds 3v6 and 4v5; seeds 1 and 2 have byes.
- Round 2: semifinals plus a 5th-place game between Round-1 losers.
- Round 3: championship and 3rd-place game.

The eight non-playoff teams are modeled with an ESPN-style consolation ladder.
Teams begin in adjacent-seed games (7v8, 9v10, 11v12, 13v14). After each
round, winners move one rung upward and losers move one rung downward; the
top-game winner and bottom-game loser stay at their boundary. The final
round's four games determine places 7/8, 9/10, 11/12, and 13/14.

The consolation-ladder mechanics are isolated in `postseason.py` on purpose.
ESPN's public documentation describes the ladder concept but does not document
every custom 14-team bracket permutation. Once ESPN populates the league's
actual postseason bracket, we can compare it and adjust only this module if
necessary.

## Important outputs

- `weekly_player_projections.csv`
- `optimal_lineups.csv`
- `weekly_team_projections.csv`
- `regular_season_matchups.csv`
- `projected_regular_season_standings.csv`
- `projected_postseason_matchups.csv`
- `projected_final_standings.csv`
- `projection_summary.json`


## Progress bars

The project uses `tqdm` for the longer-running steps:

- Pulling ESPN weekly projections.
- Screening 1-for-1 trade partners/packages.
- Screening 2-for-2 trade partners/packages.
- Evaluating exact trade candidates.
- Re-projecting the league for the top trades.

`tqdm` is included in `requirements.txt`.


## Average weekly trade-gain threshold

Trade appeal is screened using average projected starting-lineup improvement
per remaining scoring week, rather than cumulative season gain.

```text
TRADE_MIN_AVG_WEEKLY_GAIN=0.50
```

With the default above, both sides must gain more than 0.50 projected starting-
lineup points per remaining week on average.

The trade outputs retain both:
- average weekly lineup gains (primary ranking / screening metrics), and
- total projected gains across the remaining horizon (secondary context).

The old `TRADE_MIN_FUTURE_GAIN` setting is deprecated; if it remains in `.env`,
the script will stop with a message telling you to replace it.
