# Pre-M3 Repository Consolidation and Health Audit

Baseline reviewed: `381fdb2f66969c1d92910c3e63be974bace1fcb3` (22 October 2026).
This audit is a consolidation checkpoint. It does not implement M3.1.

## 1. Executive summary

The repository is ready for independent pre-M3 sign-off. M0, M1, and
M2.1–M2.6 are complete and accepted. No blocking correctness, data-integrity,
credential, or league-size hardcoding defect remains in the reviewed production
paths. Two important pre-M3 defects were corrected: the future-data diagnostic
no longer describes 14 teams as universal, and simulation identity now
canonicalizes only known unordered snapshot record collections while preserving
ordered configuration values. Eleven static unused-code findings were removed
without changing behavior. No production module was established as obsolete, so
none was removed.

## 2. Repository module and public-interface inventory

The classifications below cover every production Python module. “Active” APIs
are runtime engine contracts; “diagnostic” APIs are supported read-only tools;
“reference” APIs are retained correctness oracles, not dead code. Dataclass and
enum names are grouped with their module's functions.

| Module | Classification | Public surface and supported role |
|---|---|---|
| `__init__`, `canonical.__init__` | Active package boundary | Package markers; no executable public functions. |
| `__main__`, `healthcheck` | Supported CLI | `main`; configuration/logging smoke check, no network. |
| `config` | Active infrastructure | `Settings`, `EspnCredentials`, `load_settings`; validated local configuration. |
| `logging_config` | Active infrastructure | `configure_logging`. |
| `canonical.model` | Active production | Schema-v3 enums and immutable records from `SourceReference` through `LeagueSnapshot`; schema-v2 read compatibility constants. |
| `canonical.serialization` | Active production | `snapshot_to_json`, `snapshot_from_json`, `CanonicalSerializationError`. |
| `canonical.validation` | Active production | `validate_snapshot`, `require_understood_rules`, `CanonicalValidationError`. |
| `espn_connectivity` | Supported diagnostic CLI | Connectivity records plus `audit_league`, `fetch_and_audit`, `render_summary`, `main`. |
| `future_data_audit` | Supported diagnostic CLI | Pool/evidence/report records, parsers/retrieval, `audit_live`, `render_summary`, `main`. |
| `historical_projection_audit` | Supported diagnostic CLI / M3 evidence input | Historical records, parsing/retrieval, coverage summaries, `audit_live`, `main`. |
| `league_rules_audit` | Supported diagnostic CLI | Rule report builders, roster/waiver/trade/schedule/bracket audits, `audit_live`, `main`. |
| `projection_ui_reconciliation` | Supported diagnostic CLI | Reconciliation records, `build_examples`, `reconcile_live`, `render_report`, `main`. |
| `undroppable_audit` | Supported diagnostic CLI | Coverage/report records, `audit_undroppable_evidence`, `main`. |
| `m0_verification` | Supported diagnostic CLI | Evidence manifest `build_report`, `render_summary`, `main`. |
| `espn_adapter` | Active retrieval/translation + CLI | Captured source/bundle/result records, retry/capture/config helpers, `translate_bundle`, `retrieve_bundle`, `fetch_and_translate`, `main`. |
| `quality` | Active production | Diagnostic/report records and `generate_quality_report`. |
| `snapshot_store` | Active persistence + publication CLI | Metadata/load/integrity records, `SnapshotStore`, `publish_and_verify`, compatibility `main`. |
| `snapshot_cli` | Supported management CLI | `select_snapshot`, `build_listing`, `build_inspection`, `main`. |
| `lineup_optimizer` | Active production/reference | Slot/assignment/vacancy/result records, roster validation, `optimize_candidate_lineup`, `optimize_starting_lineup`. |
| `weekly_engine` | Active production | Standings/scoring/transition records, `initialize_standings`, `rank_standings`, `resolve_regular_season_week`. |
| `evolving_state` | Active production | Immutable state/evidence/ledger contracts and pure add/drop/replace/IR/priority/release/cycle transitions. |
| `roster_value` | Active production + reference | V(R) records, `value_roster`, hypothetical/comparison helpers; `exhaustive_allocation_oracle` is the retained exact small-case oracle. |
| `weekly_transactions` | Active production | Policy/diagnostic/result contracts, `require_supported_transaction_rules`, `execute_weekly_essential_transactions`. |
| `transaction_cycle` | Test/reference implementation | Exact feasible-cycle and independent sequential-policy contracts and comparison/equivalence functions. Intentionally retained for AGENTS.md oracle requirements. |
| `postseason` | Active production | Settings-driven graph/state/result contracts, graph generation, seeding, initialization, scoring/advancement, completion check. |
| `season_simulator` | Active production / extension point | Deterministic scenario, participation policy and result contracts; `simulate_deterministic_season` is the M2.5 coordinator and stable input to later models. |
| `player_outcomes` | Active provisional extension point | `PlayerOutcomeModel` protocol, `ProvisionalNormalModel`, projection-class summary. Deliberately swappable for M3; not calibrated. |
| `monte_carlo` | Active production, provisional statistical layer | Configuration/path/batch/aggregate contracts, fingerprinting, path/batch execution and exact batch combination. |

