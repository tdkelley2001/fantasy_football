# Immutable SQLite Snapshot Storage

## Status and authority

M1.3 is complete. `fantasy_football.snapshot_store` persists validated M1.2 adapter results in one private local SQLite database. The exact deterministic canonical JSON bytes are the sole authoritative normalized snapshot representation. SQL does not duplicate teams, players, player-weeks, rosters, rules, or matchups as competing authoritative records.

Canonical document schema version and database schema version are independent. The current supported versions are canonical schema **2** and SQLite schema **1**. Unsupported versions fail explicitly; the store does not silently migrate or rewrite documents.

## Database schema

| Table | Purpose and key |
|---|---|
| `store_metadata` | Key/value database metadata, including `database_schema_version=1` |
| `snapshots` | One row per publication UUID; league/season, canonical version, retrieval/publication UTC timestamps, canonical SHA-256/length, and expected raw-source count |
| `canonical_documents` | Exactly one canonical JSON BLOB per `snapshot_id`, enforced by primary/foreign key |
| `raw_responses` | One compressed captured response per `(snapshot_id, source_id)`, including request role, endpoint/view, sanitized parameters, retrieval UTC time, representation, uncompressed length/checksum, compression, and payload |

Indexes support deterministic newest selection by `(league_id, season, published_at_utc DESC, snapshot_id DESC)` and source lookup by snapshot. Foreign keys are enabled on every repository connection. Update and delete triggers reject mutation of published snapshot, canonical-document, and source-evidence rows. No deletion or retention API exists in M1.3.

## Identity, serialization, and checksums

Each publication attempt that reaches persistence receives a newly generated UUID. It is not derived from content, so identical refreshes remain separately retained. The UUID is applied immutably to the final `LeagueSnapshot`; that identified snapshot is validated and serialized with the schema-v2 serializer before the write transaction. SHA-256 covers the exact UTF-8 canonical JSON bytes, including the UUID.

The canonical serializer determines collection and key ordering. Persistence decodes and re-encodes the prepared document before publication to prove deterministic byte round-tripping. Retrieval and publication timestamps remain distinct, and publication cannot precede retrieval completion.

M1.2 captures parsed JSON mappings, not literal HTTP wire bodies. M1.3 therefore stores a deterministic compact UTF-8 JSON representation (`deterministic_json_utf8`) of each mapping. Its SHA-256 must equal both the captured-response digest and canonical `SourceReference` digest. The byte representation is gzip-compressed at level 9 with deterministic `mtime=0`; compression/decompression and byte equality are checked before opening the transaction. No claim is made that these bytes equal ESPN's HTTP wire encoding.

## Atomic publication and rollback

The lifecycle is:

1. M1.2 finishes all sequential ESPN retrieval and mutable-state reconciliation.
2. M1.3 assigns a UUID, validates the identified canonical snapshot, serializes it, reconciles every required source/reference, checks deterministic raw bytes and digests, and compresses/decompresses all sources in memory.
3. The repository opens SQLite, validates database schema 1, and begins `BEGIN IMMEDIATE`.
4. It inserts snapshot metadata, the complete canonical document, and all raw responses.
5. It commits only after every insert succeeds. Any exception invokes rollback and is reported as failure.

No ESPN request occurs inside the transaction. A failed candidate never replaces, hides, or modifies a previously committed snapshot. Tests force failure after multiple inserts and verify that the new UUID is absent while the prior snapshot remains byte-for-byte unchanged. SQLite uses WAL journal mode with `synchronous=FULL`; standard SQLite commit, rollback, and crash recovery are authoritative rather than a custom staging service.

## Read-time integrity verification

`SnapshotStore.load(snapshot_id)` verifies:

- database and canonical schema versions;
- one metadata row and one canonical document;
- canonical byte length and SHA-256;
- canonical deserialization and full validation;
- UUID, league, season, schema, and retrieval-time agreement between metadata and document;
- exact required raw-source IDs and count;
- supported encoding and compression;
- successful gzip decompression;
- uncompressed source length and SHA-256;
- source checksum and request metadata agreement with canonical provenance; and
- valid JSON payload and sanitized parameter metadata.

`verify()` performs the full path. `newest_metadata()` returns only metadata and uses publication time followed by UUID as an explicit tie-breaker. M1.5 will add user-facing listing and inspection; M1.3 exposes only the minimal internal publish/load/newest/verify operations.

## Retention, configuration, and security

Every committed snapshot is retained indefinitely by default, even when content resembles an earlier refresh. There is no automatic cleanup, rolling retention, deduplication, or update API.

`SNAPSHOT_DB_PATH` defaults to `outputs/fantasy_football.sqlite3`; callers may pass another local path explicitly. `.gitignore` excludes SQLite, DB, WAL, and SHM artifacts. Raw payloads contain private league information, so the database is a private local artifact. Credentials, cookies, tokens, and headers are neither accepted as stored request metadata nor written by the adapter.

## Verification evidence and limitations

Credential-free fixtures verify successful publish/reopen/round-trip, raw missing/zero/positive/negative projections, signed IDs, raw enums, structured rule evidence, observed slot 25, complete source retention, checksums, multiple retained refreshes, deterministic newest selection, cross-connection visibility, rollback before commit, forced mid-insert failure, duplicate UUID rejection, immutable-row triggers, corrupted canonical/source bytes, and unsupported schema versions.

The complete credential-free repository suite passed **210 tests**. The bounded authenticated smoke test retrieved the already accepted live league horizon, published a new UUID to an ignored temporary database, closed and reopened it, then verified a 3,845,168-byte canonical document, 1,052 players, 11,572 player-weeks, observed eligibility slot 25, and all 63 captured source responses. The private temporary database was removed after verification and was not committed.

M1.3 does not implement migrations, snapshot deletion, a listing UI/CLI, relational analytical queries, simulation compilation, background refresh, or scheduled collection.
