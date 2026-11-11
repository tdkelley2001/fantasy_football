# WR-022 missing-projection deterministic-zero correction

Current disposition: **ACCEPTED**, merged at `28bf60589b6e6856ab8ec40d55486b4da2c62bdd` ([PR #117](https://github.com/tdkelley2001/fantasy_football/pull/117)), as confirmed by R2.4 authorization. The policy, implementation and collision follow-up are accepted. Review-state statements and measurements below are preserved delivery-time evidence; this status note does not change or reopen the numerical contract.

Policy decision: explicitly approved by the Missing-Projection Deterministic-Zero Correction authorization following accepted R2.3 `79033ae`. Implementation is **In Review** on `fix/WR-022-missing-projection-zero`; independent implementation acceptance is not yet established. This separate modeling correction resolves R23-06 and does not begin another R2 documentation milestone.

## Root cause and rule

`ProvisionalNormalModel.generate_scenario` previously applied `mean + sigma * Z` to every canonical in-horizon player/week, including `MISSING` with effective mean zero. Positive base dispersion could produce a nonzero missing outcome. Ordinary projected lineup eligibility still excluded nonpositive projections; generated records were not authority to select a player. The empirical model already returned deterministic zero for missing records.

The approved rule now requires exact `0.0` for **canonical `ProjectionClass.MISSING`**, in every supported outcome family and under every distribution configuration. Normal skips its dispersion/random-number call for that class. Empirical needs no implementation change. Raw `None`, effective zero, classification and source provenance remain intact. Explicit ESPN zero remains distinct: Normal keeps its established zero-mean distribution, empirical its established deterministic zero. Positive and finite negative draws, lineup eligibility, ingestion, deterministic caller-supplied values, fixed actuals, transactions and league mechanics are unchanged.

Implementation: [player_outcomes.py](../src/fantasy_football/player_outcomes.py). The `PlayerOutcomeModel` protocol documents this obligation for replacement implementations; the two supported production families are Normal and empirical. A caller-defined model must honor the protocol; this correction does not add a general plugin-output correction wrapper or silently rewrite arbitrary supplied deterministic scenarios.

## Compatibility decision

Changing Normal's draw-key parameters or feeding a new public identity into its draw hash would change valid-projection outcomes, which is explicitly forbidden. Reusing historical public identity inputs would instead permit checkpoints/comparisons to alias different numerical behavior. The compatibility follow-up separates public policy parameters from historical draw parameters:

- Public `model_id` remains `<version>:missing-projection-zero-v1`. Public `parameters` appends `("missing_projection_outcome", "deterministic-zero-v1")` to the three historical entries. A historical caller could choose a `version` identical to the suffixed model ID, so the suffix alone was insufficient. Historical Normal parameters always have exactly three entries and cannot contain this discriminator for any supported custom version string.
- Private `_draw_parameters` retains exactly `base_stddev`, `projection_scale`, `conditional_independence`, in their original order/types. The SHA-256/Box–Muller draw key uses the original `version` and this three-entry tuple, not the public model ID or four-entry public parameters. All draw-key bytes remain unchanged. Nonmissing outcomes are bit-identical to the historical implementation; no shared RNG sequence is advanced for missing records.
- Generated score-scenario IDs incorporate the public model ID. Existing Monte Carlo configuration/run identities, worker binding, precision/checkpoint compatibility and numerical comparison/search evaluation identities include model identity; they now distinguish corrected Normal semantics without changing their algorithms or formats. Structural roster-state/candidate IDs need not change when the structural action is unchanged; their numerical evaluation identity remains separate.
- This deliberately invalidates **all prior Normal checkpoints**, including earlier PR #117 checkpoints without the public parameter discriminator and snapshots with no missing records. Existing checkpoint loading compares configuration/run fingerprints and the serialized full public parameter list; it fails before writing or executing new paths. Empirical identities and outcomes remain unchanged. No checkpoint schema or fingerprint algorithm changes.
- Retained snapshot/run/result rows, original IDs, checksums and old model metadata are never migrated or rewritten. Historical results remain inspectable as historical. Exact reproduction of old Normal runs requires the prior code/model implementation, not corrected code relabeled with an old identity. There is no production legacy-policy switch.

## Expected versus unexpected numerical changes

Expected: missing Normal player/week records become exact zero; corrected Normal model/scenario IDs and configuration/run fingerprints change globally. The score-content digest changes only when score content changes; all-nonmissing scenarios retain that digest despite their new model/scenario identity. Ordinary whole-week team/season outcomes should remain unchanged when the only score-record changes are unavailable missing players. Explicit-zero and all finite present Normal draws must be identical, not merely distributionally similar. Empirical remains unchanged.

The two accepted `432a85f` golden hashes in `test_partial_monte_carlo.py` are **not changed**. They are exercised using [a frozen pre-correction test oracle](../tests/legacy_normal_reference.py), captured from accepted `79033ae`'s draw formula. This test-only oracle is not a supported production family. New tests independently compare corrected nonmissing scores with that historical algorithm across seeds, paths, classifications and custom versions. Old/new identity differences are asserted explicitly instead of replacing golden values to make tests pass.

## Verification

The following counts record the initial WR-022 implementation before its identity-collision follow-up. Follow-up verification is recorded separately below.

Focused command: `.venv\Scripts\python.exe -m pytest tests/test_missing_projection_zero.py tests/test_partial_monte_carlo.py -q -p no:cacheprovider --tb=short` — **53 passed**, 9.89 s. Includes both families, large dispersion, exact zero across seeds/paths, skipped RNG for missing, unchanged explicit zero/positive/negative draws, canonical nonmutation, ordinary lineup exclusion, batch/order/worker/task parity, sequential/parallel checkpoint resume, old-checkpoint rejection without byte changes and matched hypothetical swaps. Old/new ordinary team/path outcomes agree for both all-present and missing-containing snapshots; their numerical policy identities intentionally differ. Empirical identity and explicit-zero behavior are checked separately.

Full tier: `.venv\Scripts\python.exe -m pytest -m "not windows_process" -q -p no:cacheprovider --tb=short` — **1,086 passed, 14 deselected**, one existing Starlette/AnyIO deprecation warning, 122.98 s. Includes canonical/schema/storage compatibility, retained results, scenario/action/search comparisons, deterministic/partial/MC, workers/checkpoints and reference/golden coverage. The initial broad run reported 1,071 passed/11 documentation-link failures because it started before this linked report had been created; the completed final tier passes. No numerical regression or unexpected golden change was found.

Documentation/security tier: `.venv\Scripts\python.exe -m pytest tests/test_documentation_links.py tests/test_contributor_documentation.py tests/test_technical_documentation.py tests/test_repository_security.py -q -p no:cacheprovider --tb=short` — **120 passed**. Full Ruff and format-check on the two new test modules pass; repository narrow gate `.venv\Scripts\python.exe -m ruff check --select E9,F63,F7,F82 .` and `git diff --check` pass. Full Ruff on the production module reports existing `C401` at its unchanged empirical validator; running the same check against accepted `79033ae` reproduces it. That unrelated cleanup was not performed. Production-wide formatting was not applied.

Source comparisons confirm empirical class AST, ingestion, canonical/storage, lineup/weekly/season, MC/scenario algorithms, frontend/dependencies and both original golden hash constants are unchanged. Only the Normal generator/public model identity and explanatory protocol/docstrings change in production. No live ESPN, private store operations, real-process recovery, dependency changes or UI work is performed. Fixture results establish **Verified by tests**, not a new **Verified live** source claim. Historical exact replay still requires the historical implementation; automatic legacy-policy execution is not added.

## Changed files and review

Production change is confined to `player_outcomes.py`. Focused tests are new `test_missing_projection_zero.py`, the frozen legacy oracle and the historical-golden call sites in `test_partial_monte_carlo.py`. Governing policy/specification and outcome/MC references explain the approved change; R23-06, current status and the stable [WR-022 backlog entry](BACKLOG.md#work-items) record its disposition. No canonical schema, snapshot serialization/storage or API contract changes. Implementation acceptance and its final review reference must be recorded only after independent review.

## Identity-collision follow-up

Before implementation, a read-only reproduction constructed `LegacyNormalReference(2.0, 0.1, corrected.model_id)`. Its serialized public identity, configuration fingerprint and seed-bearing run identity each equaled the original PR model's values. Source inspection confirmed fingerprints serialize the ordered parameter tuple as JSON arrays, and checkpoint validation compares both identities plus the full parameter list. The correction adds this fourth public array:

```json
["missing_projection_outcome", "deterministic-zero-v1"]
```

Draw hashing continues to serialize only the original three arrays. Regression coverage explicitly retains equal public model IDs for the adversarial historical/custom case, asserts unequal serialized public parameters and configuration/run fingerprints, and rejects its old checkpoint without modifying its bytes. Nonmissing draw comparisons include that custom version string. The frozen historical oracle and both golden constants are unchanged.

This follow-up changes only the public Normal identity parameters, their separation from draw parameters, focused regression assertions and the identity documentation. Relative to the initial PR, the public model ID, generated scenario ID and score-content digest remain unchanged; configuration/run/evaluation fingerprints change because the serialized public parameter list now has four entries. The deterministic-zero policy and previously reviewed numerical behavior do not change. [PR #117](https://github.com/tdkelley2001/fantasy_football/pull/117) remains pending independent acceptance.

Follow-up checks executed:

- `.venv\Scripts\python.exe -m pytest tests/test_missing_projection_zero.py tests/test_partial_monte_carlo.py tests/test_player_outcomes.py tests/test_m33_player_outcomes.py -q -p no:cacheprovider --tb=short` — **75 passed**, 10.52 s. Includes adversarial equal-ID serialization/configuration/run identity, unchanged checkpoint bytes, custom-version exact draws, historical goldens, parallel/batched/resumed and matched-scenario cases.
- `.venv\Scripts\python.exe -m pytest tests/test_monte_carlo.py tests/test_monte_carlo_parallel.py tests/test_monte_carlo_execution.py tests/test_monte_carlo_precision.py tests/test_scenario_evaluator.py tests/test_trade_search.py tests/test_unified_actions.py tests/test_app_service.py -q -p no:cacheprovider --tb=short` — **161 passed**, one existing Starlette/AnyIO warning, 38.71 s.
- `.venv\Scripts\python.exe -m pytest tests/test_documentation_links.py tests/test_contributor_documentation.py tests/test_technical_documentation.py tests/test_repository_security.py -q -p no:cacheprovider --tb=short` — **120 passed**.
- Full Ruff/format-check on the focused test module, narrow production Ruff gate (`--select E9,F63,F7,F82`) and `git diff --check` — passed. The frozen historical oracle and golden constants are unchanged. No new full-repository, live ESPN, private-store or real-process recovery run was performed for this follow-up.
