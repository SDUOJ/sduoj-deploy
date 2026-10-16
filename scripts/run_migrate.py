"""Apply the canonical, ordered migrations to this local development database."""
import subprocess
import dev


def migrate_run():
    result = dev.mysql("mysql", "SELECT COUNT(*) FROM information_schema.tables "
                       "WHERE table_schema=DATABASE() AND table_name IN "
                       "('oj_submission','oj_submission_extension','oj_problem','oj_contest');",
                       stdout=subprocess.PIPE)
    if result.stdout.decode().splitlines()[-1] != "4":
        raise RuntimeError("Install the approved base application schema before task migrations; "
                           "Nacos initdb is not the application schema")
    paths = sorted((dev.ROOT / "migrations/online-ide").glob("*.sql"))
    if not paths:
        raise RuntimeError("No canonical task migrations found")
    for path in paths:
        dev.mysql("mysql", path.read_text())
        print("Applied local migration " + path.name, flush=True)


if __name__ == "__main__":
    dev.initialize()
    migrate_run()
