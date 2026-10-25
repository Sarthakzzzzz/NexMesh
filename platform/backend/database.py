import os
import sqlite3
from pathlib import Path
from typing import Iterator

DEFAULT_DATABASE_PATH = (Path(__file__).resolve().parent.parent / "nexmesh.db").resolve()
DATABASE_PATH = Path(os.getenv("NEXMESH_DATABASE_PATH", str(DEFAULT_DATABASE_PATH))).resolve()

SCHEMA = """
CREATE TABLE IF NOT EXISTS clients (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    organization TEXT NOT NULL DEFAULT 'nvidia',
    mode TEXT NOT NULL CHECK (mode IN ('managed_kubernetes', 'remote_participant')),
    status TEXT NOT NULL CHECK (status IN (
        'PENDING', 'APPROVED', 'PROVISIONING', 'AWAITING_CLIENT_PACKAGE',
        'READY', 'ONLINE', 'OFFLINE', 'DISABLED', 'REMOVING', 'REMOVED',
        'REJECTED', 'FAILED', 'REVOKED'
    )),
    nvflare_identity TEXT,
    agent_token TEXT UNIQUE,
    dataset_ref TEXT,
    endpoint TEXT,
    capabilities_json TEXT NOT NULL DEFAULT '{}',
    csr_uploaded INTEGER DEFAULT 0,
    signed_package_path TEXT,
    error_detail TEXT,
    last_heartbeat TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    requirements TEXT NOT NULL,
    package_url TEXT,
    participants_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'ASSIGNED',
    nvflare_job_id TEXT,
    nvflare_status TEXT,
    admin_output TEXT,
    result_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def connect() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def initialize() -> None:
    with connect() as conn:
        # Check if clients table needs status check constraint migration
        table_exists = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='clients'").fetchone()
        if table_exists:
            # Check if existing CHECK constraint allows new statuses; if empty table, recreate it
            client_count = conn.execute("SELECT count(*) FROM clients").fetchone()[0]
            if client_count == 0:
                conn.execute("DROP TABLE clients")
        conn.executescript(SCHEMA)

        existing = {row[1] for row in conn.execute("PRAGMA table_info(clients)")}
        if "agent_token" not in existing:
            conn.execute("ALTER TABLE clients ADD COLUMN agent_token TEXT")
        if "organization" not in existing:
            conn.execute("ALTER TABLE clients ADD COLUMN organization TEXT NOT NULL DEFAULT 'nvidia'")
        if "csr_uploaded" not in existing:
            conn.execute("ALTER TABLE clients ADD COLUMN csr_uploaded INTEGER DEFAULT 0")
        if "signed_package_path" not in existing:
            conn.execute("ALTER TABLE clients ADD COLUMN signed_package_path TEXT")
        if "error_detail" not in existing:
            conn.execute("ALTER TABLE clients ADD COLUMN error_detail TEXT")

        job_cols = {row[1] for row in conn.execute("PRAGMA table_info(jobs)")}
        if "nvflare_job_id" not in job_cols:
            conn.execute("ALTER TABLE jobs ADD COLUMN nvflare_job_id TEXT")
        if "nvflare_status" not in job_cols:
            conn.execute("ALTER TABLE jobs ADD COLUMN nvflare_status TEXT")
        if "admin_output" not in job_cols:
            conn.execute("ALTER TABLE jobs ADD COLUMN admin_output TEXT")


def connection() -> Iterator[sqlite3.Connection]:
    database = connect()
    try:
        yield database
    finally:
        database.close()
