-- Filesys database. Apply before deploying shared-output promotion / ordinary-asset claims.
-- Allocations are durable before any physical or checkpoint writes. Normal claims never expire.
CREATE TABLE IF NOT EXISTS oj_shared_task_output (
    source_file_id BIGINT NOT NULL PRIMARY KEY,
    f_id BIGINT NOT NULL,
    task_id BIGINT NOT NULL,
    case_index INT NOT NULL,
    expected_name VARCHAR(255) NOT NULL,
    byte_size INT NOT NULL,
    md5 CHAR(32) NOT NULL,
    user_id BIGINT NOT NULL,
    origin VARCHAR(20) NOT NULL,
    state VARCHAR(20) NOT NULL DEFAULT 'READY',
    created_at DATETIME(3) NOT NULL,
    UNIQUE KEY uk_shared_output_id (f_id),
    KEY idx_shared_output_retention (state, created_at, f_id)
);
CREATE TABLE IF NOT EXISTS oj_file_asset_claim (
    f_id BIGINT NOT NULL PRIMARY KEY,
    reason VARCHAR(40) NOT NULL,
    created_at DATETIME(3) NOT NULL
);
CREATE TABLE IF NOT EXISTS oj_shared_output_cleanup_audit (
    f_id BIGINT NOT NULL PRIMARY KEY,
    task_id BIGINT NOT NULL,
    byte_size INT NOT NULL,
    origin VARCHAR(20) NOT NULL,
    state VARCHAR(20) NOT NULL,
    prepared_at DATETIME(3) NOT NULL,
    completed_at DATETIME(3) NULL,
    reason VARCHAR(200) NOT NULL
);
