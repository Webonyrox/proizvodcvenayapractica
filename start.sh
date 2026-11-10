#!/bin/bash
# DveriApp — запуск сайта в одну команду (Mac / Linux)
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null; then
  echo "[ОШИБКА] Python не найден. Установите: https://www.python.org/downloads/"
  exit 1
fi

if [ ! -d ".venv" ]; then
  echo "[Шаг 1/3] Создание виртуального окружения..."
  python3 -m venv .venv
fi
source .venv/bin/activate

if ! python -c "import flask" 2>/dev/null; then
  echo "[Шаг 2/3] Установка зависимостей..."
  pip install --quiet flask pyngrok
else
  echo "[Шаг 2/3] Зависимости уже установлены."
fi

echo "[Шаг 3/3] Запуск сайта..."
python run.py
