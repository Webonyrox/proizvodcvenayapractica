"""
Единая точка запуска DveriApp — «сайт по одной кнопке».

Делает три вещи:
  1. Запускает сам сайт (Flask) на http://localhost:5000
  2. Пробует автоматически создать ПУБЛИЧНУЮ ссылку в интернете (ngrok),
     чтобы друзья могли зайти на сайт с любого устройства.
  3. Открывает админ-панель с базой данных:
       http://localhost:5000/admin        — вход (логин admin / пароль из config.json)
       http://localhost:5000/admin/db     — просмотр таблиц, изменение и удаление строк
       http://localhost:5000/admin/export — скачивание дампа базы данных (SQLite-файл или SQL для PostgreSQL)

Запуск вручную:  python run.py
Или двойным кликом: start.bat (Windows) / ./start.sh (Mac, Linux)
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

BASE = Path(__file__).resolve().parent
CONFIG_FILE = BASE / "config.json"


def load_config() -> dict:
    """Читает config.json; если файла нет — создаёт со значениями по умолчанию."""
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            print(f"[!] Не удалось прочитать config.json ({exc}), использую значения по умолчанию.")
    cfg = {
        "admin_login": "admin",
        "admin_password": "admin123",
        "ngrok_authtoken": "",  # необязательно: без него ссылка тоже работает
    }
    CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return cfg


def port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def start_tunnel(port: int):
    """Пытается поднять публичную ссылку. Сначала cloudflared (без регистрации),
    затем ngrok (нужен бесплатный аккаунт). Возвращает URL или None."""
    url = _tunnel_cloudflared(port)
    if url:
        return url
    return _tunnel_ngrok(port)


def _tunnel_cloudflared(port: int):
    """Бесплатный туннель Cloudflare — без установки и без регистрации."""
    import re as _re

    exe = shutil.which("cloudflared") or str(BASE / "cloudflared.exe")
    if not Path(exe).exists():
        # скачиваем однократно (~10 МБ)
        print("[i] Скачиваю cloudflared для создания ссылки друзьям (один раз, ~10 МБ)...")
        try:
            import urllib.request
            link = ("https://github.com/cloudflare/cloudflared/releases/latest/download/"
                    "cloudflared-windows-amd64.exe" if sys.platform == "win32" else
                    "https://github.com/cloudflare/cloudflared/releases/latest/download/"
                    "cloudflared-linux-amd64")
            urllib.request.urlretrieve(link, BASE / ("cloudflared.exe" if sys.platform == "win32" else "cloudflared"))
            exe = str(BASE / ("cloudflared.exe" if sys.platform == "win32" else "cloudflared"))
            if sys.platform != "win32":
                os.chmod(exe, 0o755)
        except Exception as exc:  # noqa: BLE001
            print(f"[i] Не удалось скачать cloudflared: {exc}")
            return None

    try:
        proc = subprocess.Popen([exe, "tunnel", "--url", f"http://localhost:{port}"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    except Exception as exc:  # noqa: BLE001
        print(f"[i] cloudflared не запустился: {exc}")
        return None

    result = {}

    def _reader():
        while True:
            line = proc.stderr.readline()
            if not line:
                break
            text = line.decode(errors="ignore")
            m = _re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", text)
            if m and "url" not in result:
                result["url"] = m.group(0)

    threading.Thread(target=_reader, daemon=True).start()
    for _ in range(40):  # ждём до 20 секунд
        if "url" in result:
            TUNNEL_PROC.append(proc)
            return result["url"]
        if proc.poll() is not None:
            break
        time.sleep(0.5)
    try:
        proc.kill()
    except Exception:  # noqa: BLE001
        pass
    print("[i] Cloudflare-туннель не поднялся, пробую ngrok...")
    return None


TUNNEL_PROC = []  # держим ссылку на процесс туннеля, чтобы не собрать его GC


def _tunnel_ngrok(port: int):
    cfg = load_config()
    try:
        from pyngrok import ngrok, conf
    except ImportError:
        print("[i] Публичную ссылку создать не удалось — сайт доступен только на этом компьютере.")
        print("    Друзья смогут зайти, если вы кинете им ссылку через любой из сервисов-туннелей.")
        return None

    try:
        token = (cfg.get("ngrok_authtoken") or "").strip()
        if token:
            conf.get_default().auth_token = token
        public = ngrok.connect(port, "http")
        return public.public_url
    except Exception as exc:  # noqa: BLE001
        print(f"[i] Не удалось создать ссылку через ngrok: {exc}")
        print("    Сайт всё равно работает локально: http://localhost:5000")
        print("    Совет: зарегистрируйтесь бесплатно на https://dashboard.ngrok.com/")
        print("    и вставьте свой authtoken в файл config.json (поле ngrok_authtoken).")
        return None


def main() -> None:
    cfg = load_config()
    port = 5000

    if not port_is_free(port):
        print(f"[!] Порт {port} уже занят. Возможно, сайт уже запущен — откройте http://localhost:{port}")
        print("    Если хотите перезапустить — закройте старое окно с сайтом и запустите снова.")
        input("Нажмите Enter для выхода...")
        return

    print("=" * 56)
    print("  DVERIAPP — запуск...")
    print("=" * 56)

    # Фоновый поток: ждём подъёма сервера и открываем браузер
    def _open_browser():
        for _ in range(40):
            if not port_is_free(port):
                break
            time.sleep(0.25)
        try:
            webbrowser.open(f"http://localhost:{port}")
        except Exception:  # noqa: BLE001
            pass

    threading.Thread(target=_open_browser, daemon=True).start()

    tunnel_url = None
    if "--no-tunnel" not in sys.argv:
        tunnel_url = start_tunnel(port)

    print("-" * 56)
    print(f"  Сайт локально:      http://localhost:{port}")
    if tunnel_url:
        print(f"  Ссылка для друзей:  {tunnel_url}")
    print(f"  База данных (админ): http://localhost:{port}/admin")
    print(f"    логин: {cfg['admin_login']}   пароль: {cfg['admin_password']}")
    print("  (пароль можно поменять в файле config.json)")
    print("-" * 56)
    print("  Остановка сайта: Ctrl+C или закрыть окно.\n")

    # Импорт здесь, чтобы сообщения выше появились до запуска Flask
    from app import app
    import db

    db.init_db()
    try:
        app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)
    except KeyboardInterrupt:
        print("\nСайт остановлен.")


if __name__ == "__main__":
    main()
