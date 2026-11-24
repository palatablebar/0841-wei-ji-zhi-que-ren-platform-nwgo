import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.init()

    def connect(self):
        connection = sqlite3.connect(self.path, timeout=8)
        connection.row_factory = sqlite3.Row
        return connection

    def init(self):
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS runs(
              id TEXT PRIMARY KEY,
              request_key TEXT UNIQUE NOT NULL,
              created_at TEXT NOT NULL,
              profile TEXT NOT NULL,
              status TEXT NOT NULL,
              revision INTEGER NOT NULL,
              payload TEXT NOT NULL,
              comment TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS specimen_reviews(
              run_id TEXT NOT NULL,
              specimen_id TEXT NOT NULL,
              status TEXT NOT NULL,
              revision INTEGER NOT NULL,
              content_fingerprint TEXT NOT NULL,
              comment TEXT NOT NULL DEFAULT '',
              reviewed_at TEXT NOT NULL,
              PRIMARY KEY (run_id, specimen_id)
            );
            CREATE TABLE IF NOT EXISTS credentials(
              run_id TEXT NOT NULL,
              specimen_id TEXT NOT NULL,
              credential_id TEXT NOT NULL,
              issued_at TEXT NOT NULL,
              revision INTEGER NOT NULL,
              artifact TEXT NOT NULL,
              PRIMARY KEY (run_id, specimen_id)
            );
            ''')

    def find_by_request(self, request_key):
        with self.connect() as db:
            row = db.execute("SELECT * FROM runs WHERE request_key=?", (request_key,)).fetchone()
        return dict(row) if row else None

    def create(self, request_key, profile, payload):
        existing = self.find_by_request(request_key)
        if existing:
            return existing
        run_id = uuid.uuid4().hex[:12]
        with self.connect() as db:
            db.execute("INSERT INTO runs(id,request_key,created_at,profile,status,revision,payload) VALUES(?,?,?,?,?,?,?)",
                       (run_id, request_key, datetime.now(timezone.utc).isoformat(), profile, "DRAFT", 0,
                        json.dumps(payload, ensure_ascii=False)))
        return self.get(run_id)

    def get(self, run_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        return dict(row) if row else None

    def review(self, run_id, decision, comment, expected_revision):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                return None, "missing"
            if row["revision"] != expected_revision:
                return None, "stale"
            db.execute("UPDATE runs SET status=?, revision=revision+1, comment=? WHERE id=?",
                       (decision, comment, run_id))
        return self.get(run_id), None

    # ----- 单标本复核与确认凭据 -----

    def list_specimen_states(self, run_id):
        with self.connect() as db:
            rows = db.execute("SELECT * FROM specimen_reviews WHERE run_id=? ORDER BY specimen_id",
                              (run_id,)).fetchall()
        return [dict(row) for row in rows]

    def get_specimen_state(self, run_id, specimen_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM specimen_reviews WHERE run_id=? AND specimen_id=?",
                             (run_id, specimen_id)).fetchone()
        return dict(row) if row else None

    def get_credential(self, run_id, specimen_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM credentials WHERE run_id=? AND specimen_id=?",
                             (run_id, specimen_id)).fetchone()
        return dict(row) if row else None

    def credential_index(self, run_id):
        with self.connect() as db:
            rows = db.execute("SELECT specimen_id FROM credentials WHERE run_id=?", (run_id,)).fetchall()
        return {row["specimen_id"] for row in rows}

    def mark_reviewed(self, run_id, specimen_id, fingerprint, comment, expected_revision):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM credentials WHERE run_id=? AND specimen_id=?",
                          (run_id, specimen_id)).fetchone():
                return None, "sealed"
            row = db.execute("SELECT * FROM specimen_reviews WHERE run_id=? AND specimen_id=?",
                             (run_id, specimen_id)).fetchone()
            current_revision = row["revision"] if row else 0
            if current_revision != expected_revision:
                return None, "stale"
            reviewed_at = datetime.now(timezone.utc).isoformat()
            if row is None:
                db.execute(
                    "INSERT INTO specimen_reviews(run_id,specimen_id,status,revision,content_fingerprint,"
                    "comment,reviewed_at) VALUES(?,?,?,?,?,?,?)",
                    (run_id, specimen_id, "REVIEWED", 1, fingerprint, comment, reviewed_at))
            else:
                db.execute(
                    "UPDATE specimen_reviews SET status=?, revision=revision+1, content_fingerprint=?, "
                    "comment=?, reviewed_at=? WHERE run_id=? AND specimen_id=?",
                    ("REVIEWED", fingerprint, comment, reviewed_at, run_id, specimen_id))
        return self.get_specimen_state(run_id, specimen_id), None

    def correct_specimen(self, run_id, specimen_id, new_payload, fingerprint, expected_revision):
        """更正与状态变更在同一事务内完成，返回 (状态, 问题码)。

        指纹不变（如仅单位换算、读数与判定一致）时保留原复核；
        指纹变化时复核作废回到待复核；每次更正都推进版本号。
        批次载荷与复核状态在同一事务内落库，避免读到中间态。
        """
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM credentials WHERE run_id=? AND specimen_id=?",
                          (run_id, specimen_id)).fetchone():
                return None, "sealed"
            run = db.execute("SELECT id FROM runs WHERE id=?", (run_id,)).fetchone()
            if run is None:
                return None, "missing"
            row = db.execute("SELECT * FROM specimen_reviews WHERE run_id=? AND specimen_id=?",
                             (run_id, specimen_id)).fetchone()
            current_revision = row["revision"] if row else 0
            if current_revision != expected_revision:
                return None, "stale"
            if row is None:
                db.execute(
                    "INSERT INTO specimen_reviews(run_id,specimen_id,status,revision,content_fingerprint,"
                    "comment,reviewed_at) VALUES(?,?,?,?,?,?,?)",
                    (run_id, specimen_id, "PENDING", 1, fingerprint, "",
                     datetime.now(timezone.utc).isoformat()))
            else:
                new_status = "PENDING" if row["content_fingerprint"] != fingerprint else row["status"]
                db.execute(
                    "UPDATE specimen_reviews SET revision=revision+1, content_fingerprint=?, status=? "
                    "WHERE run_id=? AND specimen_id=?",
                    (fingerprint, new_status, run_id, specimen_id))
            db.execute("UPDATE runs SET payload=? WHERE id=?",
                       (json.dumps(new_payload, ensure_ascii=False), run_id))
        return self.get_specimen_state(run_id, specimen_id), None

    def insert_credential(self, run_id, specimen_id, expected_revision, expected_fingerprint, artifact):
        """事务内复核后再落库凭据，返回 (凭据字典, 问题码)。

        已存在凭据时原样返回，绝不重复生成。
        """
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT * FROM credentials WHERE run_id=? AND specimen_id=?",
                                  (run_id, specimen_id)).fetchone()
            if existing:
                return json.loads(existing["artifact"]), "duplicate"
            state = db.execute("SELECT * FROM specimen_reviews WHERE run_id=? AND specimen_id=?",
                               (run_id, specimen_id)).fetchone()
            if state is None or state["status"] != "REVIEWED":
                return None, "not_reviewed"
            if state["revision"] != expected_revision:
                return None, "stale"
            if state["content_fingerprint"] != expected_fingerprint:
                return None, "superseded"
            db.execute(
                "INSERT INTO credentials(run_id,specimen_id,credential_id,issued_at,revision,artifact) "
                "VALUES(?,?,?,?,?,?)",
                (run_id, specimen_id, artifact["credential_id"], artifact["issued_at"],
                 artifact["review"]["revision"], json.dumps(artifact, ensure_ascii=False)))
        return artifact, None
