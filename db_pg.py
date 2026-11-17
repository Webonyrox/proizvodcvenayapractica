"""Слой работы с базой данных PostgreSQL для DveriApp.

Использует тот же интерфейс, что и db.py (SQLite), поэтому app.py работает
с любой из двух баз без изменений.

Подключение берётся из:
  1. переменной окружения DATABASE_URL, либо
  2. файла config.json -> "postgres_url".

Формат строки подключения:
  postgresql://user:password@host:5432/dbname?sslmode=require

Установить драйвер:  pip install psycopg2-binary
"""

import json
import os
from datetime import datetime
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

CONFIG_FILE = Path(__file__).resolve().parent / "config.json"

TYPE_LABELS = {"install": "Установка двери", "measure": "Замер проёма"}
STATUS_LABELS = {"new": "Новая", "taken": "В работе", "done": "Выполнена", "cancelled": "Отменена"}


def connection_url():
    url = os.environ.get("DATABASE_URL", "").strip()
    if url:
        return _normalize(url)
    if CONFIG_FILE.exists():
        try:
            cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            url = str(cfg.get("postgres_url", "")).strip()
        except Exception:
            url = ""
    if not url:
        raise RuntimeError(
            "Не указан адрес PostgreSQL. Добавьте в config.json поле "
            '"postgres_url": "postgresql://user:password@host:5432/db?sslmode=require" '
            "или переменную окружения DATABASE_URL."
        )
    return _normalize(url)


def _normalize(url):
    # некоторые хостинги отдают URL как postgres:// — psycopg2 понимает только postgresql://
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url


def get_conn():
    conn = psycopg2.connect(connection_url(), cursor_factory=RealDictCursor)
    return conn


def init_db():
    conn = get_conn()
    with conn, conn.cursor() as cur:
        cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            login TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('seller','worker')),
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS requests (
            id SERIAL PRIMARY KEY,
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
        """)


# ----------------------------------------------------------------- users ----

def create_user(name, login, password_hash, role):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO users (name, login, password_hash, role, created_at) "
            "VALUES (%s,%s,%s,%s,%s) RETURNING id",
            (name, login, password_hash, role, datetime.now().isoformat(timespec="seconds")),
        )
        return cur.fetchone()["id"]


def get_user(uid):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM users WHERE id = %s", (uid,))
        row = cur.fetchone()
    return dict(row) if row else None


def get_user_by_login(login):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM users WHERE login = %s", (login,))
        row = cur.fetchone()
    return dict(row) if row else None


def get_default_seller():
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM users WHERE role = 'seller' ORDER BY id LIMIT 1")
        row = cur.fetchone()
    return dict(row) if row else None


# -------------------------------------------------------------- requests ----

def create_request(seller_id, rtype, client_name, client_phone, address,
                   comment="", date_preferred="", door_count="1"):
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO requests
               (seller_id, type, status, client_name, client_phone, address,
                comment, date_preferred, door_count, created_at, updated_at)
               VALUES (%s,%s,'new',%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (seller_id, rtype, client_name, client_phone, address,
             comment, date_preferred, door_count, now, now),
        )
        return cur.fetchone()["id"]


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
        query += " AND r.status = %s"
        params.append(status)
    if seller_id is not None:
        query += " AND r.seller_id = %s"
        params.append(seller_id)
    if worker_id is not None:
        query += " AND r.worker_id = %s"
        params.append(worker_id)
    query += " ORDER BY r.created_at DESC"
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()
    result = [dict(r) for r in rows]
    for r in result:
        r["type_label"] = TYPE_LABELS.get(r["type"], r["type"])
        r["status_label"] = STATUS_LABELS.get(r["status"], r["status"])
    return result


def get_request(rid):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM requests WHERE id = %s", (rid,))
        row = cur.fetchone()
    return dict(row) if row else None


def take_request(rid, worker_id):
    """Рабочий берёт заявку в работу (только если она ещё свободна)."""
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE requests SET status='taken', worker_id=%s, updated_at=%s "
            "WHERE id=%s AND status='new'",
            (worker_id, now, rid),
        )


def release_request(rid, worker_id):
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE requests SET status='new', worker_id=NULL, updated_at=%s "
            "WHERE id=%s AND worker_id=%s",
            (now, rid, worker_id),
        )


def complete_request(rid, worker_id):
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE requests SET status='done', updated_at=%s "
            "WHERE id=%s AND worker_id=%s",
            (now, rid, worker_id),
        )


# ------------------------------------------------ admin panel helpers ----

def table_columns(table):
    """Имена колонок таблицы (для админ-панели). Таблица берётся из белого списка."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = %s ORDER BY ordinal_position",
            (table,),
        )
        return [r["column_name"] for r in cur.fetchall()]


def table_rows(table, limit=500):
    cols = table_columns(table)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(f'SELECT * FROM "{table}" ORDER BY id DESC LIMIT %s', (limit,))
        rows = [dict(r) for r in cur.fetchall()]
    return cols, rows


def update_row(table, row_id, updates):
    """updates: dict col->value. Колонки уже проверены вызывающим по схеме БД."""
    parts, params = [], []
    for col, val in updates.items():
        parts.append(f'"{col}" = %s')
        params.append(val)
    params.append(row_id)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(f'UPDATE "{table}" SET {", ".join(parts)} WHERE id = %s', params)


def delete_user(uid):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("UPDATE requests SET worker_id = NULL, status='new' WHERE worker_id = %s", (uid,))
        cur.execute("DELETE FROM requests WHERE seller_id = %s", (uid,))
        cur.execute("DELETE FROM users WHERE id = %s", (uid,))


def delete_request(rid):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM requests WHERE id = %s", (rid,))


def export_sql_dump():
    """Возвращает SQL-дампы обеих таблиц как текст (для скачивания из админки)."""
    lines = ["-- DveriApp PostgreSQL dump", ""]
    with get_conn() as conn, conn.cursor() as cur:
        for table in ("users", "requests"):
            cols = table_columns(table)
            cur.execute(f'SELECT * FROM "{table}" ORDER BY id')
            for row in cur.fetchall():
                vals = ", ".join(
                    cur.mogrify("%s", (row[c],)).decode("utf-8") for c in cols
                )
                collist = ", ".join(f'"{c}"' for c in cols)
                lines.append(f'INSERT INTO "{table}" ({collist}) VALUES ({vals});')
            lines.append("")
    return "\n".join(lines)
