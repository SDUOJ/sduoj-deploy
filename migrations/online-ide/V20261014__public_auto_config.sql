-- Validator + standard source may each be 64KB; TEXT cannot hold both.
ALTER TABLE oj_problem MODIFY COLUMN p_checker_config MEDIUMTEXT NULL;
