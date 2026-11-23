"""Перенос данных из старой базы SQLite (dveri.db) в PostgreSQL.

Запуск:  python migrate_sqlite_to_postgres.py
Скрипт безопасен: если в PostgreSQL уже есть пользователи — ничего не переносит
(можно форсировать флагом --force).
"""
import sys

import db        # SQLite (старая база)
import db_pg     # PostgreSQL (новая база)


def main():
    force = "--force" in sys.argv
    db_pg.init_db()
    with db_pg.get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS c FROM users")
        n_users = cur.fetchone()["c"]
    if n_users > 0 and not force:
        print(f"В PostgreSQL уже {n_users} пользователей — перенос пропускаю.")
        print("Чтобы перенести всё равно (будут дубли), запустите с --force.")
        return

    users = []
    with db.get_conn() as conn:
        users = [dict(r) for r in conn.execute("SELECT * FROM users ORDER BY id").fetchall()]
        reqs = [dict(r) for r in conn.execute("SELECT * FROM requests ORDER BY id").fetchall()]

    if not users and not reqs:
        print("Старая база SQLite пуста — переносить нечего.")
        return

    db_pg.init_db()
    id_map = {}
    for u in users:
        new_id = db_pg.create_user(u["name"], u["login"], u["password_hash"], u["role"])
        id_map[u["id"]] = new_id

    n = 0
    now = __import__("datetime").datetime.now().isoformat(timespec="seconds")
    with db_pg.get_conn() as conn, conn.cursor() as cur:
        for r in reqs:
            worker = id_map.get(r["worker_id"]) if r["worker_id"] else None
            cur.execute(
                """INSERT INTO requests
                   (seller_id, worker_id, type, status, client_name, client_phone,
                    address, comment, date_preferred, door_count, created_at, updated_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (id_map[r["seller_id"]], worker, r["type"], r["status"],
                 r["client_name"], r["client_phone"], r["address"],
                 r.get("comment", ""), r.get("date_preferred", ""),
                 r.get("door_count", "1"), r["created_at"], now),
            )
            n += 1

    print(f"Перенесено: {len(users)} пользователей, {n} заявок — из SQLite в PostgreSQL.")


if __name__ == "__main__":
    main()
