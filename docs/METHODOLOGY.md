# War Room methodology

**P2 pilot: M1 and M2 are developed below; M3 and M6 provide conceptual bridges.** The other chapters explicitly identify later scope. This is a quantitative reader's guide pending transfer review, not a new authority or a claim of empirical validation. Current [outcome](PLAYER_OUTCOME_MODEL.md), [data](DATA.md), [research](RESEARCH.md), [season](SEASON_SIMULATOR.md), [transaction](TRANSACTIONS.md) and [Monte Carlo](MONTE_CARLO.md) contracts remain binding under [authority and precedence](../AGENTS.md#authority-and-precedence). No existing owner is retired or superseded. The [accepted architecture plan](development/model-documentation-architecture.md#reviewable-implementation-packages) defines subsequent packages; [BACKLOG](BACKLOG.md) retains open obligations. For operating procedures, use the [user guide pilot](USER_GUIDE.md).

## Contents

- [M1: Analytical framework and objective](#analytical-framework-and-objective)
  - [Experiment, inputs and estimand](#experiment-inputs-and-estimand)
  - [Notation and interpretation](#notation-and-interpretation)
- [M2: Player outcome generation and assumptions](#player-outcome-generation-and-assumptions)
  - [Projection classes and complete outcome universe](#projection-classes-and-complete-outcome-universe)
  - [Provisional Normal outcomes](#provisional-normal-outcomes)
  - [Internal empirical residual outcomes](#internal-empirical-residual-outcomes)
  - [Assumptions and unapproved alternatives](#assumptions-and-unapproved-alternatives)
  - [Validation evidence and open gates](#validation-evidence-and-open-gates)
- [M3: Season simulation and lineup optimization](#season-simulation-and-lineup-optimization)
- [M4: Current-week and partial-week treatment](#current-week-and-partial-week-treatment)
- [M5: Roster evolution and transaction rules](#roster-evolution-and-transaction-rules)
- [M6: Monte Carlo simulation and estimators](#monte-carlo-simulation-and-estimators)
- [M7: Statistical inference, precision and uncertainty](#statistical-inference-precision-and-uncertainty)
- [M8: Manual scenarios and action-search methodology](#manual-scenarios-and-action-search-methodology)
- [M9: Decision evaluation, ranking and limitations](#decision-evaluation-ranking-and-limitations)

## Analytical framework and objective

### Experiment, inputs and estimand

War Room estimates the consequences of a league's remaining season, conditional on a validated ESPN snapshot and explicit modeling policies. Its initial decision objective is **expected championship probability** for the requesting manager. It evaluates effects for every manager: moving a player changes opponents, playoff qualification and shared acquisition competition as well as the requesting roster. Other reported outcomes help explain the result; they do not silently replace that objective. [README's approved objective](../README.md#current-capabilities) and the [required output obligations](BACKLOG.md#wr-021-output-provenance-and-numerical-lifecycle) distinguish the delivered summary subset from future reporting requirements.

The snapshot supplies observed identities, ownership, rosters, standings, eligibility, league settings, matchup periods and currently returned ESPN player-specific future weekly projections. Source and manual-rule provenance constrain what may be simulated. Publication integrity does not establish that every league capability is understood or that a returned projection was genuinely available before a historical game. [DATA](DATA.md#raw-to-canonical-map) owns those distinctions and [RESEARCH](RESEARCH.md#external-trust-and-exact-row-binding) owns temporal authentication. Unknown rules, inconsistent identities and unsafe simulation boundaries fail at the affected validation/permission boundary rather than receiving guessed replacements.

ESPN is the sole initial projection source. War Room initially converts those forecasts into uncertain league outcomes rather than attempting to outperform ESPN's player means. No third-party fallback, arbitrary horizon inflation/discount or unapproved injury adjustment is permitted. The empirical transformation below can have a mean different from its target projection because of its fitted residual/zero atoms; that implemented provisional policy is distinct from authorizing a new general bias-correction method.

Let $S$ be the immutable observed snapshot, $\pi$ the explicit league/lineup/transaction policies and $\theta$ the outcome-model configuration, including fitted evidence where applicable. Let $a$ identify a legal hypothetical action or completed roster state; $a=0$ denotes the baseline. This notation describes the experiment, not a new API. A path supplies player-week outcomes $X^{(i)}$. One shared deterministic engine maps them to a season:

$$
Y^{(i)}_a = G(S,\pi,a,X^{(i)}).
$$

For team $t$, the principal estimand is

$$
p_t(a\mid S,\pi,\theta)
= \mathbb{E}_{\theta}\!\left[\mathbf{1}\{t\text{ is champion in }G(S,\pi,a,X)\}\right].
$$

The expectation is over modeled player outcomes, not uncertainty about whether a manager accepts an offer. A hypothetical comparison conditions on its specified legal completion. War Room neither submits ESPN transactions nor predicts acceptance or waiver-claim success. The engine may model competing essential acquisitions under explicit policies; those policies are not empirical estimates of human behavior. Unsupported current-week actions do not become legal through this notation.

The baseline has no analyst-proposed change but still uses the configured future roster-evolution policy. A scenario modifies a legal state and retains the same underlying player-week shocks for comparison. All teams' effects remain in the experiment; the requesting manager determines the ranking objective, not which opponents exist. Championship probability differs from qualification probability, final placement or mean points: maximizing one does not mathematically maximize the others.

### Notation and interpretation

| Symbol / term | Meaning |
|---|---|
| $j,w$ | Canonical player and scoring week in one season; a matchup period may contain multiple scoring weeks. |
| $r_{jw},\mu_{jw}$ | Raw ESPN projection and effective canonical projection. Missing raw evidence remains null even when policy supplies effective zero. |
| $A_{jw},X^{(i)}_{jw}$ | Observed actual score, when independently available, versus a simulated realization on path $i$. A projection is neither. |
| Path $i$ | One complete set of player-week realizations and its deterministic season progression. |
| Scenario $a$ | A baseline or hypothetical experiment evaluated over paths; an action sequence and its completed roster state have distinct structural meanings. |
| $p,\widehat p$ | Model probability versus finite-path estimate. Fractions range from 0 to 1; a difference of 0.02 is two probability points. |

Equations describe mathematical meaning; ordered floating-point expressions and numerical identities remain in their current owners. Examples below are synthetic arithmetic, not observed ESPN results, fitted defaults or calibration claims. Fully developed components identify provenance, definitions, parameters, assumptions, invalid inputs, implementation status and evidence gates; later chapters will follow this convention without duplicating implementation-byte recipes.

Sampling uncertainty measures finite-path error under $(S,\pi,\theta)$. Model uncertainty concerns the adequacy of that experiment, projection timing, parameters and source evidence. More paths can reduce the former without correcting the latter. Passing software tests, a historical benchmark or source-field availability cannot establish real-world predictive accuracy.

## Player outcome generation and assumptions

M2 explains the two currently supported provisional generators. [PLAYER_OUTCOME_MODEL](PLAYER_OUTCOME_MODEL.md#current-execution-boundary) remains the policy authority; [DATA's projection contract](DATA.md#projection-contract) owns classification rather than this exposition redefining it. The public application accepts the provisional Normal family. The empirical family is an internal engine input, not an officially promoted replacement or public model selector.

### Projection classes and complete outcome universe

The raw weekly projection is `appliedTotal` from exactly matching season/scoring-period, source-1, split-1 ESPN stats. Source-0 weekly actuals are separate evidence. Period-zero totals/averages cannot stand in for a week. Missing matching records differ from matching numeric zero; malformed, duplicate or nonfinite matching values fail validation. Current player identity/ownership is reconciled independently of future projection retrieval. See [raw fields and transformations](DATA.md#identity-rosters-and-player-weeks).

| Canonical class | Raw / effective evidence | Normal realization | Empirical realization | Ordinary projected lineup |
|---|---|---|---|---|
| `MISSING` | Raw null; effective 0 from `missing_projection_policy` | Exactly `0.0`, bypass dispersion and sampling | Exactly `0.0`, bypass sampling | Unavailable |
| `EXPLICIT_ZERO` | Raw 0; effective 0 from ESPN | $\mu=0,\sigma=\text{base_stddev}$; nonmissing draw path | Exactly `0.0`, bypass sampling | Unavailable |
| Positive `PRESENT` | Raw/effective positive ESPN value | Normal equation below | Empirical target atoms below | Available subject to legality |
| Finite negative `PRESENT` | Raw/effective signed ESPN value | Same Normal equation | Same empirical target policy | Unavailable |

Ordinary projection-based selection requires **effective_projection > 0**, before seeing draws. That decision boundary is not a nonnegative floor on realized scores. A positive realization cannot make an unavailable player eligible. Observed partial-week starters follow their separate permission/composition contract.

These are four distinct layers: raw source evidence, canonical classification/effective value, model policy, and sampled realization. Canonical missing-zero imputation does not manufacture an ESPN forecast or an observed actual zero. The deterministic missing outcome is an approved conservative policy, not proof of nonparticipation. Explicit ESPN zero likewise proves neither inability to score nor absence. Injury labels, NFL association and actual-stat presence do not authorize an extra participation inference. The [dated missingness evidence](PLAYER_OUTCOME_MODEL.md#missing-zero-and-present-projections) records counterexamples and its bounded scope.

Each generator emits one finite score for **every canonical in-horizon player-week**, including unrostered, bench and reserve players. It sorts by player/season/week, rejects duplicate keys and checks coverage of that canonical universe. Canonical validation supplies the roster/player/week completeness contract; this does not prove ESPN's independently unknown population total. A lawful later acquisition or different lineup uses the already path-defined score, without resampling. No independent injury/availability draw, replacement forecast or conditional injury-return process is added. Caller-supplied deterministic realizations and fixed observed actuals are different input contracts, not generated forecasts.

### Provisional Normal outcomes

For each **nonmissing** player-week, the current model takes

$$
\mu = \operatorname{float}(\text{effective_projection}),\qquad
\sigma = \text{base_stddev} + \text{projection_scale}\times|\mu|,
$$

$$
Z\sim\mathcal N(0,1),\qquad X=\mu+\sigma Z.
$$

Here $\mu$ is the ESPN-based mean in fantasy points, $\sigma$ the standard deviation in points, $Z$ a standardized Normal shock and $X$ the realized fantasy score supplied to the season engine. For $\sigma>0$, this specifies $X\sim\mathcal N(\mu,\sigma^2)$. When $\sigma=0$, the formula is deterministic at $\mu$. MISSING bypasses this formula entirely, even with positive dispersion parameters.

| Parameter | Current admissibility / meaning |
|---|---|
| `base_stddev` | Mandatory finite nonnegative int/float, excluding Boolean; absolute dispersion in points. |
| `projection_scale` | Mandatory finite nonnegative int/float, excluding Boolean; dispersion per absolute projected point. At least one dispersion parameter must be positive. |
| `version` | Nonempty string, default `provisional-independent-normal-v1`; identifies the version used for established draws. |

There is no implicit dispersion default or empirically fitted setting in this class. UI/profile choices are explicit experiment inputs, not universal league constants. With `base_stddev=0`, an explicit-zero projection has zero dispersion even though it remains on the nonmissing draw path. Positive and negative nonzero projections then have positive dispersion because `projection_scale` must be positive. Generated nonfinite values fail rather than being clipped or replaced.

Synthetic arithmetic, conditioning on the displayed standardized shock (not asserting a particular seed produces it):

| mu | base_stddev | projection_scale | Z | sigma | X |
|---|---|---|---|---|---|
| 8 | 2 | 0.25 | -1 | 4 | 4 |
| -2 | 2 | 0.25 | -1 | 2.5 | -4.5 |
| 0 | 0 | 0.25 | 1 | 0 | 0 |

Scores remain signed and unrounded. Normal support includes negative and arbitrarily large values; there is no artificial nonnegative clipping, position multiplier, discrete scoring-granularity adjustment or separate zero atom for nondegenerate draws. Symmetry, common linear dispersion and continuous tails are illustrative assumptions, not authenticated fantasy-score calibration. Positions whose actual scoring mechanisms prohibit negatives need empirical support checks; globally clipping legitimate signed outcomes is not an approved correction.

The implemented shocks are reproducible, player-week/path-indexed deterministic pseudorandom values approximating the stated Normal experiment. Conditional on the chosen snapshot/model, the policy assumes independence across players and weeks: no shared game shocks, stacks, across-week persistence or player-specific volatility. Reusing a player's shock across hypothetical scenarios is variance reduction, not within-path player correlation.

The current public model identity appends `:missing-projection-zero-v1` to `version`; public parameters contain dispersion, `conditional_independence=True` and `missing_projection_outcome=deterministic-zero-v1`. Established nonmissing draws retain the original version and historical three draw parameters. The explicit public policy discriminator prevents collision with historical custom version strings. Earlier Normal checkpoints are incompatible even for nonmissing inputs; historical artifacts are not rewritten. Exact encodings, hashing, Box–Muller operation order, private/public identity and golden constants remain solely in [Normal draw bytes](PLAYER_OUTCOME_MODEL.md#normal-distribution-and-draw-bytes), [identity compatibility](PLAYER_OUTCOME_MODEL.md#identity-and-compatibility) and [Monte Carlo identity](MONTE_CARLO.md#configuration-run-and-path-identity). P2 changes none of them.

### Internal empirical residual outcomes

The internal fitted sampler uses historical raw projection/actual pairs, not imputed forecasts. The [current empirical owner](PLAYER_OUTCOME_MODEL.md#empirical-engine-model) and [research evaluation](RESEARCH.md#temporal-evaluation-and-candidates) distinguish this family from the broader research candidate universe.

Fitting revalidates dataset/report identity and linkage, requires the explicit `exploratory_best_candidate_id=projection_empirical_residual` with exactly the empirical/projection-conditioned candidate, and a nonempty selection reference. An arbitrary recommendation or differently labeled family cannot silently substitute. Only rows strictly before the configured evaluation season/week boundary qualify, with raw projection and actual present and no policy imputation. Authenticated-only policy requires row-bound authenticated pregame evidence; exploratory policy can also include unverified historical pairs. Minimum training rows must be met. This constructor's selection field is an implementation restriction, not a production-promotion rule.

For eligible training row $\ell$, let $r_\ell$ be its raw projection and $A_\ell$ its historical actual. Store the residual and exact-zero flag

$$
e_\ell=A_\ell-r_\ell,\qquad q_\ell=\mathbf1\{A_\ell=0\}.
$$

Group rows by configured projection bins, with lower-inclusive/upper-exclusive edges, unbounded outer bins and no position conditioning in this engine family. For target finite-present projection $\mu$, choose the matching group's atoms if its count meets `minimum_group_size`; otherwise use all pooled training atoms. Equality meets the threshold. Sparse and absent groups use this explicit **pooled_empirical** policy, not the research hybrid's nonempty-group shrinkage and not a missing-projection substitute.

Transform each selected atom at the target projection:

$$
b_\ell(\mu)=
\begin{cases}
0,&q_\ell=1,\\
\mu+e_\ell,&q_\ell=0.
\end{cases}
$$

Sort the $n$ transformed outcomes, retaining multiplicity. For the path-defined pseudorandom quantile $u$, use zero-based index

$$
k=\min(\lfloor un\rfloor,n-1),\qquad X=b_{(k)}(\mu).
$$

There is no interpolation. Historical actual-zero atoms remain exactly zero at every target projection; nonzero residual atoms translate by the target projection and may themselves produce zero or negative outcomes. Multiplicity determines empirical mass. Signed support survives and the mean need not equal $\mu$. Missing and explicit-zero target classes bypass this sampling and return deterministic zero.

For a hand-checkable synthetic example, training pairs $(r,A)=(2,0),(3,5),(10,12),(20,15)$, bin edges 5 and 15, and minimum group size 2 give target $\mu=3$ sorted atoms $[0,5]$. Target $\mu=20$ has only one local training row and therefore uses pooled sorted atoms $[0,15,22,22]$. The second 22 retains its mass. These numbers demonstrate the implementation, not recommended bins, fitted evidence or a live forecast.

Bin edges are explicit finite sorted unique values; the group minimum is a positive integer. Fitted support must be finite, contain every declared training row, and partition exactly into unique sorted groups. Nonempty version/evidence/selection identities, valid dataset/report/training/fitted-support hashes and a valid evaluation boundary are required. No generic bin, sample minimum or pooling strength is a universal default. The fitted model's default version is `provisional-projection-empirical-residual-v1`; dataset/report identities, evidence status, boundary, bin edges, group threshold, pooling rule, row count, fitted atoms and selection reference remain part of public parameters/provenance. `conditional_bias_correction=False` does not mean empirical mean residuals vanish. Complete fitted identity enters quantile draws; technical representation stays with the current owner.

Finite historical support cannot invent unseen tails. Projection-only bins may mix positions and regimes; pooling preserves computability without proving calibration. Returned historical forecasts can be retrospective, and missingness/selection/scoring revisions can distort fitted residuals. Existing historical training remains **unverified_exploratory**, not authenticated pregame error evidence. A fitted internal model or exploratory CRPS winner has not replaced the public provisional Normal baseline.

### Assumptions and unapproved alternatives

| Category | Interpretation and current boundary |
|---|---|
| Current model assumptions | ESPN-only projection basis; deterministic missing-zero policy; ordinary positive-projection availability; explicit dispersion or fitted atoms; conditionally independent player-week draws; no extra injury/participation process or horizon adjustment. Snapshot-derived rules and named approved roster policies constrain the experiment. |
| Known limitations | Provisional Normal symmetry/continuous tails/common dispersion; finite empirical support and projection-only grouping; sparse pooled data; unknown historical pregame timing and universe completeness; no calibrated joint player/game/week dependence. Implementation correctness is not predictive calibration. |
| Approved outstanding requirements | Authentic temporal training/validation/sealed-test evidence, representative position/projection/scoring support, zero/downside/tail/bias calibration, pooling sensitivity, runtime and championship-decision evaluation. Component-specific independent acceptance is still required. |
| Proposed alternatives | Empirical/parametric/hybrid research competition, shrunk conditional bias adjustments, genuine lead-time models, player-specific effects or joint dependence. Each requires its documented evidence, scope and independent approval; proposals are not current behavior or blanket authorization. |

The research framework already implements additional candidates and hybrid partial pooling **for evaluation**. That does not install those policies into this empirical generator. Correlation/persistence and conditional live remaining-performance distributions are not implemented here. A future bias correction must preserve raw ESPN lineup/waiver/completion/V(R) inputs, shrink toward no correction according to evidence, and apply exactly once in sampled outcomes under a separately approved version. Horizon variance needs genuinely older forecasts, not later pregame restatements; a variance curve cannot substitute for availability risk. [WR-019](BACKLOG.md#wr-019-scientific-promotion-and-deferred-research) preserves the detailed requirements and proposal boundaries.

### Validation evidence and open gates

Source inspection and synthetic tests establish **Verified by tests** behavior, not new **Verified live** calibration. [player_outcomes.py](../src/fantasy_football/player_outcomes.py) implements both generators. [Normal/universe tests](../tests/test_player_outcomes.py), [empirical fit tests](../tests/test_m33_player_outcomes.py) and [missing-zero/identity regressions](../tests/test_missing_projection_zero.py) cover reproducibility, signed/zero/missing values, unchanged source records, sparse support, wrong evidence and historical nonmissing-draw equivalence. [The frozen historical oracle](../tests/legacy_normal_reference.py) and [partial/golden tests](../tests/test_partial_monte_carlo.py) retain independent numerical evidence. No reference artifact, parameter or algorithm is changed by this pilot. Its inspected implementation baseline is accepted P1 `9bf43e18740f81aa646b20fbe7fabc83d563c754`; provisional model identities above remain unchanged. Actual verification commands/results belong in the P2 PR.

[RESEARCH's promotion requirements](RESEARCH.md#metrics-and-promotion) require chronological evaluation without tuning leakage, calibration/sharpness, zero/support/tail/bias diagnostics, sparse sensitivity, baseline comparisons, computational cost and decision relevance. Current research has one training/evaluation split, not a sealed final-test implementation; historical materialization had zero authenticated pregame pairs. Lowest exploratory CRPS, sufficient sample counts and synthetic correctness cannot close those gates. [Component-specific promotion](RESEARCH.md#component-specific-promotion) requires reproducible evidence and independent acceptance for the component's actual job; a sampling improvement does not validate roster value, waiver policy or mechanics. Prospective data collection is separately authorized work, not required or performed by P2.

## Season simulation and lineup optimization

**M3 conceptual bridge only; P3 retains the detailed transfer.** One realization vector enters the existing deterministic season coordinator. For each supported week it evolves legal rosters under explicit policies, selects and freezes a legal lineup using projected values, then reads realized starter values to score games. Standings update from regular results; modeled standings determine postseason seeds and configured bracket progression accumulates applicable scoring-week contributions. A matchup period can span weeks: it is not synonymous with one week. Completion requires supported reconciled final outcomes, not just reaching the calendar's end.

```mermaid
flowchart LR
    S[Validated snapshot and explicit policies] --> X[One player-week realization vector]
    X --> G[Shared deterministic season coordinator]
    G --> Y[Scores, standings and postseason outcome]
    Y --> N[Repeat for each path]
    N --> P[League-wide model probability estimates]
```

This schematic omits mechanics, not validation. Different Normal, empirical or explicit deterministic inputs must use **one season engine**, not alternate league-rule implementations. Ordinary lineup optimization does not see realized outcomes; no hindsight lineup can improve a path. Canonical facts remain source truth and hypothetical evolving ownership is separate state. [SEASON_SIMULATOR](SEASON_SIMULATOR.md#weekly-progression) owns lineup objective/ties, signed scoring, standings, playoff aggregation and incomplete capability handling; [its synthetic coordinator tests](../tests/test_season_simulator.py) provide the runnable single-engine smoke path. This pilot does not duplicate those algorithms or resolve WR-023/024 or multiweek regular-season limitations.

## Current-week and partial-week treatment

**M4 scope only, for P4.** Full-week forecasts cannot stand in for in-game remaining points. [PARTIAL_WEEK](PARTIAL_WEEK.md#current-capability-map) owns immutable observed assignments, independent lock/cutoff/full-period authority and fixed/remaining/carry composition. Its deterministic companion uses the same season engine; its narrower Monte Carlo subset accepts fully unstarted relevant current-week players with approved full-game projections, matching legal lineups/policies and no ownership-changing first-week acquisition for V1 equivalence. Completed/in-progress/missing/ambiguous MC states fail closed. No live translator, conditional remainder model, current-week recommendation or public partial execution is authorized by this chapter.

## Roster evolution and transaction rules

**M5 scope only, for P3.** [TRANSACTIONS](TRANSACTIONS.md) owns legal ownership, holds, IR conventions, essential-only acquisition competition and resulting-roster value V(R). The baseline already includes configured future competition. V(R) is a roster-policy proxy, not championship probability. Detailed legal enumeration, horizon weighting, shared replacement access and incomplete valuation remain in that owner; this pilot neither changes them nor clears the [mechanics review obligations](BACKLOG.md#mechanics-review-obligations).

## Monte Carlo simulation and estimators

**M6 conceptual bridge only; full estimator/execution treatment remains for P5.** Exact integration over uncertain player outcomes and conditional season progression is generally impractical. Monte Carlo repeats the deterministic mapping at reproducible path indices with the same snapshot, model and policies. Each path starts fresh state; it does not continue the previous path's standings or holdings. Parallelism and batching divide this same experiment, not its mathematics.

For $N$ fully complete requested paths, let $C_{it}(a)$ indicate team $t$'s championship on path $i$. The basic estimate is

$$
\widehat p_t(a)=\frac{1}{N}\sum_{i=1}^{N} C_{it}(a).
$$

Qualification and exact placements use their own indicators. [MONTE_CARLO](MONTE_CARLO.md#aggregation-and-probability-estimators) owns all denominators and per-path reconciliation. If any requested path is capability-incomplete, unconditional probability estimates are suppressed; do not divide by only successful paths. Invalid structural inputs fail rather than becoming replacement paths. A complete-batch frequency zero differs from an unavailable estimate.

For matched baseline/hypothetical comparisons, the same player's model/seed/path/week draw stays fixed even if ownership changes. Reusing draws isolates roster consequences without a second player sample. A legal transfer can change $G$ and the champion while leaving $X^{(i)}$ identical. The difference $\widehat p_t(a)-\widehat p_t(0)$ is an absolute probability difference; its paired uncertainty is not obtained by subtracting standalone interval endpoints. [Paired inference](MONTE_CARLO.md#paired-scenario-inference) remains authoritative. Seed alone is not sufficient replay provenance: exact evidence, configuration, identity and path ranges matter.

**Reader walkthrough:** begin with an ESPN source-1 weekly value 8, classified PRESENT and preserved as effective 8. For the illustrative Normal parameters and shock in M2's first row, the realization is 4. The engine selects that player's lineup slot using projections/legality before reading 4, then scores the frozen starters and progresses the same league rules through the horizon. Repeat complete seasons at different path indices. If a team wins 12 of 100 fully reconciled synthetic paths, its estimate is 0.12; this is illustrative frequency arithmetic, not a calibrated forecast or claim of adequate precision. A hypothetical evaluates legal roster changes against those same player-week draws, conditional on execution. Source authentication, calibration, supported mechanics and inference gates remain independent of that arithmetic.

## Statistical inference, precision and uncertainty

**M7 scope only, for P5.** [MONTE_CARLO](MONTE_CARLO.md#precision-and-stopping) owns all-team estimands, intervals, stopping and sampling-versus-model uncertainty. Governing 95% family confidence/0.5 probability-point target obligations remain in that owner and BACKLOG; neither a preset nor completion guarantees convergence. [WR-025](BACKLOG.md) retains unresolved progressive repeated-look coverage. Mathematical fractions/points do not change the [legacy public unit boundary](APPLICATION_SERVICE.md#public-dtos-units-and-validation). Detailed inference and API migration are outside P2.

## Manual scenarios and action-search methodology

**M8 scope only, for P6.** [MANUAL_SCENARIOS](MANUAL_SCENARIOS.md) owns explicit hypothetical completion; [UNIFIED_ACTION_SEARCH](UNIFIED_ACTION_SEARCH.md) owns finite candidate/path enumeration and shared completed-state evaluation. Actions, sequences, states and numerical evaluations are distinct. Full enumeration/coverage and incomplete-result disclosure remain binding; a visible top row is not proof of exhaustive optimality. No new search method is specified here.

## Decision evaluation, ranking and limitations

**M9 scope only, for P6.** The requesting manager's championship objective coexists with all-team effects, legal execution assumptions and incomplete evidence. [Search ranking](UNIFIED_ACTION_SEARCH.md) and [research promotion](RESEARCH.md#component-specific-promotion) retain current ranking/decision-evidence boundaries. Model, data, sampling and selection uncertainty must not be conflated; no automatic acceptance probability or proven best real-world action follows from a model estimate. [BACKLOG](BACKLOG.md) retains unimplemented requirements and research proposals; neither this pilot nor its passing tests declares model promotion, migration completion or V1 release.
