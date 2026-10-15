-- Apply before enabling task retention. Formal rows are never cleanup candidates.
CREATE TABLE IF NOT EXISTS oj_run_cleanup_audit (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    s_id BIGINT NOT NULL,
    p_id BIGINT NOT NULL,
    biz_type INT NOT NULL,
    operator_id BIGINT NULL,
    reason VARCHAR(200) NOT NULL,
    payload_bytes BIGINT NOT NULL,
    retained_file_count INT NOT NULL,
    created_at DATETIME(3) NOT NULL,
    INDEX idx_run_cleanup_created (created_at)
);
SET @retention_index_sql = IF(
  EXISTS(SELECT 1 FROM information_schema.statistics WHERE table_schema=DATABASE()
    AND table_name='oj_submission' AND index_name='idx_task_retention'),
  'SELECT 1',
  'ALTER TABLE oj_submission ADD INDEX idx_task_retention(biz_type,s_gmt_modified,s_id)');
PREPARE retention_index_stmt FROM @retention_index_sql;
EXECUTE retention_index_stmt;
DEALLOCATE PREPARE retention_index_stmt;
SET @retention_index_sql = IF(
  EXISTS(SELECT 1 FROM information_schema.statistics WHERE table_schema=DATABASE()
    AND table_name='oj_run_request' AND index_name='idx_run_request_task'),
  'SELECT 1',
  'ALTER TABLE oj_run_request ADD INDEX idx_run_request_task(s_id,expires_at)');
PREPARE retention_index_stmt FROM @retention_index_sql;
EXECUTE retention_index_stmt;
DEALLOCATE PREPARE retention_index_stmt;
