# DveriApp — заявки на установку и замер дверей

Продавцы дверей подают заявку (установка / замер проёма),
установщики и замерщики получают заявку с адресом и телефоном клиента.

## Быстрый запуск (Windows)

1. Установите Python: https://www.python.org/downloads/
   **Обязательно отметьте галочку "Add python.exe to PATH" при установке!**
2. Откройте папку проекта в VS Code (Файл → Открыть папку).
3. Откройте терминал в VS Code: меню Terminal → New Terminal (или Ctrl+`).
4. Выполните две команды по очереди:

```bash
pip install -r requirements.txt
python app.py
```

5. Откройте в браузере: http://localhost:5000

## База данных PostgreSQL (постоянная, сетевая)

Сайт работает с PostgreSQL, если указан адрес базы одним из двух способов:

**Способ 1 — config.json** (рядом с app.py):
```json
{
  "postgres_url": "postgresql://логин:пароль@хост:5432/имя_базы?sslmode=require"
}
```

**Способ 2 — переменная окружения:**
```bash
set DATABASE_URL=postgresql://логин:пароль@хост:5432/имя_базы   (Windows)
export DATABASE_URL="postgresql://логин:пароль@хост:5432/имя_базы"   (Mac/Linux)
```

Если адрес не указан — сайт автоматически использует локальный SQLite (dveri.db).

Где взять бесплатный PostgreSQL в интернете:
- Neon: https://neon.tech (кнопка «Get started free» → скопировать Connection string)
- Supabase: https://supabase.com (Project Settings → Database → Connection string)

Перенос старых данных из SQLite в PostgreSQL:
```bash
python migrate_sqlite_to_postgres.py
```

## Как пользоваться

1. Зарегистрируйтесь дважды: один раз как «Продавец», второй — как «Мастер».
2. Продавец: «Новая заявка» → заполняет адрес, телефон клиента, тип работы.
3. Мастер: «Лента заявок» → видит адрес и телефон → «Взять в работу» → «Выполнено».

## Структура

- app.py — сервер (Flask)
- db.py — слой БД SQLite (создаётся автоматически как dveri.db)
- db_pg.py — слой БД PostgreSQL (активируется, когда задан postgres_url/DATABASE_URL)
- migrate_sqlite_to_postgres.py — перенос данных SQLite → PostgreSQL
- templates/ — страницы сайта
- static/style.css — оформление

№№ Альтернативный способ запуска который я нашел в интернете 
заходишь в папку с проектом 
нажимаешь на пкм терминал 
pip install -r requirements.txt
python app.py
после того как ввел это в терминал выводит айпи который позволяет 
