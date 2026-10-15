-- Problem database. Preserve attributable legacy generated IDs before deleting old reports.
-- A report ID alone is not proof of exclusive ownership: maintenance must still check references.
CREATE TABLE IF NOT EXISTS oj_run_legacy_output (
    f_id BIGINT NOT NULL,
    task_id BIGINT NOT NULL,
    case_index INT NOT NULL,
    recorded_at DATETIME(3) NOT NULL,
    PRIMARY KEY (f_id,task_id),
    KEY idx_legacy_output_task (task_id)
);