Repository-wide searches also confirmed every module-level `main` is either
reachable through `python -m ...`, documented, or retained as a compatibility
publication command. Public functions used primarily by tests are explicit
oracles or supported external/programmatic interfaces, not removal candidates.

## 3. Dead-code findings

| Priority | File/symbol | Evidence and risk | Disposition |
|---|---|---|---|
| Important cleanup | `canonical/serialization.py`, `espn_adapter.py`, `projection_ui_reconciliation.py` imports | Ruff F401 found three unused imports. No references or import side effects. | Removed. |
| Important cleanup | Six assignments in `canonical/validation.py` | Ruff F841; five assignments retained only the necessary `_unique()` validation side effect and one dictionary was never consumed. | Kept validation calls, removed unused bindings/dictionary. |
| Important cleanup | Two exception aliases in `evolving_state.py` | Ruff F841; messages intentionally do not include source exception content. | Removed aliases; error contract unchanged. |
| Nonblocking | Public APIs with no internal production caller | Tests, documentation, CLIs, and intended external use establish support. | Retained. |

No unreachable production branch or safely removable module was established.
The audit deliberately preserves independent exhaustive references and historical
ESPN diagnostics.

## 4. Duplicate or outdated functionality

No competing canonical model, persistence store, lineup policy, transaction
legality engine, or roster valuation engine was found. Similar logic in
`transaction_cycle` and test oracles is intentionally independent validation,
not accidental duplication. `snapshot_store.main` and `snapshot_cli.main` have
different supported roles (publication versus read-only management). Historical
diagnostics retain evidence-specific parsers and are not imported into simulation
hot paths.

Outdated status prose in README, roadmap, and master specification was corrected
to the accepted M2 baseline. Historical test counts and live observations remain
identified as historical evidence rather than rewritten as current executions.

## 5. League-configurability findings

The standing detailed inventory is [LEAGUE_CONFIGURATION_AUDIT.md](LEAGUE_CONFIGURATION_AUDIT.md).
The review covered team counts, slot capacity/eligibility, scoring, waiver type
and priority, IR, limits, periods, seeding, brackets, consolation and placements.

- Canonical API-derived: league/team universe, configured slots and eligibility,
  scoring, acquisition settings/limits, matchup periods/schedules, standings,
  qualifier counts and supported postseason rules.
- Validated manual configuration: explicit consolation transitions and active-only
  postseason transaction participation, both provenance checked.
- Approved named assumptions: missing-projection effective zero,
  projection-based IR recovery, modeled weekly waiver boundary, reverse frozen
  priority for immediate free agents, all-team postseason participation, and the
  provisional independent-Normal outcome model.
- Universal invariants: unique ownership/IDs, finite values, capacity, one player
  per lineup/allocation, immutable state, checksum integrity and complete team
  permutations where a result claims completeness.
- Unsupported/unresolved: FAAB execution, exact live waiver-clearance timing,
  future strict-IR facts, certain championship placement cohorts, odd consolation
  bye reentry, unknown consolation enablement and unsupported tiebreak rules.

