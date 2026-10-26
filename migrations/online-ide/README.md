# Online IDE additive schema

Review these ten migrations with the matching server-private interface/service change. They are copies of the schema verified in the local development environment; apply to the caller-selected problem/filesys database before enabling the new protocol. No production execution is included here.

Order: V20261008__run_task_and_prefix.sql, V20261014__run_request_dedup.sql, V20261014__public_auto_config.sql, V20261014__global_submission_indexes.sql, V20261014__contest_run_context_index.sql, V20261014__run_retention.sql. Apply V20261014__task_output_files.sql to the filesys database. The request table must exist before its retention index is added. Apply V20261015__shared_output_provenance.sql to filesys and V20261015__legacy_output_ledger.sql to problem before deploying the updated promotion/claim protocol. Apply V20261015__legacy_output_clearance.sql to filesys before the optional legacy review workflow. Existing formal result bytes remain unchanged. Repeated application was tested against MySQL in the local development environment.

The Run worker uses a separate queue and sduoj.run.worker=true. Every Snowflake producer needs its own node; all internal callers need a non-empty RPC token. Run task-row and private output retention default off. Enable new creation only after schema, compatible interface artifacts, filesys, context services and the Run worker are ready.

For rollback, disable new creation, drain existing tasks, preserve query/cancel and keep additive schema. Do not delete shared CAS files based only on task age. Unproven historical assets remain retained. Individually reviewed legacy outputs can be reclaimed through the maintenance tool.

The development Dockerfiles are optional overlays and require named build contexts and their base images. compose.run-local.yaml and local Nacos configuration are environment-specific and are not a publishable production configuration.

Shared promotion maintenance is documented in [the operator guide](../../build/sduoj-run/maintenance/README.md). Historical files with incomplete provenance remain protected.
