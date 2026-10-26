#!/usr/bin/python3
# Copyright (c) 2026 AWA <https://www.akkdiy.cn>. All rights reserved.
"""Private scheduler and backup runner for DBBackup."""
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import signal
import sqlite3
import stat
import subprocess
import tempfile
import time
from pathlib import Path

import cgi_app


PKG_VAR = Path("/var/packages/DBBackup/var")
DB_PATH = PKG_VAR / "state.sqlite3"
PID_PATH = PKG_VAR / "worker.pid"
STOP = False
ACTIVE_PROCESS = None


def stop_handler(_signum, _frame):
    global STOP
    STOP = True
    if ACTIVE_PROCESS is not None:
        try:
            ACTIVE_PROCESS.terminate()
        except OSError:
            pass


def now_local():
    return dt.datetime.now().astimezone()


def dt_parse(value):
    if not value:
        return None
    try:
        result = dt.datetime.fromisoformat(value)
        return result.astimezone() if result.tzinfo else result.astimezone()
    except (ValueError, TypeError):
        return None


def dt_string(value):
    return value.astimezone().isoformat(timespec="seconds")


def interval_delta(task):
    n = max(1, int(task["interval_value"]))
    return dt.timedelta(minutes=n) if task["interval_unit"] == "minutes" else dt.timedelta(hours=n)


def scheduled_after(task, base):
    base = base.astimezone()
    if task["frequency"] == "interval":
        return base + interval_delta(task)
    hh, mm = (int(x) for x in task["run_time"].split(":"))
    date = base.date()
    candidate = dt.datetime.combine(date, dt.time(hh, mm), tzinfo=base.tzinfo)
    if task["frequency"] == "weekly":
        days = (int(task["weekday"]) - date.weekday()) % 7
        candidate = candidate + dt.timedelta(days=days)
        if candidate <= base:
            candidate += dt.timedelta(days=7)
    elif candidate <= base:
        candidate += dt.timedelta(days=1)
    return candidate


def connect_state():
    PKG_VAR.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(PKG_VAR, 0o700)
    db = sqlite3.connect(str(DB_PATH), timeout=15)
    os.chmod(DB_PATH, 0o600)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=10000")
    return db


def write_pid():
    fd = os.open(str(PID_PATH), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, (str(os.getpid()) + "\n").encode("ascii"))
        os.fsync(fd)
    finally:
        os.close(fd)
    os.chmod(PID_PATH, 0o600)


def clear_pid():
    try:
        if PID_PATH.read_text("ascii").strip() == str(os.getpid()):
            PID_PATH.unlink()
    except OSError:
        pass


