export type RunStatus =
  | "queued"
  | "running"
  | "cancel_requested"
  | "completed"
  | "cancelled"
  | "failed"
  | "interrupted";

export interface HealthResponse {
  readonly api_schema_version: "1.0";
  readonly service: "fantasy-football-application";
  readonly package_version: string;
  readonly build_revision: string | null;
  readonly revision_status: "explicit" | "unknown";
  readonly execution_mode: "local_background_m6_2";
  readonly local_only: true;
}

export interface TeamSummary {
  readonly team_id: number;
  readonly display_name: string;
  readonly wins: number;
  readonly losses: number;
  readonly ties: number;
  readonly points_for: number;
  readonly standing: number | null;
  readonly playoff_seed: number | null;
  readonly waiver_priority: number | null;
}

export interface PlayerSummary {
  readonly player_id: number;
  readonly display_name: string | null;
  readonly default_position_id: number;
  readonly eligible_lineup_slot_ids: readonly number[];
  readonly nfl_team_id: number;
  readonly injury_status: string | null;
  readonly acquisition_status: string;
  readonly is_undroppable: boolean | null;
}

export interface RosterAssignment {
  readonly player_id: number;
  readonly team_id: number;
  readonly lineup_slot_id: number;
}

export interface MatchupPeriodSummary {
  readonly matchup_period_id: number;
  readonly scoring_weeks: readonly number[];
  readonly phase: string;
}

export interface MatchupSummary {
  readonly matchup_id: number;
  readonly matchup_period_id: number;
  readonly home_team_id: number | null;
  readonly away_team_id: number | null;
  readonly bracket_type: string | null;
  readonly entry_status: string;
}

export interface LeagueStructure {
  readonly lineup_slot_capacities: readonly (readonly [number, number, string])[];
  readonly ordinary_roster_capacity: number;
  readonly reserve_roster_capacity: number;
  readonly championship_qualifier_count: number | null;
  readonly championship_round_count: number;
  readonly consolation_enabled: boolean | null;
  readonly acquisition_type: string;
  readonly acquisition_uses_budget: boolean;
}

export interface SnapshotSummary {
  readonly api_schema_version: "1.0";
  readonly snapshot_id: string;
  readonly league_id: number;
  readonly league_name: string | null;
  readonly season: number;
  readonly canonical_schema_version: number;
  readonly canonical_sha256: string;
  readonly source_count: number;
  readonly source_ids: readonly string[];
  readonly published_at_utc: string;
  readonly retrieval_finished_at_utc: string;
  readonly first_simulation_week: number;
  readonly final_simulation_week: number;
  readonly team_count: number | null;
  readonly teams: readonly TeamSummary[];
  readonly players: readonly PlayerSummary[];
  readonly roster_assignments: readonly RosterAssignment[];
  readonly matchup_periods: readonly MatchupPeriodSummary[];
  readonly matchups: readonly MatchupSummary[];
  readonly league_structure: LeagueStructure | null;
  readonly capabilities: readonly {
    readonly capability: string;
    readonly status: string;
    readonly source_id: string | null;
    readonly detail: string | null;
  }[];
}

export interface BackgroundRunRecord {
  readonly api_schema_version: "1.0";
  readonly run_id: string;
  readonly run_type: "baseline" | "manual_scenario" | "action_search";
  readonly status: RunStatus;
  readonly request_sha256: string;
  readonly snapshot_id: string;
  readonly build: {
    readonly package_version: string;
    readonly build_revision: string | null;
    readonly revision_status: "explicit" | "unknown";
  };
  readonly created_at_utc: string;
  readonly started_at_utc: string | null;
  readonly finished_at_utc: string | null;
  readonly expires_at_utc: string;
  readonly stop_reason: string | null;
  readonly error_code: string | null;
  readonly error_message: string | null;
  readonly result_available: boolean;
}

export interface ConfidenceInterval {
  readonly method: string;
  readonly interval_confidence_level: number;
  readonly simultaneous_family_confidence_level: number;
  readonly lower_probability: number;
  readonly upper_probability: number;
  readonly half_width_probability: number;
}

export interface ProbabilityValue {
  readonly successes: number;
  readonly trials: number;
  readonly probability: number | null;
  readonly interval: ConfidenceInterval | null;
  readonly precision_reached: boolean;
}

export interface TeamProbabilityResult {
  readonly team_id: number;
  readonly championship: ProbabilityValue;
  readonly playoff_qualification: ProbabilityValue;
  readonly final_placements: readonly { readonly placement: number; readonly estimate: ProbabilityValue }[];
}

export interface RunIdentity {
  readonly identity_schema_version: "application-run-identity-v1";
  readonly analytical_equivalence_sha256: string;
  readonly application_execution_sha256: string;
  readonly presentation_query_sha256: string;
  readonly execution_nonce: string;
  readonly build: BackgroundRunRecord["build"];
}

export interface AnalysisProvenance {
  readonly snapshot_id: string;
  readonly canonical_sha256: string;
  readonly simulation_config_sha256: string;
  readonly engine_run_identity_sha256: string;
  readonly model_id: string;
  readonly model_parameters: readonly (readonly [string, string | number | boolean])[];
  readonly master_seed: number;
  readonly first_path_index: number;
  readonly requested_path_count: number;
  readonly effective_request_sha256: string;
  readonly application_run: RunIdentity;
}

export interface BaselineAnalysisResult {
  readonly api_schema_version: "1.0";
  readonly provenance: AnalysisProvenance;
  readonly precision_config_sha256: string;
  readonly stopping_reason: string;
  readonly league_wide_precision_reached: boolean;
  readonly requested_paths: number;
  readonly completed_paths: number;
  readonly incomplete_paths: number;
  readonly candidate_coverage_complete: null;
  readonly teams: readonly TeamProbabilityResult[];
  readonly incomplete_capabilities: readonly (readonly [string, number])[];
  readonly limitations: readonly string[];
}

export interface BackgroundBaselineResultSummary {
  readonly api_schema_version: "1.0";
  readonly run: BackgroundRunRecord;
  readonly result: BaselineAnalysisResult;
}

export interface ApiErrorEnvelope {
  readonly api_schema_version: "1.0";
  readonly error: {
    readonly code: string;
    readonly message: string;
    readonly category: string;
    readonly context: Readonly<Record<string, string | number | boolean | null>>;
  };
}
