"""
DveriApp — сервис заявок на установку и замер дверей.

Продавцы дверей подают заявку (установка / замер),
установщики и замерщики видят заявку: адрес, телефон клиента, тип работы.

Запуск:
    python app.py
Сайт: http://localhost:5000
"""

import json
import secrets
from datetime import datetime
from pathlib import Path

from flask import (Flask, Response, jsonify, redirect, render_template,
                   request, send_file, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

import db

app = Flask(__name__)
app.config["SECRET_KEY"] = "dveri-app-secret-change-me"

# ---------- настройки админ-панели (доступ к базе данных) ----------
CONFIG_FILE = Path(__file__).resolve().parent / "config.json"


def admin_credentials():
    """Читает логин/пароль админа из config.json (создаёт файл при необходимости)."""
    cfg = {"admin_login": "admin", "admin_password": "admin123", "ngrok_authtoken": ""}
    if CONFIG_FILE.exists():
        try:
            cfg.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
        except Exception:
            pass
    else:
        CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return cfg["admin_login"], cfg["admin_password"]


# ---------------------------------------------------------------- helpers ---

def current_user():
    from flask import session
    uid = session.get("user_id")
    return db.get_user(uid) if uid else None


def role_required(*roles):
    user = current_user()
    if not user or user["role"] not in roles:
        return None
    return user


# ------------------------------------------------------------------ pages ---

@app.route("/")
def index():
    user = current_user()
    if not user:
        return render_template("index.html")
    if user["role"] == "seller":
        return redirect(url_for("new_request"))
    return redirect(url_for("feed"))


# ---- auth ----

@app.route("/register", methods=["GET", "POST"])
def register():
    error = None
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        login = request.form.get("login", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "seller")
        if role not in ("seller", "worker"):
            role = "seller"
        if not name or not login or len(password) < 4:
            error = "Заполните имя, логин и пароль (минимум 4 символа)."
        elif db.get_user_by_login(login):
            error = "Такой логин уже занят."
        else:
            uid = db.create_user(name, login, generate_password_hash(password), role)
            from flask import session
            session["user_id"] = uid
            return redirect(url_for("index"))
    return render_template("register.html", error=error)


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        login_name = request.form.get("login", "").strip()
        password = request.form.get("password", "")
        user = db.get_user_by_login(login_name)
        if user and check_password_hash(user["password_hash"], password):
            from flask import session
            session["user_id"] = user["id"]
            return redirect(url_for("index"))
        error = "Неверный логин или пароль."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    from flask import session
    session.pop("user_id", None)
    return redirect(url_for("index"))


# ---- seller: create request ----

@app.route("/new", methods=["GET", "POST"])
def new_request():
    user = role_required("seller")
    if not user:
        return redirect(url_for("login"))

    error = None
    if request.method == "POST":
        rtype = request.form.get("type", "")
        client_name = request.form.get("client_name", "").strip()
        client_phone = request.form.get("client_phone", "").strip()
        address = request.form.get("address", "").strip()
        comment = request.form.get("comment", "").strip()
        date_preferred = request.form.get("date_preferred", "").strip()
        door_count = request.form.get("door_count", "1").strip()

        if rtype not in ("install", "measure"):
            error = "Выберите тип заявки."
        elif not client_name or not client_phone or not address:
            error = "Имя клиента, телефон и адрес обязательны."
        else:
            db.create_request(
                seller_id=user["id"],
                rtype=rtype,
                client_name=client_name,
                client_phone=client_phone,
                address=address,
                comment=comment,
                date_preferred=date_preferred,
                door_count=door_count or "1",
            )
            return redirect(url_for("my_requests"))

    return render_template("new_request.html", user=user, error=error)


@app.route("/my-requests")
def my_requests():
    user = role_required("seller")
    if not user:
        return redirect(url_for("login"))
    requests_ = db.list_requests(seller_id=user["id"])
    return render_template("my_requests.html", user=user, requests=requests_)


# ---- worker: feed & take requests ----

@app.route("/feed")
def feed():
    user = role_required("worker")
    if not user:
        return redirect(url_for("login"))
    new = db.list_requests(status="new")
    mine = db.list_requests(status="taken", worker_id=user["id"])
    done = db.list_requests(status="done", worker_id=user["id"])
    return render_template("feed.html", user=user, new=new, mine=mine, done=done)


@app.route("/request/<int:rid>/take", methods=["POST"])
def take_request(rid):
    user = role_required("worker")
    if not user:
        return redirect(url_for("login"))
    db.take_request(rid, user["id"])
    return redirect(url_for("feed"))


@app.route("/request/<int:rid>/release", methods=["POST"])
def release_request(rid):
    user = role_required("worker")
    if not user:
        return redirect(url_for("login"))
    db.release_request(rid, user["id"])
    return redirect(url_for("feed"))


@app.route("/request/<int:rid>/done", methods=["POST"])
def done_request(rid):
    user = role_required("worker")
    if not user:
        return redirect(url_for("login"))
    db.complete_request(rid, user["id"])
    return redirect(url_for("feed"))


# ---- JSON API (для мобильной версии / интеграций) ----

@app.route("/api/requests", methods=["GET"])
def api_requests():
    status = request.args.get("status")
    return jsonify(db.list_requests(status=status))


@app.route("/api/requests", methods=["POST"])
def api_create_request():
    data = request.get_json(silent=True) or {}
    required = ("client_name", "client_phone", "address")
    missing = [k for k in required if not str(data.get(k, "")).strip()]
    if data.get("type") not in ("install", "measure"):
        missing.append("type")
    if missing:
        return jsonify({"ok": False, "error": f"Не заполнено: {', '.join(missing)}"}), 400
    seller = db.get_default_seller()
    if not seller:
        return jsonify({"ok": False,
                        "error": "Нет ни одного продавца — сначала зарегистрируйте продавца на сайте"}), 400
    rid = db.create_request(
        seller_id=seller["id"],
        rtype=data["type"],
        client_name=data["client_name"].strip(),
        client_phone=data["client_phone"].strip(),
        address=data["address"].strip(),
        comment=str(data.get("comment", "")).strip(),
        date_preferred=str(data.get("date_preferred", "")).strip(),
        door_count=str(data.get("door_count", "1")).strip() or "1",
    )
    return jsonify({"ok": True, "id": rid}), 201


# ---------------------------------------------------------------- admin ----
# Админ-панель: полный доступ владельца к базе данных.

ADMIN_TABLES = ("users", "requests")


@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    login_ok, pass_ok = admin_credentials()
    error = None
    if request.method == "POST":
        if request.form.get("login") == login_ok and request.form.get("password") == pass_ok:
            session["is_admin"] = secrets.token_hex(8)
            return redirect(url_for("admin_db"))
        error = "Неверный логин или пароль администратора."
    if session.get("is_admin"):
        return redirect(url_for("admin_db"))
    return render_template("admin_login.html", error=error)


@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    return redirect(url_for("admin_login"))


def _table_data(table):
    """Безопасно читает таблицу: имена колонок — только из схемы БД, не из URL."""
    conn = db.get_conn()
    cols = [r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    rows = [dict(r) for r in conn.execute(f"SELECT * FROM {table} ORDER BY id DESC LIMIT 500").fetchall()]
    conn.close()
    # поле для отображения/редактирования пароля (в БД хранится хеш — показываем прочерк)
    if table == "users":
        for u in rows:
            u.pop("password_hash", None)
    return cols, rows


@app.route("/admin/db")
def admin_db():
    if not session.get("is_admin"):
        return redirect(url_for("admin_login"))
    tables = {t: _table_data(t) for t in ADMIN_TABLES}
    _, users_rows = tables["users"]
    _, req_rows = tables["requests"]
    stats = {
        "sellers": sum(1 for u in users_rows if u["role"] == "seller"),
        "workers": sum(1 for u in users_rows if u["role"] == "worker"),
        "new": sum(1 for r in req_rows if r["status"] == "new"),
        "taken": sum(1 for r in req_rows if r["status"] == "taken"),
        "done": sum(1 for r in req_rows if r["status"] == "done"),
    }
    return render_template("admin_db.html", tables=tables, stats=stats)


@app.route("/admin/edit/<table>/<int:row_id>", methods=["POST"])
def admin_edit(table, row_id):
    if not session.get("is_admin") or table not in ADMIN_TABLES:
        return abort_403_or_login()
    conn = db.get_conn()
    cols = [r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    conn.close()
    updates, params = [], []
    for col in cols:
        if col in ("id", "created_at", "updated_at", "password_hash"):
            continue
        if col in request.form:
            val = request.form[col].strip()
            if table == "users" and col == "password":
                continue  # пароль меняется отдельно ниже
            updates.append(f"{col} = ?")
            params.append(val if val != "" else None)
    # отдельная смена пароля пользователя
    if table == "users" and request.form.get("password_new", "").strip():
        updates.append("password_hash = ?")
        params.append(generate_password_hash(request.form["password_new"].strip()))
    if updates:
        now = datetime.now().isoformat(timespec="seconds")
        if table == "requests":
            updates.append("updated_at = ?")
            params.append(now)
        params.append(row_id)
        conn = db.get_conn()
        conn.execute(f"UPDATE {table} SET {', '.join(updates)} WHERE id = ?", params)
        conn.commit()
        conn.close()
    return redirect(url_for("admin_db"))


def abort_403_or_login():
    if not session.get("is_admin"):
        return redirect(url_for("admin_login"))
    return "Запрещено", 403


@app.route("/admin/delete/<table>/<int:row_id>", methods=["POST"])
def admin_delete(table, row_id):
    if not session.get("is_admin"):
        return redirect(url_for("admin_login"))
    if table not in ADMIN_TABLES:
        return "Неизвестная таблица", 400
    conn = db.get_conn()
    if table == "users":
        # сначала отвязываем заявки этого пользователя, потом удаляем
        conn.execute("UPDATE requests SET worker_id = NULL, status='new' WHERE worker_id = ?", (row_id,))
        conn.execute("DELETE FROM requests WHERE seller_id = ?", (row_id,))
        conn.execute("DELETE FROM users WHERE id = ?", (row_id,))
    else:
        conn.execute("DELETE FROM requests WHERE id = ?", (row_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_db"))


@app.route("/admin/export")
def admin_export():
    if not session.get("is_admin"):
        return redirect(url_for("admin_login"))
    return send_file(db.DB_PATH, as_attachment=True, download_name="dveri.db",
                     mimetype="application/x-sqlite3")


# ------------------------------------------------------------------- run ----

def _ensure_db():
    # Создаём таблицы при каждом старте — если удалить файл dveri.db,
    # сервер сам пересоздаст базу без ошибок.
    db.init_db()


_ensure_db()


@app.before_request
def _before():
    # Гарантируем наличие таблиц перед каждым запросом — даже если
    # файл dveri.db был удалён вручную во время работы сервера.
    db.init_db()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
