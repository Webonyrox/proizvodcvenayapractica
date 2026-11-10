"""Слой работы с базой данных (SQLite) для DveriApp."""

import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "dveri.db"

TYPE_LABELS = {"install": "Установка двери", "measure": "Замер проёма"}
STATUS_LABELS = {"new": "Новая", "taken": "В работе", "done": "Выполнена", "cancelled": "Отменена"}


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            login TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('seller','worker')),
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_id INTEGER NOT NULL REFERENCES users(id),
            worker_id INTEGER REFERENCES users(id),
            type TEXT NOT NULL CHECK (type IN ('install','measure')),
            status TEXT NOT NULL DEFAULT 'new'
                CHECK (status IN ('new','taken','done','cancelled')),
            client_name TEXT NOT NULL,
            client_phone TEXT NOT NULL,
            address TEXT NOT NULL,
            comment TEXT DEFAULT '',
            date_preferred TEXT DEFAULT '',
            door_count TEXT DEFAULT '1',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    conn.commit()
    conn.close()


# ----------------------------------------------------------------- users ----

def create_user(name, login, password_hash, role):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO users (name, login, password_hash, role, created_at) VALUES (?,?,?,?,?)",
        (name, login, password_hash, role, datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit()
    uid = cur.lastrowid
    conn.close()
    return uid


def _rows_to_dicts(rows):
    return [dict(r) for r in rows]


def get_user(uid):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_login(login):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE login = ?", (login,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_default_seller():
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM users WHERE role = 'seller' ORDER BY id LIMIT 1"
    ).fetchone()
    conn.close()
    return dict(row) if row else None


# -------------------------------------------------------------- requests ----

def create_request(seller_id, rtype, client_name, client_phone, address,
                   comment="", date_preferred="", door_count="1"):
    now = datetime.now().isoformat(timespec="seconds")
    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO requests
           (seller_id, type, status, client_name, client_phone, address,
            comment, date_preferred, door_count, created_at, updated_at)
           VALUES (?,?, 'new', ?,?,?,?,?,?,?,?)""",
        (seller_id, rtype, client_name, client_phone, address,
         comment, date_preferred, door_count, now, now),
    )
    conn.commit()
    rid = cur.lastrowid
    conn.close()
    return rid


def list_requests(status=None, seller_id=None, worker_id=None):
    query = (
        "SELECT r.*, s.name AS seller_name, w.name AS worker_name "
        "FROM requests r "
        "JOIN users s ON s.id = r.seller_id "
        "LEFT JOIN users w ON w.id = r.worker_id "
        "WHERE 1=1"
    )
    params = []
    if status:
        query += " AND r.status = ?"
        params.append(status)
    if seller_id is not None:
        query += " AND r.seller_id = ?"
        params.append(seller_id)
    if worker_id is not None:
        query += " AND r.worker_id = ?"
        params.append(worker_id)
    query += " ORDER BY r.created_at DESC"
    conn = get_conn()
    rows = conn.execute(query, params).fetchall()
    conn.close()
    result = _rows_to_dicts(rows)
    for r in result:
        r["type_label"] = TYPE_LABELS.get(r["type"], r["type"])
        r["status_label"] = STATUS_LABELS.get(r["status"], r["status"])
    return result


def get_request(rid):
    conn = get_conn()
    row = conn.execute("SELECT * FROM requests WHERE id = ?", (rid,)).fetchone()
    conn.close()
    return dict(row) if row else None


def take_request(rid, worker_id):
    """Рабочий берёт заявку в работу (только если она ещё свободна)."""
    now = datetime.now().isoformat(timespec="seconds")
    conn = get_conn()
    conn.execute(
        "UPDATE requests SET status='taken', worker_id=?, updated_at=? "
        "WHERE id=? AND status='new'",
        (worker_id, now, rid),
    )
    conn.commit()
    conn.close()


def release_request(rid, worker_id):
    now = datetime.now().isoformat(timespec="seconds")
    conn = get_conn()
    conn.execute(
        "UPDATE requests SET status='new', worker_id=NULL, updated_at=? "
        "WHERE id=? AND worker_id=?",
        (now, rid, worker_id),
    )
    conn.commit()
    conn.close()


def complete_request(rid, worker_id):
    now = datetime.now().isoformat(timespec="seconds")
    conn = get_conn()
    conn.execute(
        "UPDATE requests SET status='done', updated_at=? "
        "WHERE id=? AND worker_id=?",
        (now, rid, worker_id),
    )
    conn.commit()
    conn.close()
