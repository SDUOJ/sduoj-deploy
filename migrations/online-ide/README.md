# Task and operations migrations

These ten additive migrations cover separate capabilities: Run, context lookup, public-case automation, global submission queries, private outputs, shared provenance, retention, and historical review. Select the files required by the release after inspecting the target schema; local editing and the original formal submission do not require this schema.

The internal [release and operations guide](../../../docs/maintenance/release-operations.md) defines database ownership, ordering, feature gates and rollback. This directory is the canonical SQL source. Preserve the existing `se_value NOT NULL` constraint; repeatable ALTER still needs a measured lock and runtime budget.

The MySQL regression uses an isolated temporary-data container and checks repeatability, preserved values and constraints. It does not execute production migrations. Never import a production dump through the local bootstrap path or replace the toolchain producer with consumer-side patches.