No production fantasy-team-count constant was found. NFL's 32-team completeness
check is a domain-universe invariant, not a fantasy league template. Explicit
14-team values remain only in historical evidence, examples and representative
fixtures. The verified defect in `future_data_audit.audit_live` was corrected so
its description uses the explicit `expected_team_count` argument.

## 6. Configuration-fingerprint assessment

The accepted snapshot normalizer already sorts only named unordered canonical
record collections. A remaining outer `_order_independent()` pass then sorted
every nested list in the entire payload, erasing potentially meaningful model or
policy sequence order. This was a verified identity defect: two ordered parameter
sequences could hash alike. The outer normalization was removed. JSON object keys
remain canonically sorted; known unordered snapshot records remain schema-aware;
nested and configuration sequences retain order.

Tests establish that reordered canonical player/player-week/roster records keep
the same fingerprint, an ordered model-parameter change produces a different
fingerprint, every supported policy changes identity, disjoint compatible batches
merge exactly, and existing stable player/week/path score generation is unchanged.
The accepted random-key algorithm was not modified.

## 7. Documentation inconsistencies resolved

- README, roadmap and master specification now identify M0, M1 and M2.1–M2.6
  as complete and accepted; M3.1 is next and not started.
- Stale M2.3 review-pending labels and descriptions saying later M2 engines were
  unimplemented were removed while preserving their historical evidence.
- README now indexes every current M2 technical contract and this audit.
- The standing league configuration audit records the dynamic future-audit text
  and order-aware fingerprint semantics.
- A credential-free test now verifies every relative Markdown file link under
  README and `docs/` resolves.

## 8. Remaining known technical limitations

The outcome model is provisional and uncalibrated; M3 must not treat current
frequencies as empirically calibrated probabilities. Historical ESPN projections
lack authenticated pregame revision timing. Exact small-case allocation and cycle
references are combinatorial and deliberately not full-league exhaustive trees.
The ESPN waiver/IR/postseason limitations listed above remain capability-specific
fail-closed boundaries. There is still no integrated end-user M6 CLI for season
forecasting or decision search.

## 9. Quality-tool findings

Python 3.12 bytecode compilation succeeds. Ruff's narrow correctness profile
(`F,E9`) now reports no production or touched-test findings. Ruff was not added
to the locked runtime/test dependency set merely to impose style policy; the
command is an optional developer audit until a separately approved tooling change
locks it. The new pytest documentation-link check uses only the standard library
and the already locked test stack. Broad formatting, typing-framework adoption,
and cosmetic refactoring were intentionally excluded.

## 10. Tests and performance evidence

The complete credential-free suite collected and passed **511 tests in 17.52
seconds** on Python 3.12.10. This comprises the accepted 487-test baseline plus
the new fingerprint, dynamic-description, and 23-document link checks. Focused Monte Carlo tests cover path replay, draw
stability, all configuration identities, reconciliation and batch merging. These
changes do not alter lineup, transaction, season, score-draw or aggregation hot
paths. Fingerprinting performs less generic recursive sorting than before; no
runtime or memory regression is expected or observed in focused runs. Historical
accepted performance measurements remain in the relevant module documents and
are not relabeled as newly executed benchmarks.

## 11. Remaining risks

- **Blocking correctness/data integrity:** none found.
- **Important before interpreting M3 results:** historical pregame provenance and
  outcome-model calibration remain the explicit purpose/gate of M3.1–M3.3.
- **Nonblocking maintenance:** formal lint/tool locking and broader static typing
  may be evaluated later based on demonstrated value.
- **Deferred:** unsupported ESPN transaction/postseason configurations and
  full-league exhaustive counterfactual search remain documented capability gaps.

Tracked-file review found no `.env`, database, bytecode or local output artifact.
`.gitignore` covers credential variants, SQLite sidecars, outputs, environments,
coverage and build products. Pure simulation modules contain no ESPN retrieval;
network access remains confined to explicit diagnostics/adapters.

## 12. Recommendation

**GO for independent pre-M3 sign-off and, after that approval, M3.1.** The code
base has a coherent accepted M2 boundary, deterministic and immutable references,
explicit unsupported capabilities, reconciled documentation, and a clean
credential-free regression baseline. This audit does not start or pre-approve
M3.1 implementation.
