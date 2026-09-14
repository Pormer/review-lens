import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as con:
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("""CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, status TEXT NOT NULL, stage TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                request TEXT NOT NULL, report TEXT, error TEXT)""")
            con.execute("CREATE INDEX IF NOT EXISTS jobs_created ON jobs(created_at)")
            con.execute("CREATE TABLE IF NOT EXISTS rate_events (created_at TEXT NOT NULL, mode TEXT NOT NULL)")

    def connect(self):
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        return con

    def recover(self, days: int):
        with self.connect() as con:
            con.execute("UPDATE jobs SET status='failed', stage='중단됨', error=? WHERE status IN ('queued','running')",
                        ("서버가 재시작되어 작업이 중단되었습니다. 다시 분석해 주세요.",))
        self.cleanup(days)

    def cleanup(self, days: int):
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self.connect() as con:
            con.execute("DELETE FROM jobs WHERE created_at < ? AND status IN ('completed','failed')", (cutoff,))
            hour = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
            con.execute("DELETE FROM rate_events WHERE created_at < ?", (hour,))

    def create(self, job_id, request):
        with self.connect() as con:
            con.execute("INSERT INTO jobs VALUES (?, 'queued', '분석 대기', ?, ?, ?, NULL, NULL)",
                        (job_id, now(), now(), request.model_dump_json()))
            con.execute("INSERT INTO rate_events VALUES (?, ?)", (now(), request.mode))

    def update(self, job_id, *, status=None, stage=None, report=None, error=None):
        values = {"updated_at": now()}
        for key, value in {"status": status, "stage": stage, "report": report, "error": error}.items():
            if value is not None:
                values[key] = json.dumps(value, ensure_ascii=False) if key == "report" else value
        with self.connect() as con:
            con.execute(f"UPDATE jobs SET {', '.join(k + '=?' for k in values)} WHERE id=?", (*values.values(), job_id))

    def get(self, job_id):
        with self.connect() as con:
            row = con.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            return None
        result = dict(row)
        result["request"] = json.loads(result["request"])
        result["report"] = json.loads(result["report"]) if result["report"] else None
        return result

    def recent_live_count(self):
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        with self.connect() as con:
            return con.execute("SELECT count(*) FROM rate_events WHERE created_at >= ? AND mode='live'", (cutoff,)).fetchone()[0]

    def recent_count(self):
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        with self.connect() as con:
            return con.execute("SELECT count(*) FROM rate_events WHERE created_at >= ?", (cutoff,)).fetchone()[0]

    def delete(self, job_id):
        with self.connect() as con:
            con.execute("DELETE FROM jobs WHERE id=?", (job_id,))
