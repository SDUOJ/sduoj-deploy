-- Apply before deploying Run, against the caller-selected database. Safe to resume/reapply.
-- Back up the database before a production migration; production execution is out of this task.
SET @run_schema_sql = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE()
    AND table_name='oj_submission' AND column_name='s_task_results'),
  'SELECT 1',
  'ALTER TABLE oj_submission ADD COLUMN s_task_results MEDIUMBLOB NULL COMMENT ''Run numeric results; formal remains NULL''');
PREPARE run_schema_stmt FROM @run_schema_sql;
EXECUTE run_schema_stmt;
DEALLOCATE PREPARE run_schema_stmt;
SET @run_schema_sql = IF(
  EXISTS(SELECT 1 FROM information_schema.statistics WHERE table_schema=DATABASE()
    AND table_name='oj_submission' AND index_name='idx_run_recovery'),
  'SELECT 1',
  'ALTER TABLE oj_submission ADD INDEX idx_run_recovery (biz_type, s_judge_result, s_gmt_create)');
PREPARE run_schema_stmt FROM @run_schema_sql;
EXECUTE run_schema_stmt;
DEALLOCATE PREPARE run_schema_stmt;
ALTER TABLE oj_submission_extension MODIFY COLUMN se_value MEDIUMTEXT;
-- biz_type 0..3 formal; 100 CASES. Formal scheduling and metrics exclude >=100.
