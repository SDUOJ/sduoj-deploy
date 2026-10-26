#!/usr/bin/env python3
"""Conservative offline CAS collection. Read-only unless --execute --writers-stopped.

Config: {"filesysRoot": "/mount", "instances": [{"host":..., "port":3306,
"user":..., "passwordEnv":"MYSQL_PASSWORD", "schemas": {"filesys":"oj",
"problem":"oj", "autolab":"autolab"}}]}. All three roles are required.
Never print credentials or row contents. Requires PyMySQL and MySQL 8.
"""
from __future__ import annotations
import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct

SELF_TABLES = {"oj_shared_task_output", "oj_shared_output_cleanup_audit", "oj_file_asset_claim",
               "oj_run_legacy_output", "oj_task_output_file", "oj_task_output_cleanup_audit", "oj_legacy_output_clearance"}
MUTABLE = {"oj_shared_task_output", "oj_shared_output_cleanup_audit", "oj_file", "oj_legacy_output_clearance"}
NUMERIC = {"bigint", "int", "smallint", "mediumint", "tinyint", "decimal", "numeric", "float", "double"}
TEXT = {"char", "varchar", "tinytext", "text", "mediumtext", "longtext", "json", "enum", "set"}
BINARY = {"binary", "varbinary", "tinyblob", "blob", "mediumblob", "longblob"}
IGNORED = {"date", "datetime", "timestamp", "time", "year", "bit"}


def ident(value):
    if not re.fullmatch(r"[A-Za-z0-9_$]+", value):
        raise ValueError("Unsupported SQL identifier")
    return "`" + value + "`"


def jump(key):
    b, j = -1, 0
    while j < 1024 * 1024:
        b = j
        key = (key * 2862933555777941757 + 1) & ((1 << 64) - 1)
        j = int((b + 1) * ((1 << 31) / ((key >> 33) + 1)))
    return b


