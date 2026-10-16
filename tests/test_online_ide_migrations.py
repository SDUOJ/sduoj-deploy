"""Exercise canonical DDL only in an explicit, network-disabled disposable MySQL."""
import json
import os
from pathlib import Path
import subprocess
import unittest
import uuid


class OnlineIdeMigrationsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.container = os.environ.get("SDUOJ_TEST_MYSQL_CONTAINER")
        if not cls.container:
            raise unittest.SkipTest("Set SDUOJ_TEST_MYSQL_CONTAINER to an isolated test container")
        info = json.loads(subprocess.check_output(["docker", "inspect", cls.container]))[0]
        if info["HostConfig"]["NetworkMode"] != "none" or "/var/lib/mysql" not in info["HostConfig"].get("Tmpfs", {}):
            raise RuntimeError("Refusing schema tests outside a network-disabled tmpfs MySQL")
        cls.schema = "sduoj_test_" + uuid.uuid4().hex
        cls.sql("CREATE DATABASE " + cls.schema)

    @classmethod
    def sql(cls, query):
        result = subprocess.run(["docker", "exec", "-i", cls.container, "mysql", "-uroot", "--batch", "--skip-column-names"],
                                input=query, text=True, capture_output=True, check=True)
        return result.stdout.strip()

    @classmethod
    def tearDownClass(cls):
        cls.sql("DROP DATABASE " + cls.schema)

    def test_repeatability_original_data_and_not_null_constraint(self):
        self.sql("USE " + self.schema + "; "
                 "CREATE TABLE oj_submission(s_id BIGINT PRIMARY KEY,biz_type INT,s_judge_result INT,s_gmt_create DATETIME(3),s_gmt_modified DATETIME(3));"
                 "CREATE TABLE oj_submission_extension(se_id BIGINT PRIMARY KEY,se_value TEXT NOT NULL);"
                 "CREATE TABLE oj_problem(p_id BIGINT PRIMARY KEY,p_checker_config TEXT NULL);"
                 "CREATE TABLE oj_contest(ct_id BIGINT PRIMARY KEY,ct_gmt_end DATETIME(3),ct_is_deleted INT,ct_gmt_start DATETIME(3));"
                 "INSERT INTO oj_submission_extension VALUES(1,'original-value');")
        paths = sorted((Path(__file__).resolve().parents[1] / "migrations/online-ide").glob("*.sql"))
        self.assertEqual(len(paths), 10)
        for _ in range(2):
            for path in paths:
                self.sql("USE " + self.schema + ";\n" + path.read_text())
        value = self.sql("SELECT CONCAT(DATA_TYPE,':',IS_NULLABLE) FROM information_schema.columns "
                         "WHERE TABLE_SCHEMA='" + self.schema + "' AND TABLE_NAME='oj_submission_extension' AND COLUMN_NAME='se_value'")
        self.assertEqual(value, "mediumtext:NO")
        self.assertEqual(self.sql("USE " + self.schema + "; SELECT se_value FROM oj_submission_extension WHERE se_id=1"), "original-value")
        with self.assertRaises(subprocess.CalledProcessError):
            self.sql("USE " + self.schema + "; INSERT INTO oj_submission_extension VALUES(2,NULL)")


if __name__ == "__main__":
    unittest.main()