def initialize_boot_schedule():
    try:
        boot_id = Path("/proc/sys/kernel/random/boot_id").read_text("ascii").strip()
    except OSError:
        boot_id = "boot-" + now_local().date().isoformat()
    db = connect_state()
    try:
        prior = db.execute("SELECT value FROM meta WHERE key='boot_id'").fetchone()
        if prior and prior[0] == boot_id:
            return
        now = now_local()
        rows = db.execute("SELECT id,startup_delay FROM tasks WHERE enabled=1 AND manual_only=0 AND frequency='startup'").fetchall()
        for row in rows:
            due = now + dt.timedelta(minutes=int(row["startup_delay"]))
            db.execute("UPDATE tasks SET next_run=?,last_message='等待开机后备份' WHERE id=?", (dt_string(due), row["id"]))
        db.execute("UPDATE tasks SET next_run=NULL WHERE enabled=1 AND manual_only=0 AND frequency!='startup'")
        db.execute("INSERT INTO meta(key,value) VALUES('boot_id',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (boot_id,))
        db.commit()
    finally:
        db.close()


def output_name(task, database):
    stamp = now_local().strftime("%Y%m%d-%H%M%S-%f")
    safe_db = re.sub(r'[\\/\x00-\x1f<>:"|?*]+', "_", database).strip(" .")[:120] or "database"
    return "{}-{}.sql".format(safe_db, stamp)


def record_and_prune(target, task, database, final_path):
    """Track only package-created files and rotate within this task/database."""
    keep = int(task.get("retention_count", 0))
    if keep <= 0:
        return ""
    db_key = hashlib.sha256(database.encode("utf-8")).hexdigest()[:16]
    try:
        db = connect_state()
    except Exception:
        return "备份已生成，但无法更新保留记录"
    warning = ""
    try:
        db.execute("INSERT OR IGNORE INTO backup_files(path,task_id,database_key,created_at) VALUES(?,?,?,?)",
                   (final_path, task["id"], db_key, time.time()))
        db.commit()
        rows = db.execute("SELECT path FROM backup_files WHERE task_id=? AND database_key=? ORDER BY created_at DESC,path DESC",
                          (task["id"], db_key)).fetchall()
        target_real = os.path.realpath(target)
        for row in rows[keep:]:
            path = os.path.abspath(row["path"])
            try:
                if os.path.dirname(path) != target_real:
                    warning = "有旧备份路径不在当前目录，已跳过清理"
                    continue
                info = os.lstat(path)
                if not stat.S_ISREG(info.st_mode):
                    warning = "有旧备份不是普通文件，已跳过清理"
                    continue
                os.unlink(path)
            except FileNotFoundError:
                pass
            except OSError:
                warning = "旧备份清理失败，请检查目录权限"
                continue
            db.execute("DELETE FROM backup_files WHERE path=?", (path,))
        db.commit()
    except Exception:
        warning = "备份已生成，但旧备份清理失败"
    finally:
        db.close()
    return warning


def dump_candidates():
    return cgi_app.client_candidates(True)


def dump_attempt(command, target):
    """Run one dump command into a private temp file next to the target."""
    global ACTIVE_PROCESS
    fd, temporary = tempfile.mkstemp(prefix=".dbbackup-", suffix=".partial", dir=target)
    # Backups contain database contents. Keep them private to the package
    # account unless the NAS share's inherited ACL grants additional readers.
    os.fchmod(fd, 0o600)
    try:
        with os.fdopen(fd, "wb") as raw, tempfile.TemporaryFile(mode="w+b", dir=str(PKG_VAR)) as errors:
            proc = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=errors, close_fds=True)
            ACTIVE_PROCESS = proc
            try:
                while True:
                    chunk = proc.stdout.read(1024 * 1024)
                    if not chunk:
                        break
                    raw.write(chunk)
                proc.stdout.close()
                code = proc.wait()
                ACTIVE_PROCESS = None
                raw.flush()
                os.fsync(raw.fileno())
            except BaseException:
                proc.kill()
                proc.wait()
                ACTIVE_PROCESS = None
                raise
            errors.seek(0)
            stderr = errors.read(4096).decode("utf-8", "replace").strip()
        return code, stderr, temporary
    except BaseException:
        try: os.unlink(temporary)
        except OSError: pass
        raise


