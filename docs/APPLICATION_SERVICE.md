# Application service and HTTP contracts (M6.1)

Status: **IMPLEMENTED — REVIEW PENDING**.

Governing requirements are `MASTER_SPEC.md` Sections 2, 8, 9, and 12 plus the
M6.1 roadmap gate. M6.1 adds a synchronous local adapter over the accepted
engine. It does not add analytical rules, background jobs, persistent run
history, live updates, authentication, or frontend code.

## Boundaries

`fantasy_football.app.contracts` contains frozen Pydantic DTOs with public schema
version `1.0`. `fantasy_football.app.service` maps those DTOs to the accepted
snapshot store, M3 precision runner, M4 scenario evaluator, and M5.8 search
orchestrator. `fantasy_football.app.http` translates the same services into
FastAPI routes. `fantasy_football.app.server` is the loopback-only development
entry point.

The dependency direction is HTTP → application service → accepted engine →
snapshot/result storage. The application layer validates public shape, numeric
ranges, schema versions, and resource bounds. The engine remains authoritative
for league settings, legality, completion, candidate feasibility, distributions,
probabilities, precision, and ranking.

M6.1 intentionally supports the explicit provisional Normal model through HTTP.
No model is selected implicitly. Empirical-model requests require a future
explicit evidence-selection DTO; an unknown model discriminator is rejected.

## Versioned HTTP surface

| Method | Route | Contract |
|---|---|---|
| GET | `/api/v1/health` | Service/schema/build metadata; no snapshot or credentials required. |
| GET | `/api/v1/snapshots` | Compact persisted snapshots with optional league/season filters. `team_count` is null because compact store metadata does not load the canonical document. |
| GET | `/api/v1/snapshots/{snapshot_id}` | Full canonical league/team summary plus unresolved rule capabilities. |
| POST | `/api/v1/analyses/baseline` | Synchronous accepted M3.4 precision execution. |
| POST | `/api/v1/analyses/manual-scenario` | Synchronous accepted M4 completion and paired evaluation. |
| POST | `/api/v1/analyses/action-search` | Synchronous accepted M5.8 unified action search. |

Requests use strict discriminators and forbid unknown fields. Probabilities are
named `*_probability`; paired changes are `*_probability_points`; counts include
their units. Missing estimates remain null, never zero. Candidate generation
coverage, state evaluation coverage, all-team precision, ranking resolution,
transaction authorization, and acquisition condition remain separate fields.

Search response `response_candidate_limit` is a display/transport bound between
1 and 500. It does not change the analytical candidate universe. The response
retains total coverage and `response_truncated`; candidate rows are read only up
to that limit. Candidate/evaluation resource limits remain separately explicit
and can make analytical coverage incomplete.

## Configuration and defaults

There are no hidden analytical defaults for seed, path budget, IR policy,
waiver boundary, precision, outcome dispersion, requesting team, candidate
universe, or action ordering. The few transport/runtime defaults—schema `1.0`,
first path zero, sequential execution, one worker, queue/page sizes, and response
limit 100, and synchronous 10,000-path ceiling—are present in the versioned DTO
schema. The path ceiling is an M6.1 request-safety limit, not an analytical
shortcut; M6.2 will govern larger work through bounded background policies.
Canonical roster, scoring,
team count, postseason, and acquisition rules always come from the snapshot.

Finite acquisition limits whose source counts are unknown, unsupported waiver
mechanisms, unresolved transaction evidence, and unsupported engine semantics
continue to fail closed. The API does not translate them into friendlier rules.

## Provenance and identity

M6.1 resolves the application-level build provenance gap with an outer
`application-run-identity-v1` envelope. It does **not** alter M3 simulation
fingerprints, M3.6 checkpoints, M5.3 state identity, or M5.8 search identity.

Every result exposes:

1. `analytical_equivalence_sha256`, binding the accepted deterministic analysis
   or search identity;
2. `application_execution_sha256`, additionally binding the complete public
   request, an execution nonce, package version, and build revision status;
3. `presentation_query_sha256`, separately identifying the unfiltered M6.1
   presentation/query view.

The package version comes from installed metadata. A build revision can be
supplied by `FANTASY_FOOTBALL_BUILD_REVISION` or dependency injection. Packaged
execution works without Git. When no immutable revision is supplied, the public
value is null and status is `unknown`; the service never invents a revision.
An unknown-revision run therefore does not prove source-code byte equivalence.

## Result ownership and cleanup

The synchronous action-search service owns the returned
`SearchOrchestrationResult`. It serializes at most the response row limit inside
a `try` block and always calls `close()` in `finally`, removing the M5.8
temporary SQLite index and sidecars on success or serialization failure. It
does not rely on garbage collection. M6.2 will transfer ownership to a bounded
background-run lifecycle so indexed pages remain available while a run is active.

## Errors and local execution

Public failures use a versioned `{error: {code, category, message, context}}`
envelope. Request-shape, missing-snapshot, unsupported configuration, invalid
scenario, resource, engine-invariant, and unexpected-internal categories remain
distinct. Responses omit tracebacks, filesystem paths, credentials, raw source
payloads, and arbitrary exception objects. Unexpected failures retain logged
exception context and return HTTP 500 rather than masquerading as user errors.

Install and run locally:

```powershell
python -m pip install -e ".[app]"
python -m fantasy_football.app.server --database outputs/fantasy_football.sqlite3 --port 8000
```

The entry point always binds `127.0.0.1`; it offers no public-host flag. CORS is
not used as a network security boundary. M6.3 will perform the broader review.

## M6.1 limits and M6.2 handoff

- All analyses are synchronous and suitable only for bounded local requests.
- No job IDs, polling, cancellation owner, durable run records, search resume,
  WebSockets, or long-lived result index exist.
- Search candidate detail is a compact first page, not a query system.
- HTTP empirical-model evidence selection and explicit postseason ladder
  configuration are not yet exposed; they fail rather than use substitutes.
- FastAPI's test stack emits one upstream AnyIO deprecation warning; it does not
  affect contract behavior.

M6.2 owns bounded background execution, lifecycle/status, cancellation, retained
temporary indexes, pagination/filtering/detail, concurrency, and interruption
cleanup. M6.1 must not be represented as providing those capabilities.

## Verification evidence

- Fourteen focused application tests cover source-derived snapshot structure,
  the accepted SQLite store, exact direct-engine baseline/manual/search parity,
  HTTP serialization, strict OpenAPI contracts, unknown schema/resource
  rejection, explicit build/run identities, incomplete search coverage, safe
  errors, loopback binding, and temporary-index cleanup on success and failure.
- The focused suite passed in 1.38 seconds on the development Windows host. Its
  synthetic one-path HTTP baseline/manual/search parity workflow took 0.22
  seconds; direct baseline, manual, and bounded-search calls each took at most
  0.07 seconds. These tiny sanitized fixtures are contract checks, not realistic
  production-search throughput benchmarks.
- All 812 credential-free repository tests passed in 129.11 seconds.
- Thirty-seven documentation-link/status tests, Python compilation, Ruff
  `F,E9`, dependency consistency, and Git whitespace checks passed.
- One upstream Starlette test-client warning reports a deprecated AnyIO alias;
  no test was skipped and application behavior is unaffected.
