from __future__ import annotations

from datetime import datetime, timezone

from fantasy_football.canonical.model import (
    AcquisitionRules,
    ChampionshipRules,
    ConsolationRules,
    FantasyMatchup,
    FantasyTeam,
    InterpretationStatus,
    JsonArray,
    JsonObject,
    LeagueRules,
    LeagueSnapshot,
    LineupSlotRule,
    MatchupEntryStatus,
    MatchupPeriod,
    MatchupPhase,
    NFLGame,
    NFLTeam,
    Player,
    PlayerWeek,
    PositionLimit,
    PostseasonRound,
    ProjectionClass,
    ProjectionSource,
    RosterEntry,
    RuleGap,
    RuleInterpretation,
    SCHEMA_VERSION,
    ScoringRule,
    SlotKind,
    SourceReference,
    StandingsRules,
    TradeRules,
    ValidationMetadata,
)


UTC = timezone.utc


def canonical_snapshot() -> LeagueSnapshot:
    source = SourceReference(
        source_id="league-request-1",
        endpoint="https://example.invalid/league/77",
        view="sanitized_fixture",
        parameters=(("scoringPeriodId", 15), ("view", "mSettings")),
        retrieved_at_utc=datetime(2026, 10, 16, 12, 0, 1, tzinfo=UTC),
        payload_sha256="a" * 64,
    )
    interpretations = (
        RuleInterpretation(
            rule_id="consolation_structure",
            raw_field="illustrative.consolationConfiguration",
            raw_value=JsonObject((
                ("enabled", True),
                ("rounds", JsonArray((
                    JsonObject((("duration", 1), ("round", 1))),
                    JsonObject((("duration", 2), ("round", 2))),
                ))),
            )),
            normalized_value=None,
            status=InterpretationStatus.UNSUPPORTED,
            source_id=source.source_id,
        ),
        RuleInterpretation(
            rule_id="playoff_tie",
            raw_field="settings.scoringSettings.playoffMatchupTieRule",
            raw_value="HIGHER_SEED",
            normalized_value="higher_seed",
            status=InterpretationStatus.UNDERSTOOD,
            source_id=source.source_id,
        ),
        RuleInterpretation(
            rule_id="regular_matchup_tie",
            raw_field="settings.scoringSettings.matchupTieRule",
            raw_value="NONE",
            normalized_value=None,
            status=InterpretationStatus.UNVERIFIED,
            source_id=source.source_id,
        ),
        RuleInterpretation(
            rule_id="standings_tiebreak_order",
            raw_field="settings.scheduleSettings.playoffSeedingRule",
            raw_value=JsonArray(("TOTAL_POINTS_SCORED", "HEAD_TO_HEAD", "RANDOM")),
            normalized_value=JsonArray(("points_for", "head_to_head", "random")),
            status=InterpretationStatus.UNDERSTOOD,
            source_id=source.source_id,
        ),
    )
    rules = LeagueRules(
        team_count=4,
        scoring=(ScoringRule(1, 0.04), ScoringRule(2, -2.0)),
        lineup_slots=(
            LineupSlotRule(0, 1, SlotKind.STARTER, "QB"),
            LineupSlotRule(16, 1, SlotKind.STARTER, "D/ST"),
            LineupSlotRule(20, 2, SlotKind.BENCH, "Bench"),
            LineupSlotRule(21, 1, SlotKind.RESERVE, "IR"),
        ),
        position_limits=(PositionLimit(1, 3), PositionLimit(16, 2)),
        lineup_lock_type="INDIVIDUAL_GAME",
        roster_lock_type="INDIVIDUAL_GAME",
        move_limit=None,
        acquisition=AcquisitionRules("WAIVERS_TRADITIONAL", False, None, None, 24, ("WEDNESDAY",), 11, True),
        trades=TradeRules(True, datetime(2026, 12, 2, 17, 0, tzinfo=UTC), None, 24, 2),
        standings=StandingsRules("H2H_POINTS", "TOTAL_POINTS_SCORED", "regular_matchup_tie", None),
        championship=ChampionshipRules(True, 2, False, (PostseasonRound(1, 2),), "playoff_tie"),
        consolation=ConsolationRules(None, 2, (PostseasonRound(1, 2),), "consolation_structure"),
        interpretations=interpretations,
    )
    teams = (
        FantasyTeam(1, "Alpha", 8, 5, 0, 1300.25, 1200.0, 1, 1, 1, None),
        FantasyTeam(2, "Beta", 7, 6, 0, 1250.0, 1240.5, 2, 2, 2, None),
        FantasyTeam(3, "Gamma", 6, 7, 0, 1200.0, 1260.0, 3, 3, 3, None),
        FantasyTeam(4, "Delta", 5, 8, 0, 1150.0, 1300.0, 4, 4, 4, None),
    )
    players = (
        Player(-101, "Defense A", 16, (16, 20), 1, None, "ONTEAM"),
        Player(1, "Quarterback A", 1, (0, 20, 21), 1, "ACTIVE", "ONTEAM"),
        Player(2, "Quarterback B", 1, (0, 20), 2, "QUESTIONABLE", "ONTEAM"),
        Player(3, "Unassigned Player", 1, (0, 20), 0, None, "FREEAGENT"),
        Player(4, "Available Player", 1, (0, 20), 3, "ACTIVE", "WAIVERS"),
    )
    rosters = (
        RosterEntry(-101, 1, 16, 1),
        RosterEntry(1, 1, 0, 1),
        RosterEntry(2, 2, 0, 2),
    )
    player_weeks: list[PlayerWeek] = []
    for week in (15, 16, 17):
        player_weeks.extend((
            PlayerWeek(-101, 2026, week, float(14 - week), ProjectionClass.PRESENT, float(14 - week), ProjectionSource.ESPN, source.source_id),
            PlayerWeek(1, 2026, week, float(week - 5), ProjectionClass.PRESENT, float(week - 5), ProjectionSource.ESPN, source.source_id),
            PlayerWeek(2, 2026, week, 0.0, ProjectionClass.EXPLICIT_ZERO, 0.0, ProjectionSource.ESPN, source.source_id),
            PlayerWeek(3, 2026, week, None, ProjectionClass.MISSING, 0.0, ProjectionSource.MISSING_PROJECTION_POLICY, source.source_id),
            PlayerWeek(4, 2026, week, 5.5, ProjectionClass.PRESENT, 5.5, ProjectionSource.ESPN, source.source_id),
        ))
    periods = (
        MatchupPeriod(1, (15,), MatchupPhase.REGULAR),
        MatchupPeriod(2, (16, 17), MatchupPhase.POSTSEASON),
    )
    matchups = (
        FantasyMatchup(1, 1, 1, 2),
        FantasyMatchup(2, 2, 1, 2, "championship"),
        FantasyMatchup(3, 1, 3, 4),
        FantasyMatchup(4, 2, 3, 4, "consolation"),
        FantasyMatchup(5, 2, None, None, "placement", MatchupEntryStatus.PLACEHOLDER),
    )
    nfl_teams = (
        NFLTeam(1, "A", 15), NFLTeam(2, "B", 15), NFLTeam(3, "C", None), NFLTeam(4, "D", None),
    )
    nfl_games = (
        NFLGame("15-C-D", 15, 3, 4, datetime(2026, 12, 20, 18, 0, tzinfo=UTC)),
        NFLGame("16-A-B", 16, 1, 2, datetime(2026, 12, 27, 18, 0, tzinfo=UTC)),
        NFLGame("16-C-D", 16, 3, 4, datetime(2026, 12, 27, 21, 0, tzinfo=UTC)),
        NFLGame("17-A-B", 17, 1, 2, datetime(2027, 1, 3, 18, 0, tzinfo=UTC)),
        NFLGame("17-C-D", 17, 3, 4, datetime(2027, 1, 3, 21, 0, tzinfo=UTC)),
    )
    gaps = (
        RuleGap("consolation_ladder", "Future consolation pairings are unavailable", source.source_id, ("full_placement_simulation",), True),
        RuleGap("regular_tie", "Raw NONE semantics are unverified", source.source_id, ("regular_matchup_resolution",), True),
    )
    return LeagueSnapshot(
        schema_version=SCHEMA_VERSION,
        snapshot_id="sanitized-2026-15",
        league_id=77,
        league_name="Sanitized League",
        season=2026,
        retrieval_started_at_utc=datetime(2026, 10, 16, 12, 0, tzinfo=UTC),
        retrieval_finished_at_utc=datetime(2026, 10, 16, 12, 0, 2, tzinfo=UTC),
        first_simulation_week=15,
        final_simulation_week=17,
        rules=rules,
        teams=teams,
        players=players,
        roster_entries=rosters,
        player_weeks=tuple(sorted(player_weeks, key=lambda item: (item.player_id, item.season, item.scoring_week))),
        matchup_periods=periods,
        fantasy_matchups=matchups,
        nfl_teams=nfl_teams,
        nfl_games=nfl_games,
        sources=(source,),
        rule_gaps=gaps,
        validation=ValidationMetadata(datetime(2026, 10, 16, 12, 0, 2, tzinfo=UTC), "m1.1", ("consolation unresolved",)),
    )
