-- Filesys database. Individual content-bound review of proven legacy task output only.
-- A filename or missing database reference never creates a clearance automatically.
CREATE TABLE IF NOT EXISTS oj_legacy_output_clearance (
    f_id BIGINT NOT NULL PRIMARY KEY,
    task_id BIGINT NOT NULL,
    case_index INT NOT NULL,
    expected_name VARCHAR(255) NOT NULL,
    expected_features TEXT NOT NULL,
    byte_size INT NOT NULL,
    md5 CHAR(32) NOT NULL,
    sha256 CHAR(64) NOT NULL,
    user_id BIGINT NOT NULL,
    snapshot_sha256 CHAR(64) NOT NULL,
    review_sha256 CHAR(64) NOT NULL,
    reviewed_by VARCHAR(100) NOT NULL,
    review_reason VARCHAR(200) NOT NULL,
    reviewed_at DATETIME(3) NOT NULL
);
