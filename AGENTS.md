# Standing Development Instructions

These rules apply to all future work in this repository. The approved requirements in `docs/MASTER_SPEC.md` are authoritative; `docs/ROADMAP.md` defines delivery order and gates.

## Scope and sequencing

1. Implement from the specification, not from memory, prior code, or convenience. Cite the governing specification section in each task or pull request.
2. Preserve a clean-sheet architecture. Legacy code is historical reference only and must not shape interfaces or behavior merely because it exists.
3. Work in small, independently testable tasks. Do not combine roadmap packages unless their interfaces and acceptance gates have already been verified.
4. Respect milestone dependencies and statuses. Never mark a task or milestone complete until its documented acceptance gate passes with inspectable evidence.
5. Do not begin a milestone or work package without the required review or approval.
6. Inspect existing modules before adding new ones. Reuse established configuration, authentication, logging, error handling, and validation; extract shared infrastructure only after multiple tasks demonstrate a real need.
7. Avoid premature frameworks, unnecessary abstractions, and architectural changes unrelated to the assigned work package.

## Correctness rules

1. Fail fast on invalid, missing, ambiguous, or structurally inconsistent inputs. Errors must identify the violated invariant and relevant snapshot, transaction, team, player, configuration, or work step.
2. Do not introduce fallback behavior, guessed rules, substitute data, catch-and-continue paths, implicit corrections, or default league mechanics unless the specification explicitly approves and documents them.
3. Exhaustive search means complete enumeration of the explicitly selected finite universe, constrained only by real legality, structural feasibility, and approved model constraints. Optional pruning must be independently disableable and disclose lost coverage.
4. Partial or resource-capped work must report exact coverage and incomplete convergence. Never label a partial search exhaustive.
5. Monte Carlo results must be reproducible from recorded snapshots, configuration, code version, seed, and path definition. Results must remain equivalent across supported worker counts, batching, checkpoint/resume, and generation order.
6. Maintain a simple reference implementation as the correctness oracle. Optimized implementations must prove equivalence for feasible sequences, final states, and path-indexed outputs before promotion.

## Testing and evidence

1. Define each task's input contract, output artifact, invalid-input behavior, and acceptance test before implementation.
2. Add focused unit tests plus negative and adversarial tests that attempt to break invariants. Do not make unexpected cases unreachable merely to satisfy a test.
3. Use hand-checkable fixtures for exhaustive enumeration and deterministic season behavior. Use seeded fixtures and cross-worker comparisons for probabilistic behavior.
4. Benchmark before adding complex optimizations. Record correctness equivalence, runtime, memory, environment, and limitations.
5. Keep provisional methods visibly provisional. Do not describe an algorithm, data source, ESPN field, or milestone as verified without source evidence and passing tests.
6. Prefer representative sanitized fixtures. Assert precise failure behavior and messages, not merely that some exception occurred.
7. Mock and synthetic tests establish code behavior only; they never prove a live ESPN field or API behavior exists.

## ESPN evidence and provenance

1. For every investigated ESPN field, record the raw endpoint and field, any `espn-api` transformation, any repository transformation, the verification method, and known limitations.
2. Classify findings exactly as **Verified live**, **Verified by tests**, **Unverified**, or **Unsupported**.
3. Keep missing values distinct from explicit zeros. Detect truncated pagination and incomplete multi-request retrieval; never substitute a default for absent or inconsistent data.
4. Validate identifiers and relationships across responses. Record retrieval context sufficient to identify observations that may have changed between requests.
5. Record library defects and unsupported assumptions explicitly. Do not quietly compensate with new modeling rules.
6. Each ESPN discovery task must report implementation, live evidence, test-only evidence, library/API limitations, uncertainties, tests and results, and any recommended architecture change.
7. Do not introduce or implement a new modeling assumption without explicit approval.
8. Discover league settings dynamically and derive supported behavior from the retrieved configuration. Never use this league's team count, roster slots, playoff field, byes, round lengths, divisions, IR/flex presence, or consolation format as a universal validation template. Separate structurally invalid data from valid-but-unsupported semantics.

## Change discipline

1. Keep the engine independent of presentation and network retrieval. Preserve immutable snapshot and provenance boundaries defined by the specification.
2. Never commit credentials, cookies, tokens, private league data, or sensitive values. Use ignored local configuration and sanitized fixtures.
3. Do not silently change approved modeling requirements. Propose specification changes explicitly, document the rationale, and obtain approval before implementation.
4. Update the authoritative documentation when approved behavior changes. A code change that contradicts the specification is incomplete.
5. Leave the repository runnable and reviewable after each increment; include the smallest relevant verification evidence in the commit or pull request.
