SET @contest_context_index_sql = IF(
  EXISTS(SELECT 1 FROM information_schema.statistics WHERE table_schema=DATABASE()
    AND table_name='oj_contest' AND index_name='idx_contest_run_window'),
  'SELECT 1',
  'ALTER TABLE oj_contest ADD INDEX idx_contest_run_window(ct_gmt_end,ct_is_deleted,ct_gmt_start)');
PREPARE contest_context_index_stmt FROM @contest_context_index_sql;
EXECUTE contest_context_index_stmt;
DEALLOCATE PREPARE contest_context_index_stmt;
