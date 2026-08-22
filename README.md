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

Each run is saved under a timestamped folder such as
`ESPN_OUTPUT_DIR/projection_260821_143509/`. The timestamp uses local time in
`yymmdd_hhmmss` format.

## Evaluate a proposed trade

Run the single-trade evaluator and enter player names when prompted:

```bash
python run_trade.py
```

Player names must exactly match the current ESPN roster data. You can also
enter ESPN player IDs. For multi-player trades, separate names or IDs with
commas. Your team is read from `MY_TEAM_ID` in `.env`, and all received
players must currently be on the same opposing team.

Results are written under a timestamped folder such as
`ESPN_OUTPUT_DIR/trade_comparison_260821_143509/`:

- `before/` and `after/` contain the complete projection output sets.
- `team_comparison.csv` summarizes both teams before and after the trade.
- `weekly_comparison.csv` shows weekly starter-projection changes.
- `lineup_comparison.csv` shows changes to each optimized starting lineup.
- `league_comparison.csv` shows league-wide seed and placement effects.
- `trade_summary.json` records the proposed trade and headline results.

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

The single-trade workflow lives in `trade_analysis.py`; its before/after file
output is handled by `trade_analysis_outputs.py`.

## Evaluate a proposed waiver move

Run the single-waiver evaluator and enter one available player to add and one
player from your roster to drop:

```bash
python run_waiver.py
```

Enter exact player names or ESPN player IDs when prompted. The evaluator
checks current ESPN availability, ownership, drop locks, undroppable status,
and roster position limits. It then optimizes every week and reruns the same
regular-season, standings, playoff, and final-finish engine used by trades.

Results are written to a timestamped folder such as
`waiver_comparison_260821_143509/`:

- `before/` and `after/` contain the complete projection output sets.
- `team_comparison.csv` contains immediate, ROS, regular-season, playoff,
  game-flip, seed, playoff-path, and final-position effects.
- `weekly_comparison.csv` shows the lineup impact in each remaining week.
- `lineup_comparison.csv` shows changes to the optimized starters.
- `league_comparison.csv` shows any league-wide seed and finish changes.
- `waiver_summary.json` records the proposed move and headline results.

## Waiver analyzer

Run the exhaustive waiver analyzer with:

```bash
python run_waivers.py
```

It pulls every player ESPN currently marks `FREEAGENT` or `WAIVERS`, then
evaluates every legal `add X / drop Y` combination for `MY_TEAM_ID`. Available
players without an eligible starter slot or any positive remaining-week
projection are retained in `all_available_players.csv` but excluded from the
transaction combinations with a recorded reason. Locked or undroppable roster
players are not used as executable drop candidates.

Every valid move uses the same weekly lineup optimizer and regular-season,
standings, postseason, and final-finish projection functions as the trade
engine. Results are saved under a timestamped folder such as
`waiver_analysis_260821_143509/`:

- `all_available_players.csv` contains the complete available-player pull.
- `all_add_drop_results.csv` contains every evaluated add/drop transaction.
- `marginal_roster_values.csv` values each rostered player against the best
  available overall and same-position replacement.
- `waiver_analysis_summary.json` records counts, exclusions, and tag totals.

Move tags identify immediate and rest-of-season upgrades, playoff-window
upgrades, game flips, added wins, seed improvements, and final-position
improvements. `BYE_OR_DEPTH_IMPROVEMENT` means the move helps in at least one
week while its median weekly impact is non-positive. `PLAYOFF_STASH` means its
playoff-window gain is positive while its remaining regular-season gain is
non-positive.

Marginal roster value is `current roster projection - best replacement
projection`. A positive number means the rostered player is better; a negative
number means an available replacement improves the optimized lineup. Locked or
undroppable players remain in the marginal-value file with status
`NO_EXECUTABLE_REPLACEMENT` and blank comparison metrics.

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
- Evaluating every 1-for-1 trade.
- Evaluating every 2-for-2 trade.
- Re-projecting the league for every valid trade.
- Evaluating waiver add/drop combinations.

`tqdm` is included in `requirements.txt`.


## Complete trade search

`python run_trades.py` evaluates every 1-for-1 and 2-for-2 combination involving
`MY_TEAM_ID`. All rostered positions are eligible, including kickers and D/ST.
There is no top-N limit or minimum-gain threshold.

Every valid trade is fully reprojected and written to a timestamped path such
as `trade_search_260821_143509/all_trade_results.csv`. Each row
includes current-week, remaining-
season, regular-season, and playoff-window lineup impacts; median gain;
positive/negative weeks; best/worst week; projected game flips; projected
wins; seed; playoff path; and final finish for both teams. Invalid trades that
cannot form a legal lineup are retained with their error reason.

`trade_search_summary.json` is the only additional file in that run folder.
The trade-search command does not rewrite the baseline projection files; run
`python run_projection.py` separately when those files are wanted.