def backup_database(profile, task, database, tables):
    target = cgi_app.safe_target(task["target"])
    # Recheck names against the live catalog immediately before invoking the client.
    available_dbs = set(cgi_app.list_databases(profile))
    if database not in available_dbs:
        raise RuntimeError("数据库已不存在或账号失去读取权限：" + database)
    available_tables = set(cgi_app.list_tables(profile, database))
    if tables and any(name not in available_tables for name in tables):
        raise RuntimeError("所选数据表已不存在或账号失去读取权限：" + database)
    if tables and (database.startswith("-") or any(name.startswith("-") for name in tables)):
        raise RuntimeError("MariaDB 备份工具不支持以连字符开头的数据库或数据表名称")
    clients = dump_candidates()
    if not clients:
        raise RuntimeError("找不到 mariadb-dump/mysqldump；请確認已安裝 MariaDB 10")
    connect_cmd, option_file = cgi_app.connection(profile)
    dump_client = None
    for candidate in clients:
        # Probe the matching dump client with --version before using it.
        p = subprocess.run([candidate, "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10, check=False)
        if p.returncode == 0:
            dump_client = candidate
            break
    if not dump_client:
        try: os.unlink(option_file)
        except OSError: pass
        raise RuntimeError("MariaDB dump 工具无法启动")

    # connect_cmd[1:] holds only options that both the client and mariadb-dump
    # accept; client-only options such as --connect-timeout must stay out.
    command = [dump_client] + connect_cmd[1:]
    command += ["--single-transaction", "--quick", "--hex-blob", "--triggers"]
    attempts = []
    if not tables:
        attempts.append(command + ["--routines", "--events", "--databases", database])
        # A remote account limited to its own database cannot always export
        # stored routines/events. Keep the data backup instead of failing.
        attempts.append(command + ["--databases", database])
    else:
        attempts.append(command + [database] + list(tables))

    filename = output_name(task, database)
    final_path = os.path.join(target, filename)
    downgrade_note = ""
    try:
        for index, attempt in enumerate(attempts):
            code, stderr, temporary = dump_attempt(attempt, target)
            if code == 0:
                break
            try: os.unlink(temporary)
            except OSError: pass
            message = stderr.replace(profile["db_password"], "[已隐藏]")[:700] or "MariaDB 备份失败"
            if index + 1 < len(attempts) and re.search(r"PROCESS|EVENT|ROUTINE|TRIGGER|Access denied", stderr, re.I):
                downgrade_note = "账号无权导出存储过程/事件，已改为仅备份表结构与数据"
                continue
            raise RuntimeError(message)
        # Publish the complete plain SQL dump without exposing a partial file.
        os.link(temporary, final_path)
        os.unlink(temporary)
        warning = record_and_prune(target, task, database, final_path)
        if downgrade_note:
            warning = (warning + "；" if warning else "") + downgrade_note
        return final_path, warning
    finally:
        try: os.unlink(option_file)
        except OSError: pass


def run_task(task):
    db = connect_state()
    try:
        source = cgi_app.source_by_id(db, task.get("source_id") or "")
    finally:
        db.close()
    if not source:
        raise RuntimeError("此计划关联的数据源已被删除，请重新编辑计划并选择数据源")
    if source["owner"] != task["owner"]:
        raise RuntimeError("数据源不属于此计划的所有者")
    databases = json.loads(task["databases_json"])
    outputs = []
    for selection in databases:
        path, warning = backup_database(source, task, selection["name"], selection.get("tables", []))
        outputs.append(os.path.basename(path) + ("（" + warning + "）" if warning else ""))
    return outputs


def next_due_tasks():
    db = connect_state()
    try:
        now = now_local()
        rows = db.execute("SELECT * FROM tasks WHERE manual_only=1 AND run_requested=1 OR enabled=1 AND run_requested=1 OR enabled=1 AND manual_only=0 AND next_run IS NOT NULL").fetchall()
        # Determine and persist first scheduled run for newly created or re-enabled tasks.
        missing = db.execute("SELECT * FROM tasks WHERE enabled=1 AND manual_only=0 AND frequency!='startup' AND next_run IS NULL").fetchall()
        for row in missing:
            due = scheduled_after(row, now)
            db.execute("UPDATE tasks SET next_run=? WHERE id=?", (dt_string(due), row["id"]))
        db.commit()
        due_rows = []
        for row in rows:
            if row["run_requested"]:
                due_rows.append(dict(row))
            elif row["enabled"] and row["manual_only"] == 0:
                due = dt_parse(row["next_run"])
                if due and due <= now:
                    due_rows.append(dict(row))
        return due_rows
    finally:
        db.close()


def run_one(task):
    started = now_local()
    db = connect_state()
    try:
        db.execute("UPDATE tasks SET last_message='备份进行中' WHERE id=?", (task["id"],))
        db.commit()
    finally:
        db.close()
    try:
        outputs = run_task(task)
        message = "完成：" + ", ".join(outputs)
        success = True
    except Exception as error:
        message = "失败：" + str(error).replace("\n", " ")[:700]
        success = False
    db = connect_state()
    try:
        current = db.execute("SELECT * FROM tasks WHERE id=?", (task["id"],)).fetchone()
        if not current:
            return
        if current["manual_only"] and success:
            db.execute("DELETE FROM tasks WHERE id=?", (task["id"],))
        elif current["manual_only"]:
            db.execute("UPDATE tasks SET run_requested=0,last_run=?,last_message=? WHERE id=?", (dt_string(started), message, task["id"]))
        elif current["frequency"] == "startup":
            db.execute("UPDATE tasks SET run_requested=0,last_run=?,last_message=?,next_run=NULL WHERE id=?", (dt_string(started), message, task["id"]))
        elif current["enabled"]:
            next_run = scheduled_after(current, now_local())
            db.execute("UPDATE tasks SET run_requested=0,last_run=?,last_message=?,next_run=? WHERE id=?", (dt_string(started), message, dt_string(next_run), task["id"]))
        else:
            db.execute("UPDATE tasks SET run_requested=0,last_run=?,last_message=?,next_run=NULL WHERE id=?", (dt_string(started), message, task["id"]))
        db.commit()
    finally:
        db.close()
    print("{} {} {}".format(dt_string(started), "OK" if success else "ERROR", message), flush=True)


def main():
    signal.signal(signal.SIGTERM, stop_handler)
    signal.signal(signal.SIGINT, stop_handler)
    PKG_VAR.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(PKG_VAR, 0o700)
    lock_handle = open(PKG_VAR / "worker.lock", "a+b")
    os.chmod(PKG_VAR / "worker.lock", 0o600)
    try:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return
    write_pid()
    try:
        # The web interface may not have been opened yet after package installation.
        # Create the shared SQLite schema before boot scheduling reads its tables.
        schema_db = cgi_app.connect_db()
        schema_db.close()
        initialize_boot_schedule()
        while not STOP:
            for task in next_due_tasks():
                if STOP:
                    break
                run_one(task)
            for _ in range(10):
                if STOP:
                    break
                time.sleep(1)
    finally:
        clear_pid()


if __name__ == "__main__":
    main()

