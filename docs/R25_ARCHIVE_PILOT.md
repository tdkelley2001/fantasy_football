# R2.5 historical audit archive pilot

Baseline: independently accepted R2.4 `05165a8fbf4084fc9c2d56780335581c65006657` ([PR #118](https://github.com/tdkelley2001/fantasy_football/pull/118)). Scope is the explicitly authorized two-document WR-002 pilot, under [standing rules](../AGENTS.md), [verification guidance](development/verification.md) and the unchanged [R1 inventory](R1_REPOSITORY_AUDIT.md#7-file-by-file-documentation-migration-map). R2.5 awaits independent review. Relocation does not supersede analytical requirements, historical gates, findings or evidence.

## Files and evidence preservation

| Original path (retained compatibility page) | Complete historical record | Original heading anchors |
|---|---|---|
| [PRE_M3_REPOSITORY_AUDIT.md](PRE_M3_REPOSITORY_AUDIT.md) | [archive/audits/PRE_M3_REPOSITORY_AUDIT.md](archive/audits/PRE_M3_REPOSITORY_AUDIT.md) | 13, including the title. |
| [PRE_M4_INTEGRATION_AUDIT.md](PRE_M4_INTEGRATION_AUDIT.md) | [archive/audits/PRE_M4_INTEGRATION_AUDIT.md](archive/audits/PRE_M4_INTEGRATION_AUDIT.md) | 11, including the title. |

The archived bodies match the accepted R2.4 originals **in full**, not summaries. Only a separated archival notice and one reviewed Markdown link rebase are allowed. Baseline revisions, measurements, caveats, findings and recommendations remain verbatim, including the pre-M4 correction requiring the reusable executor to check both seed-independent configuration and seed-bearing run identity before dispatch. Its adversarial regression, deterministic path/aggregate significance, acceptance and 103/619-test evidence remain intact. Old provisional/deferred statements retain their historical context rather than becoming current instructions.

## Inbound reference audit

Ran `git grep -n -I -E 'PRE_M[34]_(REPOSITORY|INTEGRATION)_AUDIT(\.md)?' 05165a8fbf4084fc9c2d56780335581c65006657 -- .` over all tracked repository text, covering Markdown, inline-code/plain filenames, source, scripts and tests. This found six matching lines in five files:

| Referencer | Purpose and disposition |
|---|---|
| `docs/index.md` | Current historical-record navigation: link directly to full archive copies. Current architecture/verification references stay primary. |
| `docs/MASTER_SPEC.md` | Pre-M4 accepted consolidation citation in inline code: retain original referent/path and all wording; compatibility page links to the full record. |
| `docs/ROADMAP.md` | Pre-M4 acceptance/gate citation as a plain filename: retain verbatim. |
| `docs/R1_REPOSITORY_AUDIT.md` | Two original-path inventory entries and proposed earlier destinations: retain the accepted inventory unchanged. R2.5's explicit destination takes precedence for this pilot only. |
| `docs/development/verification.md` | R2.4 proposal uses original paths in code formatting: preserve proposal text with a separated follow-through pointer. |

The table covers all five referencers (the R1 map contributes two matching lines). Existing tests indirectly check all 56 R1 inventory paths; they still resolve through the compatibility pages. No literal inbound references appeared in baseline production source, scripts, README or tests. The pilot adds explicit test references and this record; it does not automatically replace historical citations. External links/bookmarks cannot be inventoried completely, so both original paths and all original headings are retained.

## Heading and outbound-link handling

Compatibility pages repeat exactly the original ATX heading text, level and order, including the title, and put only a deep link beneath each historical section. They add no new headings. This preserves GitHub's automatically generated anchor sequence; they do not rely on a redirect that would lose fragments. All 24 original anchors remain available at both old and new paths, with deep links to the corresponding full sections.

[GitHub's section-link rules](https://docs.github.com/en/get-started/writing-on-github/getting-started-with-writing-and-formatting-on-github/basic-writing-and-formatting-syntax#section-links) specify lowercase/punctuation/space handling and incrementing suffixes for duplicate IDs. Both actual audits use plain ASCII headings and have no duplicates or fenced code; tests compare complete ordered heading/anchor sequences and separately exercise repeated headings plus a heading already ending in `-1`. This is a bounded check for these documents, not a general Markdown renderer. Adding/reordering a heading in a compatibility page could break bookmarks and must be reviewed against the preserved sequence.

Pre-M3 has one relative Markdown link: `LEAGUE_CONFIGURATION_AUDIT.md` becomes `../../LEAGUE_CONFIGURATION_AUDIT.md`. Pre-M4 has no original Markdown outbound links. Inline module/file names and historical references remain literal evidence, not newly invented links. New archive notices point two levels up to current architecture/verification. Neither audit has linked images or JSON assets; no other asset is moved or deleted. No new archive index is needed for two files: the existing documentation index links them directly.

## Verification and limitations

[Focused tests](../tests/test_archive_pilot.py) read the exact accepted R2.4 Git objects, compare full archive text allowing only the fixed notice/link rebase, compare ordered original/compatibility/archive headings and anchors, resolve inbound fragments and outbound links, preserve complete specification/roadmap/R1 text, and check every baseline tracked path remains accessible. The accepted baseline object must be available locally; an absent shallow-history object fails explicitly rather than skipping preservation. Fetching history is a separate contributor action, not an automatic network operation in tests.

Executed `.venv\Scripts\python.exe -m pytest tests/test_archive_pilot.py tests/test_documentation_links.py tests/test_contributor_documentation.py tests/test_technical_documentation.py tests/test_repository_security.py tests/test_release_verification.py -q -p no:cacheprovider --tb=short`: **146 passed**, one existing Starlette/AnyIO deprecation warning. Existing documentation, security and release-marker checks remain enabled; original R1 inventory assertions are unchanged. Release-marker checks inspect test definitions without executing real process tests.

Ruff check/format for the focused archive and contributor-documentation tests, plus `git diff --check HEAD`, pass. Full baseline text comparison confirms `MASTER_SPEC.md`, `ROADMAP.md` and the R1 inventory are unchanged; all preexisting tracked paths remain accessible. Production source, scripts, frontend, dependencies/configuration, existing engine/golden tests and historical assets remain unchanged. No deleted files or additional archived records are present in the pilot diff.

No production behavior, engine tests, numerical identities, WR-022 policy, API/schema/storage/configuration/dependency or GitHub infrastructure changes are part of this pilot. No live ESPN, private database, process recovery, browser or full numerical regression is run. Tests establish repository content/link/anchor preservation, not a newly executed GitHub/browser-rendering or external-bookmark test.

## Pilot findings and next candidate

Reusable steps: inspect the accepted baseline; search tracked text including non-Markdown references; classify navigation versus historical/gate citations; preserve old-path entry points; compare full evidence; rebase only reviewed links; verify every heading/fragment and inspect Git's final scope. Document-specific work remains essential: relative bases, heading collisions/formatting, assets, embedded code paths, temporal claims and binding gates cannot be migrated by blind global replacement.

No content-preservation problem has been found in this pilot; the link rebase and compatibility headings are the expected relocation differences. Git may display these as additions plus compatibility-page edits rather than detecting a move, so rename detection is not preservation evidence. Checks use the complete baseline bodies instead. Renderer behavior/external bookmarks still merit independent navigation review; automated checks do not claim a newly executed browser rendering test.

Recommended next **candidate for separately authorized discovery**: `POST_M5_CONSOLIDATION_AUDIT.md` alone. It is classified historical in the R1 map, but its current-contract references and application-handoff boundaries need a fresh inbound/outbound/gate inventory before any move. Do not infer that this pilot approves it or any other archive group. Asset-heavy UI records and mixed live/current contracts should wait for document-specific plans. No further migration is begun.
