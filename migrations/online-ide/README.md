# Task and operations migrations

These ten additive migrations cover separate capabilities: Run, context lookup, public-case automation, global submission queries, private outputs, shared provenance, retention, and historical review. Select and review the files for the intended release; local editing and the original formal submission do not require this schema.

The maintained [release and operations guide](../../../OnlineJudge/website/docs/deployment/release-operations.md) describes database ownership, ordering, feature gates, verification and rollback. This directory is the canonical SQL source; application repos must not copy it.

The MySQL test uses an isolated networkless, temporary-data container and verifies repeatability, preserved values and NOT NULL. No production execution is included. Never import a production dump through the local bootstrap path or replace the toolchain producer with consumer-side patches.
