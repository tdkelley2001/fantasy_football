# War Room technical reference

**P7a pilot: T2 source/dataset interfaces only.** [DATA](DATA.md) retains canonical/source/serialization/publication authority and [RESEARCH](RESEARCH.md) retains research interfaces and M0 bindings. This chapter makes the source contracts findable without transferring unfinished technical sections or retiring their owners. Analytical meaning is in [METHODOLOGY](METHODOLOGY.md); evidence adequacy in the [V3 pilot](VALIDATION.md#empirical-validity). [Authority and precedence](../AGENTS.md#authority-and-precedence) and all [BACKLOG](BACKLOG.md) obligations remain binding.

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
