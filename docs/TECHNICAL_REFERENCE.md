# War Room technical reference

**P7c pilot: T2, T5 and T7.** T2 retains its accepted source/dataset content; T5/T7 describe the implemented wire and search/query/export contracts. [DATA](DATA.md), [RESEARCH](RESEARCH.md), [APPLICATION_SERVICE](APPLICATION_SERVICE.md), [UNIFIED_ACTION_SEARCH](UNIFIED_ACTION_SEARCH.md) and [INTERFACE](INTERFACE.md) retain their current authority and all M0 bindings remain unchanged. Analytical meaning is in [METHODOLOGY](METHODOLOGY.md); assurance is in [VALIDATION](VALIDATION.md). [Authority and precedence](../AGENTS.md#authority-and-precedence) and all [BACKLOG](BACKLOG.md) obligations remain binding. T8/T9 runtime/persistence transfer is deferred; no owner is retired.

- [T2: Canonical, source and evidence data contracts](#canonical-source-and-evidence-data-contracts)
- [T5: HTTP API, DTOs and evolution](#http-api-dtos-and-evolution)
- [T7: Search interfaces, indexing and query/export contracts](#search-interfaces-indexing-and-queryexport-contracts)

## Canonical, source and evidence data contracts

### Adapter and canonical interfaces

[espn_adapter.py](../src/fantasy_football/espn_adapter.py) separates sequential `retrieve_bundle()` from pure `translate_bundle()`; `fetch_and_translate()` composes them. `CapturedResponse`, `PlayerPage`, `EspnSourceBundle` and the resulting `SourceReference` preserve sanitized request/source identity, context, retrieval UTC and deterministic parsed-payload digest. These are not HTTP wire-byte archives or secret-bearing authentication records. Exact endpoint/field transformations, pagination, current-versus-future ownership and reconciliation remain in [D1](DATA.md#data-lifecycle-and-source-provenance) and [D3](DATA.md#inputs-transformations-and-league-rule-authority).

| Interface / representation | Current contract and authoritative detail |
|---|---|
| `LeagueSnapshot`, frozen records/tuples in [model.py](../src/fantasy_football/canonical/model.py) | Canonical schema 4; supported reads 2/3/4, new publication 4. Flat IDs/joins; roster ownership exists only in RosterEntry. See [canonical invariants](DATA.md#canonical-validation-and-serialization). |
| `validate_snapshot()` in [validation.py](../src/fantasy_football/canonical/validation.py) | Pure, deterministic, nonmutating structural/context validation; coherent unsupported capabilities remain consumer-gated. No source hash creates permission. |
| `snapshot_to_json()` / `snapshot_from_json()` in [serialization.py](../src/fantasy_football/canonical/serialization.py) | Deterministic ordered, indented, newline-terminated UTF-8 JSON; UTC Z, explicit null/zero/signed numbers, no nonfinite values. Decode revalidates. Older reads/defaults do not recreate historical bytes or live authority. |
| `SnapshotStore` in [snapshot_store.py](../src/fantasy_football/snapshot_store.py) | Independently versioned SQLite schema 1, exact canonical JSON plus context-bound parsed raw sources; [immutable publication](DATA.md#immutable-storage) retains transaction/checksum/compression/verification details pending T8. No rewrite of old IDs/bytes. |
| Partial-week companion | Independently versioned artifact 1, not snapshot schema 4 or a research dataset. [PARTIAL_WEEK](PARTIAL_WEEK.md#companion-identity-and-preservation) retains exact envelope/basis/full digest and T4 execution contracts. |

Canonical `PlayerWeek` and research `HistoricalResearchRow` are different records. The former preserves raw/class/effective/source fields for engine input; the latter preserves raw forecasts, optional disclosed policy imputation, actuals and temporal eligibility for research. Neither schema version nor serializability establishes pregame trust or executable permission.

### Research source and dataset interfaces

The public in-memory boundary in [historical_dataset.py](../src/fantasy_football/historical_dataset.py) is:

```python
build_historical_research_dataset(samples, sources, validated_pregame_captures=())
validate_pregame_capture_manifest(manifest_bytes, payload_bytes, *, independently_trusted_manifest_sha256=...)
historical_research_dataset_to_json(dataset)
```

The builder performs no network, snapshot writes or fitting. [RESEARCH](RESEARCH.md#dataset-and-authenticated-captures) owns input validity/error semantics. The following table lists **all public dataclass fields** for the source/sample/row/dataset boundary, in declaration order; types and enum constraints remain inspectable in the linked implementation.

| Record | Fields |
|---|---|
| `HistoricalResearchSource` | `source_id`, `kind`, `roles`, `endpoint`, `view`, `parameters_json`, `retrieved_at_utc`, `payload_sha256`, `target_season`, `target_week`, `evidence_classification`, `verification_reference` |
| `HistoricalResearchInputRecord` | `player_week`, `policy_imputed_projection` |
| `HistoricalResearchSample` | `season`, `week`, `observation_period_start_utc`, `observation_period_end_utc`, `projection_source_id`, `actual_source_id`, `scoring_source_id`, `scoring_signature`, `records` |
| `HistoricalResearchRow` | `player_id`, `season`, `scoring_week`, `position_id`, `pro_team_id`, `raw_projection`, `policy_imputed_projection`, `actual_score`, `actual_stat_breakdown_present`, `raw_as_of_metadata_present`, `projection_value_kind`, `projection_temporal_provenance`, `projection_source_id`, `actual_source_id`, `scoring_source_id`, `observation_period_start_utc`, `observation_period_end_utc`, `scoring_signature`, `eligible_authenticated_pair`, `eligible_unverified_exploratory_pair` |
| `CoverageSummary` | `dimension`, `key`, `row_count`, `raw_projection_count`, `actual_count`, `paired_count`, `authenticated_pair_count`, `unverified_exploratory_pair_count`, `missing_projection_count`, `explicit_zero_count`, `policy_imputed_zero_count` |
| `HistoricalResearchDataset` | `schema_version`, `dataset_sha256`, `selected_samples`, `scoring_signature`, `sources`, `validated_pregame_captures`, `rows`, `coverage`, `limitations` |

`SourceRole` values are `projection`, `actual`, `scoring`. `SourceKind` values are `espn_historical_current_response`, `immutable_pregame_capture`, `sanitized_fixture`. `EvidenceClassification` values are `verified_live`, `verified_by_tests`, `unverified`, `unsupported`; a fixture cannot claim verified_live. `ProjectionValueKind` values are `espn_value`, `espn_explicit_zero`, `missing`, `model_policy_imputed_zero`. `ProjectionTemporalProvenance` values are `authenticated_pregame`, `historical_projection_pregame_provenance_unverified`, `not_applicable`. They describe separate dimensions, not interchangeable approval states.

The capture manifest schema is **`fantasy_football.pregame_capture.v1`**. Its exact field set is `schema`, `source_id`, `target_season`, `target_week`, `captured_at_utc`, `observation_period_start_utc`, `payload_sha256`, `endpoint`, `view`, `parameters_json`, `verification_authority`, `verification_reference`. Unknown/missing fields reject. Manifest bytes must be canonical JSON; parameters_json must itself be a canonical JSON object string. Digests are lowercase SHA-256. Capture time must be timezone-aware and strictly before period start; dataset actual retrieval must be at or after period end. Exact payload bytes must match the manifest digest and reparse into a nonempty historical player-week universe.

`ValidatedPregameCapture` has no supported direct constructor: only validation produces its internal token. Its retained fields are `source_id`, `target_season`, `target_week`, `captured_at_utc`, `observation_period_start_utc`, `payload_sha256`, `manifest_sha256`, `endpoint`, `view`, `parameters_json`, `verification_authority`, `verification_reference`, `projection_records`. `_validation_token` is internal and omitted from JSON. Parsed projection_records are serialized; **raw payload bytes are not**. Retain exact private payload/manifest bytes and independently provisioned trust records separately. A valid digest still cannot prove the external provisioning story; [D2](DATA.md#research-source-trust) and [RESEARCH](RESEARCH.md#external-trust-and-exact-row-binding) retain that boundary.

Dataset schema **2** sorts sources/captures by source ID, rows by `(season, scoring_week, player_id)` and selected samples by `(season, week)`. `dataset_sha256` hashes precisely this core: `schema_version`, `selected_samples`, `scoring_signature`, `sources`, `validated_pregame_captures`, `rows`. Derived coverage/limitations are serialized but outside that core; the serializer separately rechecks them. Thus an altered derived count is rejected even if the core digest still matches. Canonical research JSON uses sorted keys, separators `(',', ':')`, ensure_ascii=True, enum values and datetime.isoformat(), encoded UTF-8 without an added newline. Do not apply Markdown artifact newline normalization or snapshot pretty-printing to these identities.

### Evaluation and report interfaces

[outcome_distribution_research.py](../src/fantasy_football/outcome_distribution_research.py) exposes `research_outcome_distributions(dataset, configuration, candidates=DEFAULT_CANDIDATES)` and `outcome_distribution_report_to_json(report)`. It verifies dataset identity first; `dataset=None` yields explicit insufficiency. `HistoricalDatasetError` and `OutcomeResearchError` reject inconsistent inputs/identities rather than repairing them. There is no corresponding automatic production promotion operation.

| Record | Fields |
|---|---|
| `TemporalSplit` | `evaluation_start_season`, `evaluation_start_week` |
| `ResearchConfiguration` | `evidence_policy`, `temporal_split`, `projection_bin_edges`, `minimum_group_size`, `minimum_training_rows`, `minimum_evaluation_rows`, `hybrid_shrinkage_strength`, `density_bandwidth_floor`, `normal_quadrature_points` |
| `CandidateSpecification` | `candidate_id`, `family`, `conditioning` |
| `OutcomeDistributionResearchReport` | `schema_version`, `report_sha256`, `source_dataset_sha256`, `configuration`, `candidates`, `coverage`, `authenticated_rows`, `unverified_exploratory_rows`, `excluded_rows`, `evidence_sufficient`, `exploratory_best_candidate_id`, `recommended_candidate_id`, `recommendation`, `limitations` |

Report schema **1** hashes every serialized report field except `report_sha256` itself; it uses sorted compact ensure_ascii JSON like the dataset, but its own independent schema/identity. Serializing rechecks the schema and digest. `evidence_sufficient` is authenticated-policy sample sufficiency, not all scientific promotion gates. `exploratory_best_candidate_id` can also be populated on an authenticated run; it is not an exclusive evidence-class flag. [RESEARCH’s metrics](RESEARCH.md#metrics-and-promotion) and [V3](VALIDATION.md#diagnostics-and-recommendation-boundaries) explain candidate diagnostics/ordering, not a new API. Full `CandidateEvaluation` and `SampleCoverage` layouts remain in the implementation/current RESEARCH reference pending broader technical consolidation.

### Executable evidence and deferred ownership

The **seven** M0 roles and contract-2 JSON stay at [DATA’s register](DATA.md#m0-consumer-dependency), bound to the existing DATA, RESEARCH and PLAYER_OUTCOME_MODEL anchors and immutable historical identities. [m0_verification.py](../src/fantasy_football/m0_verification.py) checks offline structure/interfaces/recorded identity, not historical bytes, ESPN compatibility or release readiness. This chapter is not an additional evidence document or migrated role owner.

The [source-section mapping](DATA.md#p7a-source-section-mapping-and-retained-ownership) records T2's limited coverage. Model/draw identities, companion execution, APIs, workers/checkpoints, search indexes and storage/process lifecycle retain their current owners; T1/T3–T8 are not transferred. [RESEARCH reproduction](RESEARCH.md#reproduction-and-artifacts) retains the separately authorized network workflow and private artifact recipe. [Source/provenance tests](../tests/test_historical_dataset.py), [research tests](../tests/test_outcome_distribution_research.py) and [pilot contract tests](../tests/test_data_documentation.py) establish code/document consistency only. No schemas, production bytes, numerical identities or evidence results change here.

## HTTP API, DTOs and evolution

[http.py](../src/fantasy_football/app/http.py) implements `/api/v1`; [contracts.py](../src/fantasy_football/app/contracts.py) defines public API schema **1.0**. The source-bound route/DTO map below describes current behavior, not a new API. Runtime `/openapi.json` and `/docs` expose the schema; `/docs/oauth2-redirect` is framework documentation support, not an application authorization API; ReDoc is disabled. When a validated frontend build is configured, GET `/assets/{asset_path:path}` and GET `/{frontend_path:path}` serve confined assets/navigation outside OpenAPI. Unknown API routes are 404, not SPA responses. Static/process/security behavior remains with [APPLICATION_SERVICE](APPLICATION_SERVICE.md#local-security-boundary) and OPERATIONS.

### Route and success-schema inventory

Path braces identify required URL strings; body `none` means no JSON body parameter. `array[T]` denotes a JSON array and `or null` a nullable response. This inventory contains every implemented versioned route, including the distinct 202 submission envelopes and empty 204 deletion response; errors are described separately below.

| Method | Route | Body DTO | Success DTO | HTTP |
|---|---|---|---|---:|
| GET | `/api/v1/health` | `none` | `HealthResponse` | 200 |
| GET | `/api/v1/snapshots` | `none` | `array[SnapshotSummary]` | 200 |
| GET | `/api/v1/snapshots/{snapshot_id}` | `none` | `SnapshotSummary` | 200 |
| GET | `/api/v1/refresh/profile` | `none` | `LeagueRefreshProfile` | 200 |
| POST | `/api/v1/refreshes` | `SnapshotRefreshRequest` | `SnapshotRefreshSubmission` | 202 |
| GET | `/api/v1/refreshes/current` | `none` | `SnapshotRefreshRecord or null` | 200 |
| GET | `/api/v1/refreshes/{refresh_id}` | `none` | `SnapshotRefreshRecord` | 200 |
| POST | `/api/v1/refreshes/{refresh_id}/cancel` | `none` | `SnapshotRefreshRecord` | 200 |
| GET | `/api/v1/refreshes/{refresh_id}/result` | `none` | `SnapshotRefreshResult` | 200 |
| POST | `/api/v1/analyses/baseline` | `BaselineAnalysisRequest` | `BaselineAnalysisResult` | 200 |
| POST | `/api/v1/analyses/manual-scenario` | `ManualScenarioRequest` | `ManualScenarioResult` | 200 |
| POST | `/api/v1/analyses/action-search` | `ActionSearchRequest` | `ActionSearchResult` | 200 |
| POST | `/api/v1/runs/baseline` | `BaselineAnalysisRequest` | `BackgroundRunSubmission` | 202 |
| POST | `/api/v1/runs/manual-scenario` | `ManualScenarioRequest` | `BackgroundRunSubmission` | 202 |
| POST | `/api/v1/runs/action-search` | `ActionSearchRequest` | `BackgroundRunSubmission` | 202 |
| GET | `/api/v1/runs` | `none` | `array[BackgroundRunRecord]` | 200 |
| GET | `/api/v1/runs/{run_id}` | `none` | `BackgroundRunRecord` | 200 |
| GET | `/api/v1/runs/{run_id}/progress` | `none` | `BackgroundProgress` | 200 |
| POST | `/api/v1/runs/{run_id}/cancel` | `none` | `BackgroundRunRecord` | 200 |
| GET | `/api/v1/runs/{run_id}/result` | `none` | `BackgroundResultSummary` | 200 |
| GET | `/api/v1/runs/{run_id}/candidates` | `none` | `CandidateQueryPage` | 200 |
| GET | `/api/v1/runs/{run_id}/candidates/{candidate_id}` | `none` | `CandidateDetail` | 200 |
| GET | `/api/v1/runs/{run_id}/states/{state_id}` | `none` | `CompletedStateDetail` | 200 |
| DELETE | `/api/v1/runs/{run_id}` | `none` | `empty` | 204 |

`/refreshes/current` is registered before the ID route. Snapshot IDs are selected explicitly, with no fallback. Compact snapshot listing leaves team_count null; detail loads verified canonical content. Refresh bodies select only the configured local profile/league/season and optional safe-week request; they accept no credential, URL, local rule path or authority override. Manual-rule/profile availability is not evidence a rule applied. Current records/results are typed as above; refresh history and runtime publication semantics remain with their [current owner](APPLICATION_SERVICE.md#snapshot-selection-and-refresh).

| GET query surface | Declared parameters / defaults |
|---|---|
| snapshots list and snapshot detail | `league_id=null` (>0), `season=null` (>=2000); detail takes path `snapshot_id` |
| runs list | `status=null` (queued, running, cancel_requested, completed, cancelled, failed, interrupted), `limit=50` (1–200); newest first, no offset or server-side snapshot filter |
| candidate page | `offset=0` (>=0), `limit=50` (1–200), `sort_key="candidate_id"`, `direction="asc"`, `ordering=null`, `authorization=null`, `acquisition_status=null`, `evaluated=null`, `team_id=null` (>0); exact allowlist in T7 |
| other versioned GET routes | Path identifiers only; no additional declared query parameters |

### Validation, nulls and compatibility

All ContractModel DTOs are frozen and forbid extra fields. This is **not global strict coercion**: strict integer/float constraints apply where explicitly declared; ordinary booleans and unannotated fields follow Pydantic behavior. HTTP query strings undergo FastAPI parsing. Undeclared query keys are **ignored**, not additional supported operators and not guaranteed validation failures. Recognized sort/filter values reject when outside the store allowlist. Do not infer query strictness from JSON-body extra-field rejection.

The registry below lists every concrete DTO, all fields, required/optional status, JSON type/ref, nullable union, literal values, defaults and schema bounds. `name?` means omittable; **null is allowed only when explicitly shown**. Required nullable fields must still be supplied. `T[]` is a JSON array; `[T,U]` a fixed positional array; references are other registry models. `JsonValue` is recursive JSON scalar/array/object/null. Bounds use `>`, `>=`, `<`, `<=`, minLength/minItems/maxItems; defaults are JSON values, so Python tuples appear as arrays. These are wire schema shapes, not a promise of Python input coercion or cross-field legality. Date-time fields use ISO date-time strings; authoritative UTC/context validation remains at its domain boundary.

Normal dispersion requires at least one of base_stddev_points/projection_scale positive, not both zero. Precision minimum_paths cannot exceed maximum_paths. Baseline simulation.path_count must equal precision.maximum_paths; search maximum_paths_per_state must match simulation.path_count before resource clamping. Engine validation additionally checks finite values, ownership, family/order compatibility, timing, rules and evidence. DTO parse success never grants execution permission. Explicit failure/capability-incomplete responses remain distinct.

### Wire schema registry

| DTO | Fields: required unless marked `?`; types, bounds and defaults |
|---|---|
| `SnapshotSelector` | `snapshot_id: string{minLength=1}`; `league_id?: integer{>0} or null=null`; `season?: integer{>=2000} or null=null` |
| `SnapshotListQuery` | `league_id?: integer{>0} or null=null`; `season?: integer{>=2000} or null=null` |
| `TeamSummary` | `team_id: integer`; `display_name: string`; `wins: integer`; `losses: integer`; `ties: integer`; `points_for: number`; `standing: integer or null`; `playoff_seed: integer or null`; `waiver_priority: integer or null` |
| `PlayerSummary` | `player_id: integer`; `display_name: string or null`; `default_position_id: integer`; `eligible_lineup_slot_ids: integer[]`; `nfl_team_id: integer`; `injury_status: string or null`; `acquisition_status: string`; `is_undroppable: boolean or null` |
| `RosterAssignment` | `player_id: integer`; `team_id: integer`; `lineup_slot_id: integer` |
| `MatchupPeriodSummary` | `matchup_period_id: integer`; `scoring_weeks: integer[]`; `phase: string` |
| `MatchupSummary` | `matchup_id: integer`; `matchup_period_id: integer`; `home_team_id: integer or null`; `away_team_id: integer or null`; `bracket_type: string or null`; `entry_status: string` |
| `RuleCapability` | `capability: string`; `status: string`; `source_id?: string or null=null`; `detail?: string or null=null` |
| `LeagueStructure` | `lineup_slot_capacities: [integer, integer, string]{minItems=3,maxItems=3}[]`; `ordinary_roster_capacity: integer`; `reserve_roster_capacity: integer`; `championship_qualifier_count: integer or null`; `championship_round_count: integer`; `consolation_enabled: boolean or null`; `acquisition_type: string`; `acquisition_uses_budget: boolean` |
| `ScoringWeekStateSummary` | `scoring_week: integer`; `status: "completed" / "partial" / "unplayed" / "unresolved"`; `rationale: string` |
| `LiveScoringSummary` | `current_scoring_period: integer`; `last_fully_completed_period: integer or null`; `earliest_unresolved_period: integer or null`; `next_fully_unplayed_period: integer or null`; `supported_simulation_week: integer or null`; `partial_week_simulation_required: boolean`; `boundary_method: "automatic" / "manual_override" / "unresolved"`; `boundary_rationale: string`; `weeks: ScoringWeekStateSummary[]`; `unresolved_capabilities: string[]` |
| `SnapshotSummary` | `api_schema_version?: "1.0"="1.0"`; `snapshot_id: string`; `league_id: integer`; `league_name?: string or null=null`; `season: integer`; `canonical_schema_version: integer`; `canonical_sha256: string`; `source_count: integer`; `source_ids?: string[]=[]`; `published_at_utc: string(date-time)`; `retrieval_finished_at_utc: string(date-time)`; `first_simulation_week: integer`; `final_simulation_week: integer`; `team_count: integer or null`; `teams?: TeamSummary[]=[]`; `players?: PlayerSummary[]=[]`; `roster_assignments?: RosterAssignment[]=[]`; `matchup_periods?: MatchupPeriodSummary[]=[]`; `matchups?: MatchupSummary[]=[]`; `league_structure?: LeagueStructure or null=null`; `capabilities?: RuleCapability[]=[]`; `live_scoring?: LiveScoringSummary or null=null` |
| `NormalOutcomeModelConfiguration` | `model_type?: "provisional_normal"="provisional_normal"`; `base_stddev_points: number{>=0.0}`; `projection_scale: number{>=0.0}` |
| `SimulationConfiguration` | `master_seed: integer`; `path_count: integer{<=10000,>0}`; `first_path_index?: integer{>=0}=0`; `ir_policy: "projection_based" / "strict"`; `waiver_boundary: "unresolved" / "modeled_weekly_v1"`; `reject_incomplete_valuations?: boolean=true`; `require_complete?: boolean=true` |
| `PrecisionSettings` | `family_confidence_level: number{>0.0,<1.0}`; `target_half_width_probability: number{>0.0,<1.0}`; `minimum_paths: integer{<=10000,>0}`; `maximum_paths: integer{<=10000,>0}`; `evaluation_interval_paths: integer{<=10000,>0}` |
| `BuildProvenance` | `package_version: string`; `build_revision: string or null`; `revision_status: "explicit" / "unknown"` |
| `RunIdentity` | `identity_schema_version: "application-run-identity-v1"`; `analytical_equivalence_sha256: string`; `application_execution_sha256: string`; `presentation_query_sha256: string`; `execution_nonce: string`; `build: BuildProvenance` |
| `ConfidenceInterval` | `method: string`; `interval_confidence_level: number`; `simultaneous_family_confidence_level: number`; `lower_probability: number`; `upper_probability: number`; `half_width_probability: number` |
| `ProbabilityValue` | `successes: integer`; `trials: integer`; `probability: number or null`; `interval: ConfidenceInterval or null`; `precision_reached: boolean` |
| `PlacementProbability` | `placement: integer`; `estimate: ProbabilityValue` |
| `TeamProbabilityResult` | `team_id: integer`; `championship: ProbabilityValue`; `playoff_qualification: ProbabilityValue`; `final_placements: PlacementProbability[]` |
| `AnalysisProvenance` | `snapshot_id: string`; `canonical_sha256: string`; `simulation_config_sha256: string`; `engine_run_identity_sha256: string`; `model_id: string`; `model_parameters: [string, string or integer or number or boolean]{minItems=2,maxItems=2}[]`; `master_seed: integer`; `first_path_index: integer`; `requested_path_count: integer`; `effective_request_sha256: string`; `application_run: RunIdentity` |
| `BaselineAnalysisRequest` | `api_schema_version?: "1.0"="1.0"`; `snapshot: SnapshotSelector`; `simulation: SimulationConfiguration`; `precision: PrecisionSettings`; `outcome_model: NormalOutcomeModelConfiguration` |
| `BaselineAnalysisResult` | `api_schema_version?: "1.0"="1.0"`; `provenance: AnalysisProvenance`; `precision_config_sha256: string`; `stopping_reason: string`; `league_wide_precision_reached: boolean`; `requested_paths: integer`; `completed_paths: integer`; `incomplete_paths: integer`; `candidate_coverage_complete?: null=null`; `teams: TeamProbabilityResult[]`; `incomplete_capabilities: [string, integer]{minItems=2,maxItems=2}[]`; `limitations: string[]` |
| `RosterChangeInput` | `player_id: integer`; `from_team_id: integer or null`; `to_team_id: integer or null` |
| `ProtectedPlayerInput` | `team_id: integer`; `player_id: integer` |
| `ManualScenarioInput` | `scenario_id: string{minLength=1}`; `changes: RosterChangeInput[]`; `protected_players?: ProtectedPlayerInput[]=[]` |
| `ManualScenarioRequest` | `api_schema_version?: "1.0"="1.0"`; `snapshot: SnapshotSelector`; `simulation: SimulationConfiguration`; `precision: PrecisionSettings`; `outcome_model: NormalOutcomeModelConfiguration`; `scenario: ManualScenarioInput` |
| `PairedMetricResult` | `baseline_probability: number`; `scenario_probability: number`; `difference_probability_points: number`; `improved_paths: integer`; `worsened_paths: integer`; `unchanged_paths: integer`; `interval_lower_probability_points: number`; `interval_upper_probability_points: number` |
| `TeamScenarioResult` | `team_id: integer`; `championship: PairedMetricResult`; `playoff_qualification: PairedMetricResult`; `final_placements: [integer, PairedMetricResult]{minItems=2,maxItems=2}[]` |
| `WeeklyLineupResult` | `scoring_week: integer`; `baseline_starter_player_ids: integer[]`; `hypothetical_starter_player_ids: integer[]`; `baseline_bench_player_ids: integer[]`; `hypothetical_bench_player_ids: integer[]`; `baseline_reserve_player_ids: integer[]`; `hypothetical_reserve_player_ids: integer[]`; `baseline_projected_points: number`; `hypothetical_projected_points: number`; `projected_points_difference: number`; `baseline_vacancy_count: integer`; `hypothetical_vacancy_count: integer` |
| `TeamLineupResult` | `team_id: integer`; `changed_scoring_weeks: integer[]`; `weeks: WeeklyLineupResult[]` |
| `ManualScenarioResult` | `api_schema_version?: "1.0"="1.0"`; `provenance: AnalysisProvenance`; `scenario_id: string`; `scenario_sha256: string`; `precision_config_sha256: string`; `baseline_simulation_config_sha256: string`; `hypothetical_simulation_config_sha256: string`; `baseline_engine_run_identity_sha256: string`; `hypothetical_engine_run_identity_sha256: string`; `matched_path_count: integer`; `affected_team_ids: integer[]`; `forced_drop_player_ids: integer[]`; `automatic_addition_player_ids: integer[]`; `teams: TeamScenarioResult[]`; `lineup_explanations: TeamLineupResult[]`; `assumptions: string[]` |
| `TradeShapeInput` | `outgoing_count: integer{>0}`; `incoming_count: integer{>0}` |
| `UnifiedCandidateConfiguration` | `requesting_team_id: integer`; `action_families: "trade" / "trade_chain" / "acquisition"[]`; `action_orderings: "standalone_trade" / "standalone_chain" / "standalone_acquisition" / "trade_then_acquisition" / "acquisition_then_trade" / "chain_then_acquisition" / "multiple_acquisitions"[]`; `counterparty_team_ids?: integer[]=[]`; `tradeable_player_ids?: integer[]=[]`; `acquisition_player_ids?: integer[]=[]`; `eligible_drop_player_ids?: integer[] or null=null`; `trade_shapes?: TradeShapeInput[]=[]`; `minimum_trade_chain_length?: integer{>0}=2`; `maximum_trade_chain_length?: integer{>0}=2`; `maximum_total_action_count?: integer{>0}=2`; `acquisition_status_filter?: "free_agent" / "waivers" / "hold" / "unresolved"[] or null=null`; `waiver_boundary?: "unresolved" / "modeled_weekly_v1"="unresolved"`; `protected_player_ids?: integer[]=[]` |
| `SearchSamplingSettings` | `confidence_level: number{>0.0,<1.0}`; `target_paired_half_width_probability_points: number{>0.0,<1.0}`; `initial_paths: integer{<=10000,>0}`; `refinement_batch_paths: integer{<=10000,>0}`; `maximum_paths_per_state: integer{<=10000,>0}`; `minimum_finalist_states: integer{>0}`; `unique_state_evaluation_budget?: integer{>0} or null=null` |
| `SearchResourceSettings` | `execution_mode?: "sequential_reference" / "bounded_overlap"="sequential_reference"`; `worker_count?: integer{>0}=1`; `maximum_in_flight_states?: integer{>0}=1`; `paths_per_worker_task?: integer{>0}=1`; `queue_capacity?: integer{>0}=64`; `candidate_limit?: integer{>0} or null=null`; `evaluation_state_limit?: integer{>0} or null=null`; `simulation_path_budget?: integer{>0} or null=null`; `wall_clock_seconds?: number{>0.0} or null=null`; `index_page_size?: integer{>0}=128` |
| `ActionSearchRequest` | `api_schema_version?: "1.0"="1.0"`; `snapshot: SnapshotSelector`; `simulation: SimulationConfiguration`; `outcome_model: NormalOutcomeModelConfiguration`; `candidate_search: UnifiedCandidateConfiguration`; `evaluation_mode: "fixed" / "progressive"`; `sampling: SearchSamplingSettings`; `resources?: SearchResourceSettings={"candidate_limit":null,"evaluation_state_limit":null,"execution_mode":"sequential_reference","index_page_size":128,"maximum_in_flight_states":1,"paths_per_worker_task":1,"queue_capacity":64,"simulation_path_budget":null,"wall_clock_seconds":null,"worker_count":1}`; `response_candidate_limit?: integer{>=1,<=500}=100` |
| `CandidateSummary` | `candidate_id: string`; `completed_state_sha256: string`; `ordering: "standalone_trade" / "standalone_chain" / "standalone_acquisition" / "trade_then_acquisition" / "acquisition_then_trade" / "chain_then_acquisition" / "multiple_acquisitions"`; `transaction_authorization: "transaction_authorized" / "structural_hypothetical"`; `acquisition_condition: "not_applicable" / "immediate_free_agent" / "conditional_waiver"`; `evaluated_paths: integer`; `requester_championship_difference_probability_points: number or null`; `statistically_competitive: boolean`; `precision_reached: boolean`; `caveats: string[]` |
| `SearchCoverageResult` | `generated_candidates: integer`; `retained_candidates: integer`; `unique_completed_states: integer`; `returned_candidates: integer`; `response_truncated: boolean`; `candidate_coverage_complete: boolean`; `evaluation_coverage_complete: boolean`; `statistical_precision_complete: boolean`; `ranking_resolved: boolean` |
| `ActionSearchResult` | `api_schema_version?: "1.0"="1.0"`; `provenance: AnalysisProvenance`; `search_run_sha256: string`; `candidate_configuration_sha256: string`; `stop_reason: string`; `coverage: SearchCoverageResult`; `candidates: CandidateSummary[]`; `wall_clock_overrun_seconds: number` |
| `ErrorDetail` | `code: string`; `message: string`; `category: "invalid_request" / "not_found" / "unsupported_configuration" / "invalid_scenario" / "resource_exhausted" / "engine_invariant" / "internal_error"`; `context?: object<string,string or integer or number or boolean or null>={}` |
| `ErrorResponse` | `api_schema_version?: "1.0"="1.0"`; `error: ErrorDetail` |
| `HealthResponse` | `api_schema_version?: "1.0"="1.0"`; `service?: "fantasy-football-application"="fantasy-football-application"`; `package_version: string`; `build_revision: string or null`; `revision_status: "explicit" / "unknown"`; `execution_mode?: "local_background_m6_2"="local_background_m6_2"`; `local_only?: true=true`; `process_id: integer{>0}`; `launcher_run_id?: string or null=null` |
| `LeagueRefreshProfile` | `profile_id?: "configured_local_league"="configured_local_league"`; `league_id: integer{>0}`; `season: integer{>=2000}`; `credential_mode: "public" / "private_credentials_configured"`; `manual_rule_configuration_available: boolean` |
| `SnapshotRefreshRequest` | `api_schema_version?: "1.0"="1.0"`; `profile_id?: "configured_local_league"="configured_local_league"`; `league_id: integer{>0}`; `season: integer{>=2000}`; `first_simulation_week?: integer{>=1,<=25} or null=null` |
| `SnapshotRefreshSubmission` | `api_schema_version?: "1.0"="1.0"`; `refresh_id: string`; `status: "queued" / "running" / "cancel_requested" / "completed" / "cancelled" / "failed" / "interrupted"`; `created_at_utc: string(date-time)` |
| `SnapshotRefreshRecord` | `api_schema_version?: "1.0"="1.0"`; `refresh_id: string`; `status: "queued" / "running" / "cancel_requested" / "completed" / "cancelled" / "failed" / "interrupted"`; `stage: "queued" / "retrieving_and_validating" / "publishing" / "verifying" / "completed" / "cancelled" / "failed" / "interrupted"`; `league_id: integer`; `season: integer`; `first_simulation_week: integer or null`; `created_at_utc: string(date-time)`; `started_at_utc?: string(date-time) or null=null`; `finished_at_utc?: string(date-time) or null=null`; `snapshot_id?: string or null=null`; `publication_committed?: boolean=false`; `error_code?: string or null=null`; `error_message?: string or null=null` |
| `SnapshotRefreshResult` | `api_schema_version?: "1.0"="1.0"`; `refresh: SnapshotRefreshRecord`; `snapshot: SnapshotSummary`; `validation_findings: string[]`; `unresolved_capabilities: string[]` |
| `BackgroundRunSubmission` | `api_schema_version?: "1.0"="1.0"`; `run_id: string`; `run_type: "baseline" / "manual_scenario" / "action_search"`; `status: "queued" / "running" / "cancel_requested" / "completed" / "cancelled" / "failed" / "interrupted"`; `created_at_utc: string(date-time)` |
| `BackgroundRunRecord` | `api_schema_version?: "1.0"="1.0"`; `run_id: string`; `run_type: "baseline" / "manual_scenario" / "action_search"`; `status: "queued" / "running" / "cancel_requested" / "completed" / "cancelled" / "failed" / "interrupted"`; `request_sha256: string`; `snapshot_id: string`; `build: BuildProvenance`; `created_at_utc: string(date-time)`; `started_at_utc: string(date-time) or null`; `finished_at_utc: string(date-time) or null`; `expires_at_utc: string(date-time)`; `stop_reason: string or null`; `error_code: string or null`; `error_message: string or null`; `result_available: boolean` |
| `BackgroundProgress` | `api_schema_version?: "1.0"="1.0"`; `run_id: string`; `status: "queued" / "running" / "cancel_requested" / "completed" / "cancelled" / "failed" / "interrupted"`; `stage: string`; `candidates_explored?: integer=0`; `candidates_retained?: integer=0`; `unique_completed_states?: integer=0`; `state_evaluations_completed?: integer=0`; `simulation_paths_completed?: integer=0`; `candidate_coverage_complete?: boolean=false`; `evaluation_coverage_complete?: boolean=false`; `statistical_precision_complete?: boolean=false`; `ranking_resolved?: boolean=false`; `elapsed_seconds?: number=0.0`; `stop_reason?: string or null=null` |
| `BackgroundResultSummary` | `api_schema_version?: "1.0"="1.0"`; `run: BackgroundRunRecord`; `result: JsonValue` |
| `CandidateQueryPage` | `api_schema_version?: "1.0"="1.0"`; `run_id: string`; `offset: integer`; `limit: integer`; `total: integer`; `sort_key: "candidate_id" / "evaluated_paths" / "requester_improvement"`; `sort_direction: "asc" / "desc"`; `candidates: CandidateSummary[]` |
| `CandidateActionDetail` | `action_index: integer`; `action_type: string`; `team_id: integer`; `counterparty_team_id: integer or null`; `outgoing_player_ids: integer[]`; `incoming_player_ids: integer[]`; `acquired_player_id: integer or null`; `dropped_player_id: integer or null`; `source_candidate_id: string`; `conditional: boolean` |
| `CandidateDetail` | `api_schema_version?: "1.0"="1.0"`; `run_id: string`; `candidate: CandidateSummary`; `actions: CandidateActionDetail[]`; `required_assumptions: string[]`; `structural_intermediate_only: boolean` |
| `CompletedStateDetail` | `api_schema_version?: "1.0"="1.0"`; `run_id: string`; `completed_state_sha256: string`; `candidate_ids: string[]`; `evaluated_paths: integer`; `requester_championship_difference_probability_points: number or null`; `all_team_impacts?: TeamScenarioResult[]=[]` |

### Numerical units and identity scopes

Absolute probabilities/interval bounds are fractions in [0,1]; unavailable estimates/intervals remain null rather than fabricated zero. Paired fields named `*_probability_points`, including `target_paired_half_width_probability_points`, retain **fraction pass-through without service-side scaling**. For example, stored/returned 0.02 means a +2 probability-point delta mathematically; the adapter does not return 2.0. Baseline target_half_width_probability is an absolute fraction. [INTERFACE](INTERFACE.md) owns existing display behavior; [WR-017](BACKLOG.md#wr-017-query-export-and-unit-compatibility) retains a separately approved naming/scaling/presentation migration. No field rename, rescale or second frontend estimator is delivered here.

| Identity | Existing binding / limitation |
|---|---|
| Snapshot | Exact UUID, canonical_sha256, league/season match and original collection context; readable old schemas do not confer live permissions |
| AnalysisProvenance | snapshot/canonical checksum, model_id/ordered parameters, seed/first index/requested paths, simulation_config_sha256, engine_run_identity_sha256, effective_request_sha256 and application identity |
| RunIdentity (`application-run-identity-v1`) | analytical_equivalence_sha256 is the analytical identity; application_execution_sha256 additionally binds complete request, execution nonce and build; presentation_query_sha256 binds the **unfiltered** application result view, not every later page filter |
| BuildProvenance | Installed package version and injected/environment revision or explicit unknown; no Git lookup or authentication of declared source bytes. Mandatory fuller provenance remains WR-021 |
| Search path/state/evaluation | Separate scopes detailed in T7; same ownership alone is not equivalence, and query view is not numerical identity |

Empirical models and validated deterministic/fully-unstarted Monte Carlo partial companions are engine-only. Conditional in-game distributions, arbitrary source selection and current-week action permissions are not public DTO options; no conditional in-game model or new permission is implied. The accepted partial engine subset remains governed by [PARTIAL_WEEK](PARTIAL_WEEK.md); no schema/body field exposes it here. There is no HTTP export/download, automatic run resume, WebSocket stream, arbitrary SQL, historical request/draft rehydration or real ESPN transaction endpoint. A completed result query returns retained results, not a resimulation.

### Errors and version evolution

Typed public errors are API 1.0 `ErrorResponse{error: ErrorDetail{code,category,message,context}}`. Validation locations may be returned without supplied values. Categories are invalid_request, not_found, unsupported_configuration, invalid_scenario, resource_exhausted, engine_invariant and internal_error. Recognized service/domain errors are distinct from unexpected bugs. Credentials, private paths/payloads and tracebacks stay out of public errors.

| HTTP | Current semantics |
|---|---|
| 422 | invalid_request_schema; non-not_found service errors (including resource_exhausted), recognized engine_request_rejected and generic snapshot_store_unavailable; no implied 429 resource-limit contract |
| 404 | not_found service errors, including explicit missing/expired run, snapshot or refresh; unknown routes/static files use framework 404, not the typed-domain envelope guarantee |
| 403 | untrusted_browser_origin on rejected state-changing browser Origin; TrustedHost has its separate framework rejection |
| 500 | snapshot_integrity_failure and unexpected internal_engine_failure/internal_failure; failures are not converted into successful partial analytics |

Within `/api/v1`, names/types/units/null semantics and meaning remain compatible. Safe additive response fields with defaults are allowed. Removing/renaming fields, incompatible meaning/type/unit/null/enum changes or making an optional request field required needs a new API version. Unknown body fields and unsupported api_schema_version fail. Correcting a bug still needs regression evidence and release notes. API 1.0 is independent of canonical reads 2/3/4, companion artifact 1 and storage schemas. Runtime/error/retention details remain with [APPLICATION_SERVICE](APPLICATION_SERVICE.md#api-evolution), not a T8/T9 transfer.

## Search interfaces, indexing and query/export contracts

[M8](METHODOLOGY.md#manual-scenarios-and-action-search-methodology) and [M9](METHODOLOGY.md#decision-evaluation-ranking-and-limitations) define hypothetical meaning, chronology, estimands and ranking. Here the interface maps that experiment to existing [unified_actions.py](../src/fantasy_football/unified_actions.py), [trade_evaluation.py](../src/fantasy_football/trade_evaluation.py), [trade_search.py](../src/fantasy_football/trade_search.py) and [search_orchestration.py](../src/fantasy_football/search_orchestration.py). [UNIFIED_ACTION_SEARCH](UNIFIED_ACTION_SEARCH.md) retains its current binding contract; this is no action-grammar expansion.

### Configuration, leaves and identities

`UnifiedActionSearchConfiguration` supplies requester, declared finite team/player universe, families/orderings, shapes, chain/action lengths, drop/status filters, waiver boundary and protection. The public UnifiedCandidateConfiguration registry above preserves its supported subset. Engine-only options include screening and maximum_completed_paths; lower-level trade/chain interfaces also have incoming/outgoing filters not present on the unified HTTP DTO. No free-form nested configuration passes through the request boundary.

Families are trade, trade_chain and acquisition. Orderings are standalone_trade, standalone_chain, standalone_acquisition, trade_then_acquisition, acquisition_then_trade, chain_then_acquisition and multiple_acquisitions. Configuration must make the requested ordering feasible from the selected families. Omitted `None` drop/status or lower-level incoming/outgoing filters permit the declared eligible universe; explicit empty filters permit none. Empty universe lists are not an unrestricted wildcard. An acquisition leaf is `(acquired player, drop or None, ordinary destination slot)`; legal destination alternatives remain distinct. Trade shapes/partners/players and ordered chain actions remain explicit candidate identity material. Dependency is on a player received in the **immediately preceding** trade; partners cannot repeat consecutively, and no immediate step is scheduled into a future scoring week. [Current grammar](UNIFIED_ACTION_SEARCH.md#families-and-action-grammar) owns exact generation/completion rules.

| Identity / interface | Binding and retrieval consequence |
|---|---|
| Candidate path | Snapshot/baseline, normalized unified configuration, ordering and ordered source actions; standalone trade identity is discovery-filter independent, while acquisition identity includes normalized search and full destination leaf |
| `completed_state_fingerprint()` | `m5.3-completed-simulation-state-v1`: normalized snapshot and full evolving state, excluding path labels/descriptions; ownership/slots, availability/holds, current/initial priorities, week/cycle, counters, IR evidence, assumptions and acquisition ledger matter |
| `evaluation_fingerprint()` | `m5.3-shared-paired-evaluation-v1`: snapshot and baseline/completed-state pair plus public model/ordered parameters, seed/path range, simulation policies and precision/settings; worker count is not mathematical identity |
| Candidate-state registry | `build_candidate_state_registry()` / `validate_candidate_state_registry()` verify payload hashes, snapshot/schema, baseline and screening provenance; many path IDs can share one exact state evaluation without erasing lineage |
| Orchestration run_sha256 | `m5.8-search-orchestration-v1` binds snapshot/baseline, candidate-search identity, evaluation mode, supplied sampling, numerical run identity and ordered candidate IDs; **not every resource/export setting, exposure, timing or export byte** |

Same final player ownership is insufficient; do not round values to manufacture equivalent states. Reuse is within the validated execution, not a global/cross-refresh cache. Fixed/progressive paths use matched baseline draws and existing all-team evaluation. Configured screening/caps can remove candidate coverage; state coverage, precision and ranking remain independent. WR-025's repeated precision limitation persists; no new convergence claim follows from shared evaluation identity.

### Preflight, bounded execution and trusted indexing

`SearchOrchestrationConfiguration` combines candidate_search, evaluation_mode, sampling, resources, preflight and export. `SearchResourceConfiguration` has the public resource fields above plus engine-only index_directory. `maximum_completed_paths` must be unset under orchestration; use its candidate_limit instead. `evaluation_state_limit` overrides the sampling state budget. `simulation_path_budget` caps paths **per state**, not total search work. `maximum_in_flight_states` maps to max_in_flight_tasks; it does not run multiple candidate-state evaluations concurrently. Fixed versus progressive evaluation and worker/batch controls reuse existing coordinators rather than creating another probability engine.

Optional `SearchPreflightConfiguration(enabled=False,candidate_sample_size=10,monte_carlo_sample_paths=2)` measures a bounded prefix/one batch where possible. It is engine-only, not a public action-request field; results are not universal runtime estimates or child-memory measurements. One nominal deadline begins before preflight, but preflight finishes its bounded sample before later boundary checks. Expensive completion/V(R)/exact batches can overrun; report wall_clock_overrun_seconds, actual coverage and unmet targets. Stop requests currently use the wall-clock-limit label. There is no preemptive timeout or search-level durable resume. Editable quick/balanced/high_precision/exhaustive/full_bounded presets guarantee neither completeness nor precision.

`sequential_reference` materializes candidates; `bounded_overlap` uses producer→bounded queue→temporary SQLite with backpressure/index batches. Only generation/indexing overlaps; statistical evaluation waits for eligible-state discovery to preserve order-neutral initial exposure. No nested candidate-worker pool is created. Bounded queue/page sizes do not prove constant total memory: `state_ids()` materializes IDs and compact progressive comparisons remain resident.

`SearchResultIndex` stores trusted-process pickle candidate/state/result payloads; it is not public interchange, an independent forged-input validator or a safe untrusted import format. Use `result.iter_candidates()` in either mode: bounded result.candidates is intentionally empty. Index iteration pages by last candidate ID (`candidate_id > last`, ascending), distinct from HTTP offset pagination. Successfully returned result handles are caller-owned and require `close()` in finally; the index has context-manager methods, **the result handle does not**. Closure is idempotent and removes temporary DB/sidecars. Creation/bounded-generation failures close explicitly; **WR-026** retains the missing encompassing guard for later evaluation/progress/export failures before return. Garbage collection is not deterministic cleanup acceptance. [C13](APPLICATION_SERVICE.md#retention-authority) preserves separate scratch, bounded durable history, checkpoint, immutable snapshot and user-export ownership; exact T8/T9 runtime/storage/lifecycle details stay with their current owners.

### Retained HTTP query allowlist

Candidate/state/detail lookup is scoped by run_id and requires its completed retained result; candidate/state IDs cannot authorize access across runs. Candidate detail preserves ordered actions/assumptions; state detail groups candidate IDs for the exact completed_state_sha256 and stored all-team impacts. Querying never invokes Monte Carlo. The source is `BackgroundRunStore.query_candidates()` in [background.py](../src/fantasy_football/app/background.py).

| Parameter | Supported values / meaning |
|---|---|
| `sort_key` | `candidate_id`, `evaluated_paths`, `requester_improvement` |
| `direction` | `asc`, `desc`; candidate_id ascending breaks ties; unavailable improvement sorts last in both directions |
| `ordering` | `standalone_trade`, `standalone_chain`, `standalone_acquisition`, `trade_then_acquisition`, `acquisition_then_trade`, `chain_then_acquisition`, `multiple_acquisitions` |
| `authorization` | `transaction_authorized`, `structural_hypothetical` |
| `acquisition_status` | `not_applicable`, `immediate_free_agent`, `conditional_waiver`; these are result conditions, not the input free_agent/waivers/hold/unresolved filter |
| `evaluated` | boolean or omitted; true means evaluated_paths>0, false means evaluated_paths=0, not a precision/coverage test |
| `team_id` | positive involved-team ID, not a filter on that team's statistical benefit |
| `offset`, `limit` | offset >=0; limit 1–200, default 50; response total counts matching rows before pagination |

Recognized filter clauses combine with AND, then global sort, then LIMIT/OFFSET. A page is not the universe. Local page-only text filtering/sorting cannot be presented as a globally selected result. Unsupported recognized sort/filter values fail with invalid_candidate_sort/invalid_candidate_filter; invalid bounds use invalid_page. Extra undeclared HTTP query keys are ignored rather than new operators. There is one sort key, no arbitrary SQL or compound-statistic/range/multi-sort query grammar. Client [Opportunity Explorer](../frontend/src/OpportunityExplorer.tsx) and [API client](../frontend/src/lib/api.ts) consume this existing allowlist.

### Existing exports and deferred parity requirements

Engine-only `SearchExportConfiguration(output_directory=None,write_json=False,write_csv=False,filtered_candidate_ids=None)` writes `m5_8_search_results.json` / `m5_8_search_results.csv`. Enabled export requires an output directory; duplicate selected IDs reject and unknown IDs fail. None selects all current candidate-result rows; an explicit empty tuple selects none. A selected-ID subset **preserves existing result iteration order**, not the caller's requested-ID order. Reference iteration and indexed iteration remain distinct implementation paths whose byte parity is tested on equivalent fixtures. Filtering/export does not rerun analysis or alter run_sha256, and that ID is not an export checksum.

JSON schema_version=1 includes run_sha256, scope (all/filtered), coverage/precision/ranking flags, overrun, candidate rows and matching compact state_evaluations with matched_path_count and all-team championship/qualification/final-placement metrics. CSV columns are exactly SearchCandidateResult fields: candidate_id, ordering, completed_state_sha256, execution_status, acquisition_status, action_count, evaluated_paths, requester_championship_difference, statistically_competitive, precision_reached, execution_caveats. Caveats are joined by a literal vertical bar. CSV is a candidate summary, **not the JSON all-team/statistical/configuration payload**. Engine differences/intervals retain fraction units; no export scaling occurs. Full mode retains available state comparisons; filtered JSON keeps only evaluated states associated with selected candidates. Candidate and comparison scopes can differ when paths are unevaluated. Streaming candidate pages does not imply streaming/constant-memory statistical payloads or durable resumability.

The current engine export is not an HTTP download endpoint, a shared global HTTP filter/sort export pipeline, a complete transaction/team/player/position export, or proof all richer export metadata requirements are implemented. [WR-017](BACKLOG.md#wr-017-query-export-and-unit-compatibility) retains approved future compound/range/multi-sort per-team querying, normalized run/scenario/team summaries, and exports of **all candidates receiving any Monte Carlo evaluation** or the **current filtered subset**, preserving selected sort, filters, scope, complete identity, path counts, all-team deltas/intervals, target/config/model/snapshot/as-of metadata and browser/developer parity without resimulation. Those obligations remain outstanding; no new query operator, export field or compatibility migration is delivered. Optional export files stay user-owned under C13; scratch closure/run deletion must not delete them or silently reuse them in a new search.

### Source mapping, evidence and deferred owners

| Accepted source inventory | P7c destination / retained boundary |
|---|---|
| APPLICATION_SERVICE S032–S034 route/DTO/evolution; S042 identity; S045 errors | T5 route/schema/units/error/compatibility map; exact implementation checked against http.py/contracts.py/service.py. Current application authority remains; runtime/process/storage/security contracts are not transferred |
| UNIFIED_ACTION_SEARCH S182–S192 grammar/filters/identity/evaluation | T7 interface/leaf/identity map; methodology M8/M9 and current owner retain analytical chronology, estimator and ranking meaning |
| UNIFIED_ACTION_SEARCH S193–S194 resources/index/export; Application S040 query/result semantics | T7 bounded/preflight/query/export and exact limitations; T8/T9 lifecycle/persistence remain with existing owners, WR-026 unchanged |
| INTERFACE current display/query boundaries; BACKLOG S064 WR-017 | T5 actual fraction pass-through and T7 global-versus-page semantics; approved richer query/export/unit compatibility obligations remain exact BACKLOG text, not implemented endpoints |

[Service/transport tests](../tests/test_app_service.py), [retained queries](../tests/test_background_runs.py), [cross-layer tests](../tests/test_backend_validation.py), [search/export tests](../tests/test_search_orchestration.py), [unified grammar tests](../tests/test_unified_actions.py) and [focused contract map](../tests/test_transport_documentation.py) establish **Verified by tests** source/fixture consistency. They do not prove live ESPN, actual browser behavior, calibration or release readiness. Developer commands remain in [CONTRIBUTING](../CONTRIBUTING.md#change-based-verification-matrix); API/engine contracts, M0 bindings, historical identities/artifacts, C13 and WR-021 release gates remain unchanged. No P7d, M0 migration, authority retirement or release declaration is included.