def cas_relative(fid):
    # Legacy LocalFileResolver uses the boxed Long/Object overload, hence Long.hashCode.
    key = (fid ^ (fid >> 32)) & 0xffffffff
    if key >= (1 << 31):
        key -= 1 << 32
    bucket = jump(key)
    return Path(str(bucket // 1024), str(bucket % 1024), str(fid))


def binary_needles(fid):
    return [str(fid).encode(), format(fid, "x").encode(), struct.pack(">Q", fid), struct.pack("<Q", fid)]


class Store:
    def __init__(self, connection, schemas):
        self.db, self.schemas, self.tables = connection, schemas, {}

    def query(self, sql, args=()):
        with self.db.cursor() as cursor:
            cursor.execute(sql, args)
            return cursor.fetchall()

    def update(self, sql, args=()):
        with self.db.cursor() as cursor:
            cursor.execute(sql, args)
            return cursor.rowcount

    def inventory(self):
        names = sorted(set(self.schemas.values()))
        marks = ",".join(["%s"] * len(names))
        tables = self.query("SELECT TABLE_SCHEMA,TABLE_NAME,TABLE_TYPE FROM information_schema.tables "
                            f"WHERE TABLE_SCHEMA IN ({marks})", names)
        # Unknown views and column types fail closed, rather than silently omitting references.
        if any(row["TABLE_TYPE"] != "BASE TABLE" for row in tables):
            raise ValueError("Views require an explicit reference audit")
        result = {(r["TABLE_SCHEMA"], r["TABLE_NAME"]): [] for r in tables}
        for col in self.query("SELECT TABLE_SCHEMA,TABLE_NAME,COLUMN_NAME,DATA_TYPE FROM information_schema.columns "
                              f"WHERE TABLE_SCHEMA IN ({marks})", names):
            if col["DATA_TYPE"] not in NUMERIC | TEXT | BINARY | IGNORED:
                raise ValueError("Unsupported reference column type")
            result[(col["TABLE_SCHEMA"], col["TABLE_NAME"])].append((col["COLUMN_NAME"], col["DATA_TYPE"]))
        return result

    def lock(self):
        self.tables = self.inventory()
        clauses = []
        for schema, table in sorted(self.tables):
            mode = "WRITE" if schema == self.schemas.get("filesys") and table in MUTABLE else "READ"
            clauses.append(f"{ident(schema)}.{ident(table)} {mode}")
        if not clauses:
            raise ValueError("Empty application database inventory")
        self.update("LOCK TABLES " + ",".join(clauses))
        if self.inventory() != self.tables:
            raise ValueError("Schema changed during lock acquisition")

    def refs(self, fid):
        for (schema, table), columns in self.tables.items():
            if table in SELF_TABLES:
                continue
            conditions, values = [], []
            for col, kind in columns:
                if table == "oj_file" and col == "f_id":
                    continue
                c = ident(col)
                if kind in NUMERIC:
                    conditions.append(f"{c}=%s"); values.append(fid)
                elif kind in TEXT:
                    conditions.append(f"({c} LIKE %s OR {c} LIKE %s)")
                    values += ["%" + str(fid) + "%", "%" + format(fid, "x") + "%"]
                elif kind in BINARY:
                    for needle in binary_needles(fid):
                        conditions.append(f"LOCATE(%s,{c})>0"); values.append(needle)
            if conditions and self.query(f"SELECT 1 FROM {ident(schema)}.{ident(table)} WHERE " +
                                         " OR ".join(conditions) + " LIMIT 1", values):
                return f"reference:{schema}.{table}"
        return None

    def source_exists(self, task):
        schema = self.schemas.get("problem")
        if not schema:
            return False
        return bool(self.query(f"SELECT 1 FROM {ident(schema)}.oj_submission WHERE s_id=%s LIMIT 1", (task,)))

    def table(self, role, table):
        schema = self.schemas[role]
        if (schema, table) not in self.tables:
            raise ValueError("Required lifecycle table missing")
        return f"{ident(schema)}.{ident(table)}"


def protected_reason(stores, candidate, now, minimum_days, legacy_approved=False):
    if candidate["state"] not in {"READY", "DELETING"}:
        return "retired"
    if (candidate["origin"] != "PROMOTION" and not legacy_approved) or not 0 <= candidate["case_index"] <= 19:
        return "unproven-origin"
    if not 0 <= candidate["byte_size"] <= 65536 or candidate["f_id"] <= 0 or candidate["task_id"] <= 0:
        return "invalid-provenance"
    if candidate["expected_name"] not in ([f'{candidate["task_id"]:x}-{candidate["case_index"]}.out', f'auto-{candidate["task_id"]}-{candidate["case_index"]}.out'] if legacy_approved else [f'{candidate["task_id"]:x}-{candidate["case_index"]}.out']):
        return "invalid-name"
    if candidate["created_at"] > now - dt.timedelta(days=minimum_days):
        return "recent"
    for store in stores:
        if store.source_exists(candidate["task_id"]):
            return "source-retained"
        refs = store.refs(candidate["f_id"])
        if refs:
            return refs
    return None


@contextlib.contextmanager
def parent_fd(root, fid):
    # Resolve the operator-selected parent once; do not follow a linked storage root/bucket.
    root = Path(root).absolute()
    if root.is_symlink():
        raise ValueError("Linked storage root")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fds = [os.open(root, flags)]
    try:
        rel = cas_relative(fid)
        for component in rel.parts[:-1]:
            fds.append(os.open(component, flags, dir_fd=fds[-1]))
        yield fds[-1], rel.name
    finally:
        for fd in reversed(fds):
            os.close(fd)


def verify_physical(fd, name, candidate, recovering=False):
    try:
        filefd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
    except FileNotFoundError:
        if recovering:
            return None
        raise ValueError("Missing unaudited file")
    with os.fdopen(filefd, "rb") as stream:
        status = os.fstat(stream.fileno())
        if not stat.S_ISREG(status.st_mode) or status.st_nlink != 1 or status.st_size != candidate["byte_size"]:
            raise ValueError("Invalid shared file type, size or links")
        raw = stream.read(65537)
    if len(raw) != candidate["byte_size"] or hashlib.md5(raw).hexdigest() != candidate["md5"]:
        raise ValueError("Shared file digest differs")
    return status


def collect(stores, filesys, root, execute, now, days, limit, reason, after=0):
    ledger = filesys.table("filesys", "oj_shared_task_output")
    claims = filesys.table("filesys", "oj_file_asset_claim")
    metadata = filesys.table("filesys", "oj_file")
    audit = filesys.table("filesys", "oj_shared_output_cleanup_audit")
    # SQL-bound batch; inspect all persisted application columns for each selected candidate.
    candidates = filesys.query(f"SELECT * FROM {ledger} WHERE state IN ('READY','DELETING') "
                               "AND created_at<%s AND f_id>%s ORDER BY f_id LIMIT %s",
                               (now - dt.timedelta(days=days), after, limit))
    results = []
    for item in candidates:
        fid, task = item["f_id"], item["task_id"]
        result = {"fileId": str(fid), "taskId": str(task)}
        try:
            legacy = None
            if item["origin"] == "LEGACY":
                import legacy_output_review
                legacy = legacy_output_review.clearance(filesys,item)
            hold = protected_reason(stores, item, now, days, legacy is not None)
            if filesys.query(f"SELECT 1 FROM {claims} WHERE f_id=%s", (fid,)):
                hold = "ordinary-asset-claim"
            rows = filesys.query(f"SELECT * FROM {metadata} WHERE f_id=%s", (fid,))
            if rows:
                meta = rows[0]
                if (meta["f_features"] != (legacy["expected_features"] if legacy else f"task-generated:{task}") or meta["u_id"] != item["user_id"] or
                        meta["f_name"] != item["expected_name"] or meta["f_size"] != item["byte_size"] or
                        meta["f_md5"] != item["md5"] or (meta["f_is_deleted"] != 0 and item["state"] != "DELETING")):
                    hold = "metadata-provenance-mismatch"
            previous = filesys.query(f"SELECT * FROM {audit} WHERE f_id=%s", (fid,))
            recovering = bool(previous) and previous[0]["state"] in {"DELETING", "DELETED"} and all(
                previous[0][key] == item[key] for key in ("f_id", "task_id", "byte_size", "origin"))
            if (item["state"] == "DELETING" or previous) and not recovering:
                hold = "unproven-recovery"
            if hold:
                result["status"] = hold
            else:
                # All instances remain table-locked until every filesystem deletion finishes.
                if any(store.inventory() != store.tables for store in stores):
                    raise ValueError("Application schema changed")
                with parent_fd(root, fid) as (fd, name):
                    status = verify_physical(fd, name, item, recovering)
                    if legacy and status is not None:
                        with os.fdopen(os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd), "rb") as stream:
                            if hashlib.sha256(stream.read(65537)).hexdigest() != legacy["sha256"]:
                                raise ValueError("Legacy content differs from reviewed digest")
                    if not execute:
                        result["status"] = "eligible-preview"
                    else:
                        # autocommit is mandatory: durable preparation survives a process crash.
                        if not recovering:
                            filesys.update(f"INSERT INTO {audit}(f_id,task_id,byte_size,origin,state,prepared_at,reason) "
                                           "VALUES(%s,%s,%s,%s,'DELETING',%s,%s)",
                                           (fid, task, item["byte_size"], item["origin"], now, "legacy-review:"+legacy["review_sha256"] if legacy else reason))
                            filesys.update(f"UPDATE {ledger} SET state='DELETING' WHERE f_id=%s", (fid,))
                        if status is not None:
                            current = os.stat(name, dir_fd=fd, follow_symlinks=False)
                            if (current.st_dev, current.st_ino, current.st_size) != (status.st_dev, status.st_ino, status.st_size):
                                raise ValueError("Shared file changed")
                            os.unlink(name, dir_fd=fd)
                        # Reserved IDs also own their interrupted atomic-write parts.
                        pattern = re.compile(rf"\.{fid}\.promotion-[0-9a-f-]{{36}}\.part")
                        for entry in os.listdir(fd):
                            if pattern.fullmatch(entry):
                                os.unlink(entry, dir_fd=fd)
                        filesys.update(f"UPDATE {metadata} SET f_is_deleted=1,f_gmt_modified=%s WHERE f_id=%s", (now, fid))
                        filesys.update(f"UPDATE {audit} SET state='DELETED',completed_at=%s WHERE f_id=%s", (now, fid))
                        filesys.update(f"UPDATE {ledger} SET state='DELETED' WHERE f_id=%s", (fid,))
                        result["status"] = "deleted" if status is not None else "recovered-deletion"
        except Exception as error:
            result["status"] = "retained-error"
            result["errorType"] = type(error).__name__
        results.append(result)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--legacy-report", type=Path, help="Write a read-only legacy survey Markdown + JSON")
    parser.add_argument("--legacy-reviewed", type=Path, help="Install individually reviewed, digest-bound legacy clearances")
    parser.add_argument("--writers-stopped", action="store_true")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--after", type=int, default=0, help="Last scanned file ID; reset to 0 after a full pass")
    parser.add_argument("--reason", default="offline shared output retention")
    args = parser.parse_args()
    if args.after < 0 or not 30 <= args.days <= 3650 or not 1 <= args.limit <= 100 or not 1 <= len(args.reason) <= 200:
        parser.error("days=30..3650, limit=1..100, reason=1..200 characters")
    if args.legacy_report and (args.execute or args.legacy_reviewed):
        parser.error("Legacy survey is read-only and cannot be combined with execution")
    if args.legacy_reviewed and not args.execute:
        parser.error("Installing reviewed clearances requires --execute --writers-stopped")
    if args.execute and not args.writers_stopped:
        parser.error("Stop every application writer before using --execute --writers-stopped")
    import pymysql
    config = json.loads(args.config.read_text())
    stores, locks = [], []
    try:
        roles = [role for cfg in config["instances"] for role in cfg["schemas"]]
        if sorted(roles) != ["autolab", "filesys", "problem"]:
            raise ValueError("Exactly one filesys, problem and AutoLab role is required")
        for cfg in sorted(config["instances"], key=lambda c: (c["host"], c.get("port", 3306))):
            connection = pymysql.connect(host=cfg["host"], port=cfg.get("port", 3306), user=cfg["user"],
                password=os.environ[cfg["passwordEnv"]], autocommit=True, connect_timeout=5,
                read_timeout=30, write_timeout=30, cursorclass=pymysql.cursors.DictCursor)
            store = Store(connection, cfg["schemas"]); stores.append(store)
            if store.query("SELECT GET_LOCK('sduoj-shared-output-retention',0) AS acquired")[0]["acquired"] != 1:
                raise ValueError("Another collector holds maintenance lock")
            locks.append(store); store.update("SET SESSION time_zone='+00:00'"); store.update("SET SESSION lock_wait_timeout=5"); store.lock()
        filesys = next(s for s in stores if "filesys" in s.schemas)
        now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
        if args.legacy_report or args.legacy_reviewed:
            import legacy_output_review
            import sys
            module = sys.modules[__name__]
            if args.legacy_report:
                report = legacy_output_review.survey(module,stores,filesys,config["filesysRoot"],now,args.days,args.limit,args.after)
                legacy_output_review.write_report(args.legacy_report,report)
                print(json.dumps({"legacyReport":str(args.legacy_report),"items":len(report["snapshot"]["items"]),"snapshotSha256":report["snapshotSha256"],"nextCursor":report["snapshot"]["nextCursor"],"deleted":0}))
                return
            legacy_output_review.install(module,stores,filesys,config["filesysRoot"],json.loads(args.legacy_reviewed.read_text()),now,args.days,args.reason)
        result = collect(stores, filesys, config["filesysRoot"], args.execute,
                         now, args.days, args.limit, args.reason, args.after)
        print(json.dumps({"execute": args.execute, "nextCursor": result[-1]["fileId"] if len(result) == args.limit else "0", "results": result}, ensure_ascii=False, indent=2))
    finally:
        for store in reversed(locks):
            with contextlib.suppress(Exception):
                store.update("UNLOCK TABLES")
                store.query("SELECT RELEASE_LOCK('sduoj-shared-output-retention')")
        for store in stores:
            store.db.close()


if __name__ == "__main__":
    main()
