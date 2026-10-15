-- Filesys database: task-private generated output metadata, separate from durable oj_file.
-- Apply before deploying the updated filesys worker upload protocol; safe to apply twice.
CREATE TABLE IF NOT EXISTS oj_task_output_file (
    f_id BIGINT NOT NULL PRIMARY KEY,
    task_id BIGINT NOT NULL,
    task_version INT NOT NULL,
    case_index INT NOT NULL,
    byte_size INT NOT NULL,
    sha256 CHAR(64) NOT NULL,
    created_at DATETIME(3) NOT NULL,
    UNIQUE KEY uk_task_output_case (task_id, task_version, case_index),
    KEY idx_task_output_retention (created_at, f_id)
);
CREATE TABLE IF NOT EXISTS oj_task_output_cleanup_audit (
    f_id BIGINT NOT NULL PRIMARY KEY,
    task_id BIGINT NOT NULL,
    byte_size INT NOT NULL,
    deleted_at DATETIME(3) NOT NULL,
    KEY idx_task_output_audit_time (deleted_at)
);
