-- Independent global queries have no biz_id predicate, unlike legacy formal lists.
-- Idempotent: run only against the intended database selected by the caller.
SET @global_index_sql = IF(
  EXISTS(SELECT 1 FROM information_schema.statistics WHERE table_schema=DATABASE()
    AND table_name='oj_submission' AND index_name='idx_global_time'),
  'SELECT 1',
  'ALTER TABLE oj_submission ADD INDEX idx_global_time(s_gmt_create DESC,s_id DESC)');
PREPARE global_index_stmt FROM @global_index_sql;
EXECUTE global_index_stmt;
DEALLOCATE PREPARE global_index_stmt;
SET @global_index_sql = IF(
  EXISTS(SELECT 1 FROM information_schema.statistics WHERE table_schema=DATABASE()
    AND table_name='oj_submission' AND index_name='idx_global_type_time'),
  'SELECT 1',
  'ALTER TABLE oj_submission ADD INDEX idx_global_type_time(biz_type,s_gmt_create DESC,s_id DESC)');
PREPARE global_index_stmt FROM @global_index_sql;
EXECUTE global_index_stmt;
DEALLOCATE PREPARE global_index_stmt;
