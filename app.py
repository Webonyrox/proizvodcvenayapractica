"""
DveriApp — сервис заявок на установку и замер дверей.

Продавцы дверей подают заявку (установка / замер),
установщики и замерщики видят заявку: адрес, телефон клиента, тип работы.

Запуск:
    python app.py
Сайт: http://localhost:5000
"""

from datetime import datetime

from flask import Flask, jsonify, redirect, render_template, request, url_for
from werkzeug.security import check_password_hash, generate_password_hash

import db

app = Flask(__name__)
app.config["SECRET_KEY"] = "dveri-app-secret-change-me"


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


# ------------------------------------------------------------------- run ----

db.init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
