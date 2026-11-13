# War Room validation

**P7a pilot: V3 only.** This chapter explains empirical evidence and its limits. [RESEARCH](RESEARCH.md) remains the authoritative research contract, including all M0-bound sections; [PLAYER_OUTCOME_MODEL](PLAYER_OUTCOME_MODEL.md) remains the generation/promotion owner. No authority is retired or executable evidence role moved. Other validation sections are not transferred here. Requirements remain binding under [authority and precedence](../AGENTS.md#authority-and-precedence); [BACKLOG](BACKLOG.md#data-research-and-m0-migration-obligations) retains the unfulfilled evidence and release obligations.

## Empirical validity

The question is whether a method predicts or supports decisions on authentic, representative future cases. A synthetic oracle can prove that code implements an equation or preserves path identity; it cannot prove that an ESPN forecast existed before kickoff, that its error distribution is calibrated, or that a decision proxy improves championships. [M2](METHODOLOGY.md#player-outcome-generation-and-assumptions), [M6](METHODOLOGY.md#monte-carlo-simulation-and-estimators) and [M7](METHODOLOGY.md#statistical-inference-precision-and-uncertainty) describe the mathematical experiment. Monte Carlo sampling uncertainty conditional on a model is separate from empirical model/data uncertainty.

### Evidence admissibility before evaluation

Start with [D2 source trust](DATA.md#source-trust-coverage-and-research-data). A usable projection/error pair needs a raw forecast and an actual, matching player/season/week and scoring context. Missing and policy-imputed-zero projections are excluded; explicit ESPN zero and signed projections remain observations. An actual zero is an outcome, not proof of nonparticipation. Historical universe completeness and point-in-time player/scoring context remain uncertain even when a pair exists.

For authenticated pregame evidence, [RESEARCH’s gate](RESEARCH.md#external-trust-and-exact-row-binding) requires an independently provisioned trusted manifest digest, exact payload bytes and capture strictly before the observation period. The accepted parser reparses those bytes; dataset construction binds every row's player, season/week, projection, position and NFL team, plus identical source metadata and period boundary. An invented player or modified projection cannot inherit authentication from a legitimate source ID. Actuals require a separate source retrieved at or after period end. [T2](TECHNICAL_REFERENCE.md#research-source-and-dataset-interfaces) describes schemas and validation interfaces.

The validator tests structural authentication, not who really provisioned a hash. Hashing one's own untrusted manifest does not establish independent trust. Operational evidence needs an independently controlled registry/review record and retained private bytes. No authenticated live capture program is established by this pilot.

A hand-checkable dataset example (one selected period, unverified historical sources, distinct players) illustrates eligibility rather than calibration:

| Player | Raw projection | Policy imputation | Actual | ProjectionValueKind | Exploratory pair |
|---|---:|---:|---:|---|---|
| 1 | null | null | 4 | missing | no |
| 2 | null | 0 | 3 | model_policy_imputed_zero | no |
| 3 | 0 | null | 0 | espn_explicit_zero | yes |
| 4 | -2 | null | -1 | espn_value | yes |

There are four rows, two raw forecasts, four actuals, two pairs, two missing forecasts (including one disclosed imputation), one explicit forecast zero and zero authenticated pairs. No completion/participation or promotion conclusion follows. Changing player 3's actual to missing removes its pair; substituting a policy zero for either missing raw forecast cannot restore it.

### What the retained evidence supports

The [dated evidence record](RESEARCH.md#evidence-and-hypotheses) reports 8,760 selected 2024/2025 player-weeks, 7,489 projections, 5,214 actuals and 5,000 structural pairs. The later authorized schema-2 materialization divided the pairs into 2,638 training and 2,362 evaluation rows, with **zero authenticated-pregame pairs**. Availability was **Verified live** in those particular historical retrievals; parser/guard behavior is **Verified by tests**. Pregame timing remains **Unverified**; forecast vintages/revision sequences and horizon labels are **Unsupported** by the investigated source.

The projection-band empirical candidate's exploratory CRPS 2.0294 versus projection-band Normal 2.0544 is not a promotion decision: `recommended_candidate_id` remained null. Retrospective response coherence does not establish forecast vintage. Revisions, changed scoring/position/team wrappers, missingness and selected seasons/weeks may bias the comparison. There is no independently known complete historical denominator. These are retained findings, not new retrieval or recalculation.

### Temporal evaluation and support

The implemented [research interface](RESEARCH.md#temporal-evaluation-and-candidates) validates dataset identity and uses one explicit chronological boundary `(evaluation_start_season, evaluation_start_week)`: earlier periods train, boundary-or-later periods evaluate. There is no random player-week split. **This is not a sealed final-test process or automated protection against repeated tuning.** The governing promotion program still requires temporal training/validation/sealed-test separation and tuning isolation, with prospective/held-out evidence where feasible.

`AUTHENTICATED_ONLY` includes exact-row-bound pregame pairs. `INCLUDE_UNVERIFIED_EXPLORATORY` permits exploratory comparisons but cannot produce a calibrated-model recommendation. Missing/insufficient materialized data yields an insufficiency report, not fabricated scores. Configured minimum counts are execution gates, not universal scientific sufficiency thresholds.

Nine default candidates compare empirical and zero-mass Normal residuals across pooled, position, projection-band and joint conditioning, plus joint empirical hybrid partial pooling. Actual zero mass is separate; nonzero residuals translate to the target projection without flooring signed support. Normal research forecasts use deterministic quantile quadrature, not a change to production draws. Empirical/Normal sparse groups use pooled-only fallback. Hybrid empty groups use pooled-only; nonempty sparse groups retain shrunk local evidence and increment `sparse_partially_pooled_rows`, not `fallback_rows`. Audit coverage bands are not automatically model strata, and research pooling is not a missing-forecast production substitute. Mathematical outcome treatment remains in M2 and its current owner.

### Diagnostics and recommendation boundaries

The [metric contract](RESEARCH.md#metrics-and-promotion) requires more than an average error or one winning score:

| Question | Implemented report / required interpretation |
|---|---|
| Distributional accuracy | Mean CRPS orders candidates; kernel negative log score uses an explicit bandwidth floor. Ties use negative log score then stable candidate ID. |
| Bias and scale | Forecast-mean error and RMSE; relative-error count/mean only for nonzero projections. No ratio at zero. |
| Zero and signed support | Zero-outcome Brier score; explicit zeros, negative projections and negative outcomes retained. Missing imputation cannot manufacture pairs. |
| Calibration and sharpness | 50/80/90% interval coverage and mean width, lower-10/upper-90% exceedance, ten-bin deterministic mid-PIT. Narrow intervals alone are not good calibration. |
| Adequacy and sensitivity | Training/evaluation counts by evidence, season/week, position and configured band; pooled fallback versus sparse-partially-pooled counts. Dataset coverage also discloses missing/imputed/explicit-zero counts. |

Inspect support, tails, zeros, bias, sparse-group/shrinkage sensitivity, representative scoring contexts and sampling cost alongside baseline/alternative comparisons. Retain reproducible dataset/report identities and configuration. The current report does not supply authentic lead-time vintages, a sealed-test protocol, player-specific/correlation/injury evidence or universal thresholds. Apparent source metadata and additional Monte Carlo paths cannot repair these gaps.

### Independent component-specific promotion

Authenticated-only sample sufficiency can produce a **research recommendation pending independent review**. Exploratory mode can name `exploratory_best_candidate_id`; neither mode installs a production model. Even an authenticated recommendation does not satisfy all promotion obligations automatically.

Keep the [component-specific gate](RESEARCH.md#component-specific-promotion): uncertainty distributions need calibration/zero/support/tail evidence; V(R) needs sampled decision-quality evidence; waiver/mechanics policies need source-rule fidelity; pruning needs coverage/decision evidence; numerical optimization needs exact reference equivalence plus runtime/memory evidence. Compare against the incumbent approved version, accounting for selection bias and runtime regression. No single score promotes all components. Experimental selectors are supported only where implemented; the latest-approved-official-combination design obligation does not mean all selectors or official calibrated families exist today.

[WR-019](BACKLOG.md#wr-019-scientific-promotion-and-deferred-research) retains independent review, honest temporal evidence and scientific promotion duties. Other live-week, inference, mechanics and release obligations remain with BACKLOG/current domain owners; this V3 chapter does not absorb V1/V2 correctness/reproducibility, V4 decision validation or V5 release gates. It does not approve new correlations, injury models, horizon factors or third-party means.

### Verification and retained interfaces

[Dataset/provenance tests](../tests/test_historical_dataset.py) exercise exact-row binding, forged trust and modified values; [research tests](../tests/test_outcome_distribution_research.py) exercise temporal exclusion, insufficiency, perfect-forecast CRPS, signed/zero support and sparse thresholds. [Historical parser tests](../tests/test_historical_projection_audit.py) and [workflow tests](../tests/test_historical_research_workflow.py) check source parsing/materialization, not live semantics. [Focused pilot tests](../tests/test_data_documentation.py) bind the documented schemas/examples and inventory boundaries to those interfaces. None is empirical calibration.

RESEARCH retains [reproduction and private artifact instructions](RESEARCH.md#reproduction-and-artifacts), exact dated results and all M0 anchors. Networked materialization requires separate authorization; no command is run by this chapter. The [P7a mapping](DATA.md#p7a-source-section-mapping-and-retained-ownership) records source sections and deferred owners. No M0, production model or release transition follows from documentation transfer.
