# War Room methodology

**P4 pilot: M1 through M5 are developed below; M6 provides a conceptual bridge.** The other chapters explicitly identify later scope. This is a quantitative reader's guide pending transfer review, not a new authority or a claim of empirical validation. Current [outcome](PLAYER_OUTCOME_MODEL.md), [data](DATA.md), [research](RESEARCH.md), [season](SEASON_SIMULATOR.md), [transaction](TRANSACTIONS.md) and [Monte Carlo](MONTE_CARLO.md) contracts remain binding under [authority and precedence](../AGENTS.md#authority-and-precedence). No existing owner is retired or superseded. The [accepted architecture plan](development/model-documentation-architecture.md#reviewable-implementation-packages) defines subsequent packages; [BACKLOG](BACKLOG.md) retains open obligations. For operating procedures, use the [user guide pilot](USER_GUIDE.md).

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
  - [One path and weekly progression](#one-path-and-weekly-progression)
  - [Exact projected lineup objective and ties](#exact-projected-lineup-objective-and-ties)
  - [Frozen scoring and standings](#frozen-scoring-and-standings)
  - [Postseason graphs, periods and placements](#postseason-graphs-periods-and-placements)
  - [Complete season walkthrough](#complete-season-walkthrough)
- [M4: Current-week and partial-week treatment](#current-week-and-partial-week-treatment)
  - [Observed assignments, proposed assignments and locks](#observed-assignments-proposed-assignments-and-locks)
  - [Fixed actuals and supplied remaining realizations](#fixed-actuals-and-supplied-remaining-realizations)
  - [Standings cutoff, period carry and season integration](#standings-cutoff-period-carry-and-season-integration)
  - [Supported execution states and pregame equivalence](#supported-execution-states-and-pregame-equivalence)
- [M5: Roster evolution and transaction rules](#roster-evolution-and-transaction-rules)
  - [Legal state and explicit model conventions](#legal-state-and-explicit-model-conventions)
  - [Operational essential acquisitions](#operational-essential-acquisitions)
  - [Resulting-roster value and replacement access](#resulting-roster-value-and-replacement-access)
  - [Independent correctness and remaining obligations](#independent-correctness-and-remaining-obligations)
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

M2 supplies outcomes; M3 determines their league consequences through **one season engine**. Normal, empirical and caller-supplied deterministic scores all enter the same coordinator. It neither retrieves ESPN nor generates random scores. [SEASON_SIMULATOR](SEASON_SIMULATOR.md#inputs-and-boundaries) remains the current authority; this chapter develops its mathematical meaning, while M5 explains the shared roster-evolution policy.

```mermaid
flowchart LR
    S[Validated snapshot and explicit policies] --> X[One player-week realization vector]
    X --> G[Shared deterministic season coordinator]
    G --> Y[Scores, standings and postseason outcome]
    Y --> N[Repeat for each path]
    N --> P[League-wide model probability estimates]
```

### One path and weekly progression

The ordinary deterministic input is a validated published schema-v3-or-later snapshot, an immutable identified score scenario, explicit IR/acquisition policies, and any separately validated initial evolving state or consolation configuration. Score records must be finite, unique by player/season/week and agree with canonical identity and horizon. Signed IDs and negative/zero scores are valid. Every applicable frozen starter needs a score; unrelated players need not be scored by a caller-supplied scenario, unlike M2's complete generated universe. Projections never replace missing realizations. Contradictory overrides, unpublished identity and malformed calendars fail preflight.

Let $E_w$ denote modeled ownership, availability, counters and priority at week $w$, $H_w$ cumulative regular standings, and $B_w$ postseason state. These evolve coherently along one path; the source snapshot stays immutable. Canonical periods cover each week of the inclusive horizon once, with no regular phase after postseason. A scoring week is one contribution interval; a matchup period can contain several such weeks. Calendar phase does not by itself establish bracket participation.

Ordinary execution requires a verified fully unplayed boundary when live metadata exists, with independently supported full current-period membership. A later unplayed week or override cannot omit earlier unreconciled contributions. Earlier supported schema reads without live metadata retain their compatibility path, not a new live-readiness guarantee. M4's separate companion/cutoff/history route remains for P4.

The [weekly coordinator sequence](SEASON_SIMULATOR.md#weekly-progression) is:

1. Initialize standings from canonical cumulative records and evolving state from canonical ownership or a validated supplied state. For every week after the first, advance the acquisition cycle. Holds persist; matchup acquisition counts reset only across a canonical period boundary, and season counts persist.
2. Apply configured waiver resets: `True` requires a unique inverse modeled-standings order; `False` preserves dynamic priority. Unknown reset semantics fail preflight. An unresolved ranking returns an incomplete path before a guessed queue reset. Each window retains its opening queue separately from subsequent successful-claim movement.
3. At the postseason boundary, require unique modeled final regular standings and initialize bracket state. Determine transaction eligibility independently of scoring participation; a current bye can still leave future obligations.
4. Execute M5's essential acquisition window on shared $E_w$, retaining new ownership, holds, counters and diagnostics. A material unresolved authorization with a remaining starter vacancy yields an incomplete path. Under unresolved postseason participation, an acquisition-producing probe stops before retaining its mutation. This is not a deliberate choice to make no acquisition; WR-024's mixed-valuation gap below remains separate.
5. For teams actually scoring this week, optimize legal projected lineups on the resulting rosters and **freeze assignments before reading realized scores**. Bye/inactive teams require no scored lineup; their ownership and replacement demand remain in the league state.
6. Score frozen starters. Update regular matchup results/$H_w$, or add postseason weekly totals to $B_w$. Advance a postseason game only after every configured scoring-week contribution is present.
7. Retain immutable weekly transitions and validated evolving state for the next week. Return initial/final standings, frozen scores, transactions, postseason, team outcomes and explicit unresolved capabilities.

Reordered input collections cannot change the logical outcome. Timing diagnostics are normalized out of logical season equality. A complete result requires a unique supported final placement for every configured team and exactly one champion; reaching the last week or deciding the title alone is insufficient. Invalid structural/domain inputs raise contextual errors; supported but unresolved capabilities can return an explicitly incomplete path. Disabled consolation may leave useful championship outcomes without a complete league ranking. No missing rule receives a convenient default.

### Exact projected lineup objective and ties

For team $t$, week $w$ and current roster state, let $P_{tw}$ contain owned nonreserve players with canonical effective projection $\mu_{jw}>0$. Starter capacities expand into an ordered set $K$ of distinct slots $(\text{lineup_slot_id},\text{position_index})$. Let $e_{jk}=1$ mean player $j$ is eligible for slot $k$ in the lineup-slot namespace. Default-position IDs are a different namespace. Bench/ordinary occupants can start; reserve/IR occupants cannot activate implicitly.

Choose binary assignments $x_{jk}$ satisfying

$$
\sum_{k\in K}x_{jk}\le1,\qquad
\sum_{j\in P_{tw}}x_{jk}\le1,\qquad x_{jk}\le e_{jk}.
$$

The primary objective is

$$
L_{tw}=\max_x\sum_{j\in P_{tw}}\sum_{k\in K}\mu_{jw}x_{jk}.
$$

Among exact primary ties, maximize filled-slot count; then lexicographically minimize the assignment vector over ordered slots, encoding an assigned player as $(0,\text{player_id})$ and a vacancy as $(1,0)$. Thus assignments precede vacancies and lower stable signed player IDs win at the earliest slot identity. These are deterministic tie rules, not extra points or tolerances. [The lineup owner](SEASON_SIMULATOR.md#exact-lineup-selection) specifies the current finite dynamic program and invalid-input contract.

**Synthetic FLEX-overlap example:** two starter units A and FLEX; player 1 is eligible for both at 10 projected points, player 2 only A at 9, and player 3 only FLEX at 1. Assigning the largest player to A first gives 11. Global assignment gives A→2 and FLEX→1, totaling **19**. Slot labels/IDs in this example are illustrative, not universal RB/WR/FLEX rules. Actual capacities and edges always come from the snapshot.

The all-vacant assignment is feasible. If no complete assignment exists, return the best partial legal lineup with explicit vacancies, not fake zero-valued players or forced ineligible starts. Reasons distinguish no owned eligible player, reserve occupancy, no positive projection and eligible players needed elsewhere. Missing/zero/negative projections remain distinct but unavailable to ordinary projected selection; negative realized scores of a chosen positive-projection player remain valid. Invalid ownership, eligibility, duplicate usage, capacities, identities or weeks fail rather than being repaired. Canonical ownership remains source truth; a coherent validated hypothetical roster supplies the path's changed ownership without rewriting source acquisition labels.

**WR-023 remains unresolved.** The approved objective requires exact finite-score ordering over the stored numeric inputs, without rounding or epsilon. Current `Decimal.from_float` conversion is exact, but subsequent additions use ambient Decimal precision; returned totals use `math.fsum`. At precision 28, a synthetic two-slot roster with player 1 at float `1e30` eligible only for slot 1, and players 2/3 at 1.0/2.0 eligible only for slot 2 selects **(1,2)**. Exact Fraction arithmetic on the stored floats favors **(1,3)**. Identical displayed float totals do not make that a legitimate objective tie. Allocation/reference scoring helpers also use ambient Decimal additions, so agreement with them is not independent arbitrary-precision proof. This pilot fixes neither arithmetic nor goldens; [WR-023's separate correction gate](BACKLOG.md#mechanics-review-obligations) remains binding.

### Frozen scoring and standings

Let $F_{tw}$ be the frozen starter assignment for an active team. Its realized score is

$$
T_{tw}=\operatorname{fsum}\{X^{(i)}_{jw}:j\text{ starts in }F_{tw}\},
$$

where $i$ identifies the simulation path. Each starter contributes exactly one finite value; explicit vacancies contribute no player value and require no realization. The implementation uses careful finite accumulation without per-player rounding or flooring. Exact recorded signed values are retained, not mathematically infinite-precision real summation. Scoring revalidates ownership, eligibility, reserve exclusion, slot coverage and no duplicated starter across teams. A missing applicable score fails; a bench player with a larger realization cannot retrospectively replace a starter.

For regular opponents $t,h$, add $T_{tw}$ to $PF_t$ and $T_{hw}$ to $PA_t$, and symmetrically for $h$. If $T_{tw}>T_{hw}$, increment $W_t,L_h$; reverse for a loss. An exact tie increments both teams' tie counts only under the understood configured `allow_ties` interpretation. Missing/unsupported tie semantics fail when the tied result needs them. Canonical initial cumulative standings are included exactly once before modeled increments.

Standings use exact rational winning percentage

$$
u_t=\frac{2W_t+D_t}{2(W_t+L_t+D_t)},
$$

where $D_t$ counts ties; a zero-game record has percentage zero. Higher $u_t$ ranks first. Equal W/L/T records can use configured `TOTAL_POINTS_SCORED` descending. Equal percentage with different records, equal record/PF requiring a deeper rule, or an unsupported configured first tiebreak remain unresolved. Stable team-ID presentation does not break a competitive tie. Consumers needing a unique order, including waiver resets and seeding, must stop rather than guess. Matchup ties and standings ties are different decisions with different evidence.

**WR-014 limitation:** ordinary resolution selects a regular period's pairings each scoring week and updates weekly W/L/T/PF/PA. It has no aggregate multiweek regular-period reconciliation or equivalent universal preflight rejection. Therefore neither safe aggregate support nor reliable rejection of every such format is established. The partial route explicitly rejects it. Supported ordinary examples here use single-week regular periods; postseason accumulation does not repair this gap. See [weekly scoring authority](SEASON_SIMULATOR.md#weekly-scoring-and-standings).

### Postseason graphs, periods and placements

Postseason is an immutable graph/state calculation from **modeled final regular standings**, never snapshot historical seeds. Canonical qualifier count, round list, period IDs and ordered scoring weeks control progression. Populated first-round source pairings must reconcile with the generated graph; future placeholders cannot invent participants. [Postseason authority](SEASON_SIMULATOR.md#postseason-graphs-and-placements) owns supported configurations and evidence.

For $Q$ championship qualifiers, the fixed bracket expands to the next power of two $B\ge Q$, with $B-Q$ first-round byes for highest seeds and $\log_2 B$ required rounds. Winners follow predetermined graph edges; reseeding is unsupported and rejected. For example, six qualifiers in an eight-position bracket give seeds 1 and 2 byes; eight qualifiers give no byes. These illustrate the same construction, not a six-qualifier or fixed-team-count branch. Round durations are configured, not necessarily one week or equal between rounds/brackets.

For team $t$ in postseason game/period $m$ with configured weeks $W_m$,

$$
U_{tm}=\operatorname{fsum}_{w\in W_m} T_{tw}.
$$

Store finite signed weekly contributions and wait for all of them before declaring a winner. A first-week lead is not advancement. For example, 10 versus 8 followed by 0 versus 5 resolves **10 versus 13** for the second team, not a premature first-week win. Exact aggregate ties use higher **original postseason seed** under the understood `higher_seed` rule, not current ladder position. This supported tie interpretation is required at initialization.

The title graph can resolve more shapes than complete placements. Current championship finalization handles the two-team elimination cohorts needed by supported two/four/six-qualifier shapes; larger cohorts, such as eight qualifiers, retain `championship_complete_placement_mapping` instead of fabricated ranks. Placement games use graph-proven loser obligations. A title winner alone cannot certify every final position.

Consolation enablement is tri-state: True allows the supported ladder; False disables it; None leaves participation unresolved. Explicit mapping cannot override False/None. Nonqualifiers never cross into the championship field. The generated ladder pairs adjacent ordered nonqualifier seeds, moves winners up and losers down between rounds, and clamps the top/bottom boundaries. Even fields continue through collision-free mappings. Odd fields give the lowest seed a first-round bye, but reentry beyond that is unverified without a validated explicit mapping; report `consolation_bye_reentry_mapping` rather than inventing continuation.

For generated even-field **final** games, let $s$ be the first consolation seed and $k$ the zero-based game position. Award winner rank $s+2k$ and loser rank $s+2k+1$ directly; final current position equals awarded rank. Do not apply another winner-up/loser-down step or sort final winners by original seed. The explicit validated route differs: apply its supplied final transition, then its final-position mapping. That route must prove unique complete transition coverage, direction/boundary legality, collision-free permutations, final ranks and source/approval provenance, including odd-field continuation. Do not rewrite it into the generated formula.

Championship and consolation have independent round lists and completion times; league/season-bound audited manual mapping may establish a supported consolation structure without turning championship periods into consolation authority. Bracket-specific finalization is idempotent, with no duplicate teams/ranks globally. Missing topology/placement evidence yields incomplete outcomes; it is not solved by sorting surviving teams. Each complete path must reconcile every configured team's final rank.

Scoring participation is distinct from transaction eligibility. The named approved `all_league_teams_v1` assumption permits every team to continue essential competition, with provenance `approved_v1_assumption`; it is not ESPN evidence. The active-participant policy instead requires understood matching canonical/manual authority and graph-proven remaining obligations: current byes or future placement games can qualify, historical participation or a completed final placement cannot. An unresolved policy stops only when an acquisition would make it material. Actors may be filtered; other teams' ownership/demand do not disappear from M5. No live verified-ESPN participation provider is implemented. [Participation authority](SEASON_SIMULATOR.md#postseason-transaction-participation) retains precedence and validation details.

### Complete season walkthrough

The existing [hand-calculated synthetic season](../tests/test_season_simulator.py) has four teams, two single-week regular periods and a one-week title/consolation period. Initial W/L/T records are 8/5/0, 7/6/0, 6/7/0 and 5/8/0. All use the same projection-based coordinator with explicit policies. Shared-pool examination produces no essential acquisition in this fixture; incomplete but legal lineups can still score.

| Week | Frozen team totals (teams 1,2,3,4) | Pairings and consequence |
|---|---|---|
| 15 | 20, 10, 8, 9 | 1 beats 2; 4 beats 3. |
| 16 | 5, 15, 20, -1 | 3 beats 1; 2 beats 4. Final regular W/L/T: 9/6/0, 8/7/0, 7/8/0, 6/9/0. |
| 17 | 3, 30, 0, -2 | Seeds 1/2 contest the title: team 2 wins. Nonqualifiers 3/4 play for ranks 3/4: team 3 wins. Final placement order is **2,1,3,4**. |

The known zero D/ST contribution for team 1 is already included in those totals. Every result updates the appropriate modeled state; the snapshot stays unchanged. This connects M2 realizations to frozen scoring, cumulative standings and final outcomes without promising these fixture rules apply to another league. M5's examples next show how a different shared pool can change ownership before freezing. Broader seed/bye/round and final W/L/T/PF distribution reporting remains an [open WR-021 obligation](BACKLOG.md#wr-021-output-provenance-and-numerical-lifecycle), not delivered by this deterministic table.

## Current-week and partial-week treatment

M2 generates full future-game outcomes and M3 ordinarily starts at a verified unplayed boundary. A partly observed week needs a different **input contract**, not another season engine: preserve what has happened, identify what may legally change, and supply only the still-unobserved contribution that execution explicitly permits. [PARTIAL_WEEK](PARTIAL_WEEK.md) remains the substantive authority. This pilot explains its method without changing the companion, source mapping, scoring formula or numerical identity.

Four boundaries must remain separate: **source observation**, **preservable evidence**, **executable deterministic input**, and **supported stochastic experiment**. A source record or checksum does not cross all four. A validated synthetic companion is **Verified by tests**, not authenticated live ESPN evidence. The supplied authority vocabulary is `verified_live`, `verified_by_tests`, `unverified`, `unsupported`; those declarations do not independently authenticate source bytes or real-world permission.

### Observed assignments, proposed assignments and locks

Canonical roster records establish player/team/slot ownership as of retrieval. They do not automatically establish a historical current-week lineup. Observed evidence must match **exact canonical player/team/slot assignments**, derived starter/bench/reserve roles and exact canonical eligibility, with every roster entry once, configured capacities, referenced sources and observation times within the snapshot/companion retrieval interval. A legally eligible FLEX/bench exchange can still be a forged observation. League-specific slots and capacities come from configuration, not a universal roster template.

Executable timing requires the assignment source view to include `mRoster` and either request `scoringPeriodId` equal to the companion's current week, or be an unparameterized current roster request whose snapshot live context identifies that same week. The simulation horizon is not timing evidence. A coherent record with unknown/wrong roster timing can be preserved, but execution fails closed. [Observed authority](PARTIAL_WEEK.md#observed-assignments-and-locks) and [DATA's temporal boundary](DATA.md#live-and-temporal-evidence) retain the precise source interpretation.

The proposed lineup is a separate complete player/team/slot assignment over the same observed roster. It cannot change ownership or overwrite immutable observation. Eligibility and starter/bench/reserve capacities remain mandatory. Lock permission is player-specific:

| Lock state | Evidence and proposed movement | Executable composition |
|---|---|---|
| `verified_locked` | Verified determination; assignment cannot move | Preserve the observed slot. |
| `verified_changeable` | Verified determination; a started player cannot have this state | May move only to a configured eligible slot within capacity. |
| `unresolved` | Coherent unverified/unsupported permission may be preserved; assignment cannot move | Rejected **even when the proposed slot is unchanged**. |

Kickoff timestamps, NFL scheduled/completed status and assumed league-wide locking conventions cannot substitute for independently verified lock/change permission. Executable composition validates a **supplied hypothetical lineup**, not a current-week recommendation or optimizer. Current-week locks protect observed assignments; later weeks return to ordinary lineup selection instead of inheriting those locks forever.

### Fixed actuals and supplied remaining realizations

Each player record separates NFL game status, score state, fixed actuals, full-game projection, remaining-contribution approval and source. There are exactly five score states. **Unresolved authority is an evidence condition, not a sixth score-state enum.** Confirmed actual zero and missing evidence remain different.

| Score state | Preservable evidence | Deterministic starter contribution |
|---|---|---|
| `completed_fixed` | Completed game and confirmed finite actual, including zero/negative; remainder not applicable | Fixed actual once; any supplied resimulation input rejects. A zero/negative projection cannot erase it. |
| `unstarted` | Scheduled game, no actual, finite approved full-game projection | Exactly one finite `unstarted_realized_points`; no approved-remainder value. |
| `in_progress` | In-progress game, confirmed actual-so-far; remaining status approved or unresolved, never not-applicable | Requires approved semantics and exactly one finite `approved_remaining_points`; no unstarted value. Unresolved remainder blocks execution. |
| `missing` | No invented actual or remainder | Evidence can be retained, but executable validation rejects missing states, including supplied nonstarter records. |
| `nonparticipating` | No invented actual or remainder | Cannot contribute as a starter; do not supply a realization for it. This label is not inferred from a zero projection. |

Bench/reserve and explicit fantasy-team bye assignments contribute no starter points; supplied unused values still reject. Missing actuals cannot be filled with zero. Duplicate values, values for completed players, wrong categories, omitted required values and unused bench/bye inputs fail. Approval of an in-progress deterministic remainder applies to explicit supplied values; it does not create a conditional probability distribution, injury/participation event, pace model or remaining-value estimator. In particular, **projection minus actual-so-far is not an authorized remainder**. An injury during a game does not itself authorize zero remaining points.

For current scoring week $w$, let $J_{tw}$ be the proposed executable non-bye starters. Define components for each starter $j$:

$$
(f_{jw},r_{jw}^{\mathrm{rem}})=
\begin{cases}
(A_{jw},0),&\text{completed_fixed},\\
(0,x_{jw}^{\mathrm{full}}),&\text{unstarted},\\
(A_{jw}^{\mathrm{sofar}},x_{jw}^{\mathrm{rem}}),&\text{in_progress with approved remainder}.
\end{cases}
$$

Here $x^{\mathrm{full}}$ and $x^{\mathrm{rem}}$ are explicitly supplied realizations, not observed facts or automatic transformations of ESPN projections. Then

$$
F^{\mathrm{fixed}}_{tw}=\operatorname{fsum}_{j\in J_{tw}}f_{jw},\qquad
R^{\mathrm{rem}}_{tw}=\operatorname{fsum}_{j\in J_{tw}}r_{jw}^{\mathrm{rem}},\qquad
Q_{tw}=F^{\mathrm{fixed}}_{tw}+R^{\mathrm{rem}}_{tw}.
$$

Thus **current-week points = fixed actuals + approved remaining points**. Observed current-week team points must reconcile **exactly to $F^{\mathrm{fixed}}_{tw}$**, not to carry, projections or simulated remainder. Source observations and modeled contributions keep separate provenance. Preserve signed finite values and the existing accumulation/order; these accounting equations authorize no reassociation, clipping, rounding or tolerance substitution.

Let $C_{tm}$ be independently verified earlier-week carry within current matchup period $m$. The composed period slice is $C_{tm}+F^{\mathrm{fixed}}_{tw}+R^{\mathrm{rem}}_{tw}$. When $w$ is the last week of $m$, **final matchup-period points = prior verified carry + current-week points**. If the period continues, future weekly scores must also accumulate before finalization. The composer's field `final_matchup_points` names this composed slice; it does not authorize premature bracket advancement. [Composition authority](PARTIAL_WEEK.md#player-states-and-deterministic-composition) owns the exact arithmetic contract.

**Synthetic signed example:** use the existing reconstructible first-round postseason fixture with full period membership **(15,16,17)**, current week 16, simulation horizon 16–17, verified cutoff through 14 excluding this period, and complete prior week-15 team scores. Team 1's carry is 100. Its locked completed D/ST has actual **-2**; its locked in-progress QB has actual-so-far **3** and an explicitly approved deterministic remainder **4** (not projection minus actual). The fixture's verified-test observed current-week total is **1**:

| Component | Points |
|---|---:|
| Completed fixed actual | -2 |
| In-progress actual-so-far | 3 |
| Fixed current-week sum | 1 |
| Approved deterministic remainder | 4 |
| Composed current-week total | 5 |
| Verified week-15 carry | 100 |
| Composed period slice through modeled week 16 | 105 |
| Subsequent week-17 realization | 3 |
| Final period total after all three weeks | 108 |

The opponent's carry 0, week-16 realization 15 and week-17 realization 30 give final 45. Prior coverage also includes both consolation participants (week-15 scores 10 and 0), not just the title teams. The fixture provides a matching roster-time source, verified-test locks/score/carry/cutoff and exact team/week history. At week 16 there are no placements; week 17 resolves 108 versus 45. This is synthetic executable arithmetic based on [the existing carry fixture](../tests/test_partial_season.py), not live source authentication or an unconditional forecast for the QB.

### Standings cutoff, period carry and season integration

The full period $m$ can begin before the stored simulation horizon. The first simulation week is not proof that preceding scoring contributions may be omitted. Companion membership must match canonical schedule authority; with current live metadata, use independently supported full `matchup_period_configuration` membership including pre-horizon weeks. A shortened stored list cannot establish a safe boundary. A different live current week cannot simply be omitted. Without live metadata, the accepted canonical period/request-timing contract still applies; schema-v2/v3 reads and earlier readable v4 records do not manufacture new evidence or execution permission.

Standings cutoff names settled period IDs, through-week, explicit exclusion of current period, source and authority. Executable composition requires a verified cutoff excluding the current period. **Season execution additionally requires through-week = first actual period week minus one**, all known preceding canonical periods settled and no known current/future period settled. It validates those supplied assertions; it does not independently authenticate historical ESPN cumulative standings totals. Current-period scores and carry cannot already be included in initial settled standings. [Period/cutoff authority](PARTIAL_WEEK.md#standings-and-period-authority) preserves these separate gates.

Mid-period matchups need verified finite carry for both teams; first-week evidence cannot invent earlier carry. For postseason execution, provide exactly every preceding current-period **team/week contribution**, including pre-horizon weeks, with no duplicates, omissions or unrelated teams. Each team's `fsum` must equal its aggregate verified carry. Source-grounded scheduled pairings and explicit byes must cover rostered teams and agree with modeled seeded participants. Fantasy bye teams need no score inputs, while active championship and consolation obligations remain separate.

NFL completion or `statsOfficial` alone establishes neither fantasy settlement, standings incorporation nor stat-correction finality. Raw score presence, wall time and hashes cannot close those gaps. Corrections need new immutable snapshot/evidence publication; old bytes/results are not rewritten. The existing [DATA observations](DATA.md#source-observations-and-limitations) remain bounded historical evidence: the 11 November 2026 unplayed sample verified candidate field presence/type, not active-game lock permissions, conditional remainders, live score latency, carry/bench semantics or fantasy finality.

The opt-in deterministic path uses M3's **same season coordinator**, in this logical dependency sequence (the implementation performs composition during preparation and checks further season gates before returning a result):

1. Validate snapshot/companion linkage, timing, sources and preservation invariants; require the season path's verified companion-level authority and no unresolved dependent capabilities.
2. Validate exact observed assignments and the separate proposed lineup, capacities, eligibility and executable locks.
3. Reconcile current week, authoritative full membership, immediately preceding standings cutoff and required prior carry/history. Missing authority cannot be replaced by a checksum or a later start.
4. Compose the current week exactly once from fixed and supplied values. Ordinary deterministic scenario scores must contain **subsequent weeks only**; a first-week score in that scenario rejects rather than contributing again.
5. Skip first-week essential transactions. Reject retroactive initial ownership/slot-state changes or an existing transaction ledger. A separately legal lineup proposal is a supplied slot assignment under verified permissions, not a current-week trade/claim authorization.
6. For regular scoring, reuse the weekly resolver, disabling only ordinary positive-projection selection for these already validated starters; ownership, eligibility, capacities and canonical values remain checked. For postseason, replay verified prior weekly contributions into the existing accumulator, then add **only current fixed-plus-remaining**, not aggregate carry again.
7. Restore full period membership and advance only once all applicable weeks are complete. Resume ordinary future-week transactions, lineup optimization, scoring and bracket progression; current-week locks do not freeze future decisions.

Supported season starts are single-week regular periods and reconstructible **first-round** postseason matchups/byes, including mid-round carry with complete preceding history. Later-round starts lacking prior bracket history fail rather than inventing winners or seeds. Partial execution explicitly rejects multiweek regular periods; ordinary V1's separate WR-014 guard gap in M3 remains unchanged. No full historical postseason reconstruction is claimed. [Integration authority](PARTIAL_WEEK.md#deterministic-season-integration) and [M3's current owner](SEASON_SIMULATOR.md#partial-first-week) retain exact interfaces and restrictions.

### Supported execution states and pregame equivalence

| Capability | Permitted calculation | Evidence/unsupported boundary |
|---|---|---|
| Ordinary whole-week V1 | Existing projected lineups, transactions and full-game draws | With live metadata, current unplayed week must start its independently supported full period; cannot skip unresolved preceding contributions/settlement. |
| Deterministic partial composer | Supplied legal lineup with fixed actuals, approved full-game or deterministic remaining values and verified carry | Exact current observed-score reconciliation, timing, locks, cutoff and field-specific authorities; preservation/serialization alone is insufficient. |
| Deterministic partial season | First composed week once, then the same ordinary coordinator | Adds verified companion-level authority, immediate period cutoff, pair/bye/history reconstruction and no initial/current transactions. |
| Fully-unstarted partial Monte Carlo | Existing full-game player draws routed through the deterministic partial input | **Every rostered current player, including bench and reserve**, must be unstarted with approved matching nonmissing canonical projection. |
| Current-week browser/conditional forecasting | Unsupported | No public partial request fields, automatic source translator, current-week action/lineup recommendation or conditional remaining-game sampler. |

The Monte Carlo gate is stronger than deterministic composition. Completed, in-progress (even with an approved deterministic remainder), missing and nonparticipating rostered players all reject, as do unresolved game/lock/remaining/cutoff permissions. A scheduled NFL game is a player-state fact; a fantasy-team bracket bye is a scoring obligation. The latter does **not waive the rostered-player gate**: its players must still meet unstarted/full-game requirements, even though their current-week draws are not used as starter inputs. Matching nonmissing canonical projections may be explicit zero or signed values; this gate does not turn them into ordinary positive-projection eligible starters.

Before sampling, Monte Carlo validates the companion, proposed lineup and the narrow current-player gate. The deterministic coordinator retains the additional period/cutoff/history execution checks; passing the sampler gate cannot waive them. Generate the existing **complete canonical player-week universe exactly once per path**. Map only proposed current non-bye starter draws to unstarted deterministic values, remove **all current-week scores** from the ordinary subsequent-week scenario, and call the same coordinator. Bench/reserve/bye draws remain in the original scenario identity but are not supplied as unused composition inputs. No second independent draw set, completed resimulation, in-game unconditional redraw or conditional distribution is added. Future-week draws and mathematics are unchanged.

Three identity scopes are distinct:

| Scope | Meaning and limit |
|---|---|
| Companion identity | Binds immutable snapshot/league/season, current week/full period, retrieval interval, selected sources, observed assignments, player/matchup/cutoff evidence and declared unresolved capabilities. Artifact version 1 is independent of snapshot schemas 2/3/4. |
| Source-basis digest | Binds snapshot identity and selected source IDs/payload hashes; **not all companion content**, not independent authentication and not sufficient run identity. |
| Full-content integrity/configuration | Serialized artifact checksum covers complete evidence. Deterministic partial provenance also includes sorted proposed lineup, supplied realizations and history; Monte Carlo configuration binds complete companion, proposed lineup/history and the partial contract alongside ordinary model/policies. Changes invalidate incompatible checkpoints. A rewritten content/checksum pair is not authentic evidence. |

The path summary retains the **original complete scenario ID and score-content digest** for matched-draw auditing. Partial and ordinary configurations intentionally differ when the companion is supplied; score identity is not configuration identity. With absent partial input, no partial fingerprint/provenance entry is added. Existing corrected-Normal versus historical-Normal identity boundaries in M2 remain independent. Exact serialization, hash recipes, typed interfaces and checkpoint/execution compatibility remain in [companion preservation](PARTIAL_WEEK.md#companion-identity-and-preservation), [MC routing](PARTIAL_WEEK.md#monte-carlo-subset) and [numerical identity](MONTE_CARLO.md#configuration-run-and-path-identity), not a new technical specification here.

Pregame equivalence requires identical snapshot, model, seed, **prescribed path range**, league/IR/acquisition/postseason policies, consistent period/cutoff/history evidence, matching legal current starters (including V1's optimized assignments), the same player-week realizations and no first-week acquisition changing ownership. Under these supported preconditions, team scores, matchups, standings, postseason/path outcomes and aggregate probabilities agree. Partial provenance and first-week transaction audit remain distinct. A different legal supplied lineup may intentionally change team outcomes without changing player draws. Seed alone, unequal adaptive path counts or unsupported in-progress states cannot establish equivalence. Sequential/batched/parallel and execution-compatible resumed runs must preserve the same supported path results; P5 retains detailed inference and numerical recovery treatment.

Useful falsification cases and existing evidence include:

| Attempt | Required result / current regression evidence |
|---|---|
| Eligible observed starter/FLEX/bench exchange or overcapacity | Reject mismatch with canonical observation or capacities; [lineup adversaries](../tests/test_partial_week.py). A separately changeable legal proposal does not rewrite evidence. |
| Move locked/unresolved player, or leave unresolved lock unchanged | Proposed movement rejects; unchanged unresolved lock still fails execution; [lock fixtures](../tests/test_partial_week.py). |
| Replace missing actual with zero, or in-progress input without approved remainder | Preserve genuine zero; reject invented actual or unresolved execution; [state/composition fixtures](../tests/test_partial_week.py). |
| Wrong cutoff, shortened full membership, omitted/duplicate/conflicting carry history | Reject inclusion/gap/authority/coverage mismatch; [period/carry integration](../tests/test_partial_season.py). |
| First-week ordinary score, retroactive initial ownership or transaction ledger | Reject double contribution/current transaction; [once-only season tests](../tests/test_partial_season.py). |
| Completed/in-progress/nonparticipating/missing bench or reserve, including a fantasy-bye roster | Reject the narrow gate before sampling; [MC gate/draw-once/equivalence evidence](../tests/test_partial_monte_carlo.py). |

This chapter preserves the plan's **S128–S136 and S165** mapping without transferring current ownership. Future responsibilities remain identifiable through the [accepted partial-week disposition](development/model-documentation-architecture.md#partial-week-disposition): DATA/D5 owns field/timing/assignment/lock/cutoff source authority; M4 owns composition/use/integration/equivalence; future VALIDATION V1/V2 will organize adversarial/once-only/replay checks; future TECHNICAL_REFERENCE T2/T4/T6 will organize artifact/interface/identity bytes. Those future files do not exist and are not linked as current authorities. BACKLOG retains unimplemented translation, public integration, historical reconstruction and conditional research.

The supported implementation at accepted P3 `a9cca474ae0157050cea8cc14368275e2435f17d` is inspectable in [foundation](../src/fantasy_football/partial_week.py), [serialization](../src/fantasy_football/partial_week_serialization.py), [season coordinator](../src/fantasy_football/season_simulator.py) and [Monte Carlo](../src/fantasy_football/monte_carlo.py). Tests prove synthetic/code behavior, not new live authentication or calibration. [WR-009 through WR-015](BACKLOG.md#numerical-and-partial-evidence-obligations) and [WR-018/019](BACKLOG.md#mechanics-review-obligations) retain active-game evidence, permission, translation/API, wider state, bracket-history and conditional-method gates. Approved future conditional research requires authentic immutable intragame vintages and held-out group/clock/support/calibration/decision evidence; retrospective final scores or a supplied deterministic remainder cannot establish it. No LW2.3B functionality, model promotion, source-consumer migration or release approval follows from P4.

## Roster evolution and transaction rules

[TRANSACTIONS](TRANSACTIONS.md) remains the current authority. M5 describes **operational roster evolution inside each simulated season**. M8's analyst-proposed trades, manual completion and finite action search are separate experiments, scheduled for P6. They share primitive legality and valuation, but their objectives, completion phases and sequences are not interchangeable. Simulated future acquisitions are not actual ESPN manager decisions, submitted claims or execution probabilities.

### Legal state and explicit model conventions

For week $w$, modeled state $E_w$ retains snapshot linkage, one authoritative ownership/occupancy relation, acquisition availability, independent season/period counters, cycle and period identities, current and frozen opening waiver queues, IR evidence/policy and ordered transaction history. Every transition returns a new validated value. Canonical source ownership remains immutable; changed modeled ownership must not be rejected merely because old source status still describes the original owner.

Dynamic configured starter/bench/reserve and position capacities, eligible slots and unique ownership constrain add, drop, compound replace, supported IR placement and explicit activation. An illegal compound effect exposes no partial mutation or acquisition increment. A reserve occupant cannot start or activate implicitly. Undroppable source evidence governs affected drops; current designations are frozen along the modeled path as an approved replaceable assumption, not a prediction of future ESPN list changes. Missing/unknown protection evidence blocks an affected automatic drop.

Unowned availability distinguishes immediate free agent, waivers, hold and unresolved; rostered players are not pool supply. A drop creates an irreversible same-cycle hold. Advancing cycles does not silently release it. Release needs a validated player/boundary/semantic-clearance authorization, digest and source; known clearance time additionally needs a decision timestamp at or after it. Valid release can produce free-agent or waiver status. A directly constructed assertion or unrelated source ID is insufficient. [Evidence trust](TRANSACTIONS.md#eligibility-evidence-trust-boundary) currently mints only `verified_by_tests` fixture determinations; reserved `verified_source` cannot be manufactured by relabeling a fixture.

Season and matchup-period acquisition limits/counts are separate. Unknown initial usage with a finite limit blocks affected acquisition permission; an unlimited limit does not require invented usage evidence. Successful additions increment each known counter, while unknown counts remain unknown; failed operations increment neither. Only crossing a canonical period resets period counts; season counts persist. Supported successful traditional waiver claims move the claimant to last; free-agent additions do not move either queue. Configured weekly resets use the unique inverse modeled standings, not a guessed real-world clock.

IR policy must be explicit:

- **projection_based:** a positive-projection reserve occupant blocks acquisition until explicit corrective activation. The ledger labels the approved assumption; this is not an ESPN medical or eligibility rule.
- **strict:** validated player/week evidence distinguishes ELIGIBLE, INELIGIBLE and UNKNOWN. Eligible reserve occupancy does not block; ineligible occupancy requires correction; absent/unknown evidence remains unresolved. Strict activation requires that player's same-week ineligible determination. Both policies require supported OUT/IR evidence for placement; neither implicitly activates a reserve player.

The modeled weekly pregame window and reverse-opening-priority free-agent order are approved conventions. Exact individual game locks, waiver clearance clocks/timezones, multiple submitted-claim ordering, dropped-player reentry and authentic strict future IR status are **not supplied by those conventions**. Non-budget traditional waivers are supported; FAAB/unknown formats have no fallback. Postseason actor permission follows M3's separate authority. [WR-018](BACKLOG.md#mechanics-review-obligations) retains the evidence-dependent extensions; no missing setting receives a default.

### Operational essential acquisitions

Let $d_{tw}(E)$ be current mandatory starter vacancies under the **owned-only** positive-projection optimum. A full legal acquisition plan $c$ is essential iff

$$
d_{tw}(E^c)<d_{tw}(E).
$$

A coverage-improving acquisition is different from a voluntary projected-points upgrade to an already fillable lineup. A larger immediate gain does not by itself rank qualifying plans. The governing objective is highest resulting remaining-horizon $V_t(E^c)$ among eligible legal effects with sufficiently resolved values, followed by stable deterministic ties. Materially unresolved alternatives cannot justify a certified global maximum.

For every phase-eligible unowned player, enumerate supported destinations and complete legal effects: necessary drops, required IR activations, and a finite graph of reactive IR placements/corrections in legal orders. A verified injured ordinary occupant may move to reserve to free capacity for a **different** required activation, even if it cannot occupy the new player's slot. Relevance is checked at completed acquisition paths: each placement releases a distinct ordinary capacity unit consumed by a later required activation or final add. Intermediate moves need not improve coverage. Only attempt a capacity drop when the corresponding no-drop operation is illegal. Each player uses each allowed movement direction once; drops cannot be reversed in the cycle.

Preserve effects distinguished by ownership/occupancy, availability/holds, evidence, counts and movement history affecting later legality. Deduplicate effect-equivalent results without merging different future permissions. Legal sequences, essential-qualified sequences and complete-valued sequences are separate counts; unique resulting effects have their own count. No player cutoff, preferred-position shortcut or positive-intermediate-value pruning replaces complete effect enumeration.

**WR-024 remains unresolved.** Production excludes materially incomplete-valued plans from its ranked set and can select a complete alternative. The independent sequential reference instead reports `determination_complete=False` when such alternatives could affect ranking; equivalence cannot certify that decision. The binding fail-closed requirement is not waived: a retained complete plan is not a certified maximum over unresolved alternatives. Mixed-valuation correction and season propagation require separate scope/review. The pseudocode below describes **current production behavior**, including that discrepancy, not its authorization as the desired final policy.

```text
for phase in (authorized modeled waivers, immediate free agents):
    repeat:
        progress = false
        order = current dynamic priority at start of waiver pass
                or reverse frozen opening priority for free agents
        for eligible actor t in this pass order:
            recompute owned-only vacancies from current shared state
            if no mandatory vacancy: continue
            enumerate complete legal acquisition effects
            retain effects strictly reducing current vacancies
            evaluate resulting remaining-horizon V for each
            record unresolved authorization and incomplete valuations
            rank complete-valued effects only                 # WR-024 gap
            if no selectable effect: retain reason and continue
            execute highest V, breaking exact ties by stable key
            if waiver claim succeeded: move actor to queue bottom
            progress = true
        stop phase when a whole pass has no success
```

The stable selection key is acquired player ID, sorted dropped IDs, sorted activated IDs, sorted placed-on-IR IDs, then destination slot ID. Each waiver pass traverses its opening dynamic order once; a successful move affects subsequent priority, not a second turn in that pass. Waiver authorization requires the typed `modeled_weekly_waiver_boundary_v1` assumption or no waiver processing. It authorizes the modeled phase, not held-player clearance. Free-agent passes always use **reverse frozen opening priority**, not reverse post-claim order; successful additions do not move it. Recompute needs and supply after every mutation and repeat passes for additional holes. If no selectable plan exists and unresolved authorization/valuation remains material to a vacancy, the coordinator reports incomplete execution; the presence of a selectable complete alternative does not yet close WR-024.

Each success strictly reduces its actor's vacancies, consumes finite supply and prevents same-cycle reentry of drops. Combined with bounded correction movements, one success per actor per pass and no-progress termination, this avoids an arbitrary depth cap. It is a sequential greedy manager policy, not league-wide optimal coordination or reconstruction of actual claims. Eligible actors may be restricted without removing anyone's owned players or replacement demand.

**Synthetic essential transaction:** four teams have one QB and one D/ST starter each. Team 1 owns only its positive QB; all others are staffed. Two accessible D/ST free agents project 8 and 6 in each of three remaining weeks, with sufficient roster capacity, understood protection and unlimited acquisition rules. Team 1's vacancy count is 1. With opening priority (1,2,3,4), free agents are visited (4,3,2,1); only team 1 needs an acquisition. It adds the 8-point D/ST, reducing vacancies to 0, recording the add/counter increments and new ownership; no drop or priority movement occurs. The original state's empty ledger remains empty. Once fully staffed, it does not make another voluntary upgrade. This is the [existing synthetic weekly fixture](../tests/test_weekly_transactions.py), not a league-size or transaction-success assumption.

### Resulting-roster value and replacement access

$V(R)$ ranks roster-policy alternatives, not champions. Given state $E_{w_0}$, target team $t$, remaining first week $w_0$ and final horizon week $W$, define

$$
V_t(R_t,E_{w_0})=\operatorname{fsum}_{w=w_0}^{W}\widehat L_{tw}(R_t,E_{w_0}).
$$

Every week has weight **one**, including postseason weeks. The first valuation week defaults to the state week and must lie within its remaining horizon. Inputs are canonical effective projections, configured slots/eligibility, nonreserve ownership, shared unowned availability and explicit access context. There is no horizon discount, injury probability, positional premium, numeric access-success estimate or nested Monte Carlo. $L_{tw}$ is an owned-only projected lineup score; $\widehat L_{tw}$ also reflects marginal replacement opportunities; $V_t$ is their multiweek sum, not championship probability.

For each remaining week, the [replacement method](TRANSACTIONS.md#weekly-replacement-calculation) does the following:

1. Solve owned-only lineups for target and opponents. Count demonstrated mandatory vacancies $d_{hw}$, not speculative upgrades, injury insurance or roster turnover. Reserve players never activate implicitly.
2. Build a single positive-projection unrostered pool. Immediate free agents enter the snapshot-time marginal approximation. In `CURRENT_WAIVER` context, waiver players enter only for the state week; only opposing teams ahead of the target in **current dynamic** priority can consume those waiver players. Free-agent supply remains accessible to opposing demand regardless of that waiver ordering. `FUTURE_CONSERVATIVE` admits immediate free agents and treats every identifiable opposing essential demand as potentially ahead; it does not admit future waiver clearance. Rostered, held and unresolved supply is excluded, with diagnostics.
3. Allocate accessible players across opposing vacancies without duplicate use. For each proposed opposing set, reoptimize that team's whole owned-plus-replacement lineup, allowing FLEX rearrangement; accept only additions that increase filled coverage. Among feasible allocations, lexicographically **maximize vacancies filled; maximize opposing projected improvement; minimize the target's best residual attainable lineup; then stable vacancy/player identity**. Full lineups create no upgrade demand. Distinct consumed-player sets must survive even if they share a vacancy mask.
4. For allocation $A$, remove its consumed players from pool $P_w$ and reoptimize the target over owned players plus $P_w\setminus A$. The target may use at most its original $d_{tw}$ replacement players. The third, target-adverse opposing objective uses this actual residual target optimization, not a valuation result reused as its own oracle. Resulting score is $\widehat L_{tw}$; unfilled positions remain explicit vacancies.
5. Sum those weekly scores with weight one. Retain owned/replacement/total points, assignments, residual vacancies, competing demand, access ranks, exclusions, assumptions and unresolved inputs.

The opposing objective is ordered, not a weighted sum: filling more mandatory slots wins before projected improvement, and target adversity applies only after ties in those first two objectives. Replacement contribution is adjusted lineup value minus owned-only value, which can include rearrangement rather than simply a new player's raw points. No player is assigned to multiple teams in the same weekly calculation.

These are **marginal opportunities, not persistent acquisitions**. The same free agent can appear as an opportunity in different weeks without moving ownership or incrementing counters. Snapshot-time availability/owned rosters are evaluated under each week's projections; V(R) does not forecast future priority, releases or lasting pool turnover. After an actual modeled weekly transaction, recompute value from the changed shared state.

**Synthetic competing-pool example:** use the same QB/D/ST configuration. Target owned QB projections are 10,11,12 over three weeks; it lacks D/ST. Accessible D/ST supply is 8 and 6 each week; other staffed opponents have no upgrade demand. With no opposing vacancy, target adjusted weekly values are 18,19,20 and **V=57**. With one opposing D/ST vacancy, maximum opposing improvement consumes 8, leaving target 6: values 16,17,18 and **V=51**. With two opposing vacancies both players are consumed, leaving target 10,11,12 and **V=33**. Every case is a fresh valuation without ledger mutation. The [allocation fixtures/oracle](../tests/test_roster_value.py) verify these values; the rule is shared scarcity, not arbitrary discounting or prediction that a particular manager acquires the player.

Positive unresolved-status supply makes value incomplete **only when** admitting it can change target replacement-adjusted points after exact pool reallocation. Held or immaterial unresolved records stay visible without falsely invalidating value. Unknown availability is never permission. A returned numeric total with `is_complete=False` cannot certify ranking. Structural roster valuation may evaluate a supplied legal hypothetical state without authorizing the transaction sequence producing it; execution legality remains separate.

### Independent correctness and remaining obligations

Methodological exactness applies to the explicitly selected finite universe, with known arithmetic and valuation gaps stated separately. [Current independent contracts](TRANSACTIONS.md#independent-reference-contracts) distinguish:

| Reference | What it establishes; what it does not |
|---|---|
| Exhaustive lineup assignments | Enumerate legal assignments to check ordinary optimum, vacancies and stable ties. Existing Decimal-scoring references are not an arbitrary-precision solution to WR-023. |
| Exhaustive allocation leaves | Assign each small-pool player unused or to an accessible opponent, then independently compare full coverage, opposing gain, true target residual score and stable assignment. Do not use end-to-end V(R) as its own oracle. |
| Independent correction sequences | Enumerate bounded primitive IR/drop/add paths without production graph/relevance pruning, then compare legal/essential effect sets, ownership, holds and maximum resolved V(R). |
| Feasible full transaction cycles | Branch every authorized essential effect and explicit pass over full state/phase/pass/order/processed/progress identity. This enumerates counterfactual histories, not the mandatory greedy policy's choice. |
| Sequential policy reference | Independently enumerate the same operational choices, require determinate ranking and compare normalized trace, full ledger, final rosters/reserve/holds, queues, counters, vacancies and every team's resolved V(R). Timing is excluded; numerical totals alone are insufficient. |

Feasible cycles retain authorized branches even when their valuation is unresolved, reporting terminal value None and separate legal-enumeration/valuation-completeness counts. They cannot certify a sequential ranking over those alternatives. Exhaustive returned trees have no budget-truncated success mode; interruption returns no exhaustive result. Exponential cost makes them small-universe correctness references, not a second season simulator.

Optimizations must preserve these guarantees. Opponent branch-and-bound starts only after complete opposing coverage establishes an incumbent; a branch is pruned only when its optimistic remaining-projection bound cannot **match** that incumbent, retaining equal cases for target-adverse/stable ties. Incomplete-coverage search remains complete. When at most $k$ limited players may be selected, identical starter-edge classes need only their best $k$ candidates by projection then stable ID. Opponent reductions additionally require identical accessible-opponent-team sets, can consume at most the demonstrated vacancy count, and retain removed opponents' candidates in the target residual pool. Existing independently disableable dominance paths must match exhaustive leaves and correction effects with reductions enabled and disabled, including the QB/FLEX 29-point and simultaneous-shortage regressions. Cache/index implementation details stay with [safe reductions](TRANSACTIONS.md#safe-reductions-and-independent-correctness); no global cache or lossy throughput cutoff is approved.

These are **Verified by tests** synthetic/reference guarantees, not source-authenticated live waiver/IR semantics or empirical decision quality. [WR-008](BACKLOG.md#wr-008-representative-performance-and-diagnostics) still requires sampled full-simulation comparisons of V(R) ordering/choices and replacement outcomes, sensitivity, runtime and memory; no nesting Monte Carlo into every acquisition decision is implied. WR-014/018 preserve unsupported rules/formats, WR-021 broader outcomes/provenance/release gates, and WR-023/024 the unchanged correctness defects. Their [permanent obligations](BACKLOG.md#mechanics-review-obligations) cannot be closed by this exposition.

Inspected implementation baseline is accepted P2 `fed2dc7863607f539e2640b7c7e6d72ff9fdb087`. Sources: [season coordinator](../src/fantasy_football/season_simulator.py), [lineups](../src/fantasy_football/lineup_optimizer.py), [scoring/standings](../src/fantasy_football/weekly_engine.py), [postseason](../src/fantasy_football/postseason.py), [state/evidence](../src/fantasy_football/evolving_state.py), [weekly acquisitions](../src/fantasy_football/weekly_transactions.py), [cycle references](../src/fantasy_football/transaction_cycle.py) and [roster value](../src/fantasy_football/roster_value.py). Tests retain [exhaustive lineups](../tests/test_lineup_optimizer.py), [scoring](../tests/test_weekly_engine.py), [postseason configurations](../tests/test_postseason.py), [state/evidence](../tests/test_evolving_state.py), [weekly correction effects](../tests/test_weekly_transactions.py), [allocation leaves](../tests/test_roster_value.py), [cycle/policy equivalence](../tests/test_transaction_cycle.py) and [season immutability/replay](../tests/test_season_simulator.py). Full interfaces, caches, serialization, draw-byte and checkpoint contracts remain in their current authorities. No production behavior or numerical identity changes; actual checks/results belong in the P3 PR.

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
