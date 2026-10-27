# Разработка без контейнеров приложения

Для этого варианта самостоятельно запустите PostgreSQL и MinIO. Их адреса указываются
в переменных окружения. В обычном быстром старте все эти шаги выполняет Docker Compose.

## Backend

Python 3.12. Команды из `backend`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
```

Настройте окружение, не добавляя секреты в tracked файлы:

- `DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@localhost:5432/catalog`
- `INTERNAL_API_TOKEN`: случайная строка не короче 32 символов
- `S3_ENDPOINT=http://localhost:9000`
- `S3_ACCESS_KEY`, `S3_SECRET_KEY` (секрет не короче 16 символов)
- `WEBHOOK_SECRET`: случайная строка не короче 32 символов
- `API_BASE_URL=http://localhost:8000`
- `BOT_TOKEN`, `ADMIN_IDS`, `PUBLIC_BASE_URL` при работе с Telegram

Можно положить отдельный `.env` в `backend` (он игнорируется Git).

```powershell
alembic upgrade head
python -m app.manage init-storage
uvicorn app.api:create_app --factory --port 8000 --reload
```

В отдельном терминале с тем же окружением:

```powershell
uvicorn app.bot:create_app --factory --port 8001
```

Для webhook требуется reverse proxy: `/telegram/webhook` → порт 8001, `/api` → 8000,
`/` → 3000. Для этого удобнее основной Compose.

## Frontend

Node.js 24. Из `frontend`:

```powershell
npm ci
$env:API_BASE_URL = "http://localhost:8000"
npm run dev
```

Откройте `http://localhost:3000`. Встроенный rewrite передаёт `/api` в FastAPI.

```powershell
npm run typecheck
npm run build
```

## Тесты backend локально

Только тесты без PostgreSQL:

```powershell
python -m pytest -q -m "not integration"
```

Для полного набора создайте **отдельную** БД `catalog_test`:

```powershell
$env:TEST_DATABASE_URL = "postgresql+asyncpg://USER:PASSWORD@localhost:5432/catalog_test"
python -m pytest -q
```

По умолчанию S3 в тестах эмулируется библиотекой Moto. Для настоящего MinIO задайте
`TEST_S3_ENDPOINT`, `TEST_S3_ACCESS_KEY`, `TEST_S3_SECRET_KEY`. Тесты создают отдельные
временные buckets. Они не обращаются к настоящему Telegram: его HTTP session заменена
тестовой реализацией. Живой сценарий в Telegram нужно проверить отдельно.

Python зависимости зафиксированы в `requirements.txt` / `requirements-dev.txt`,
Node зависимости — в `package-lock.json`. Файлы `.in` предназначены для осознанного
обновления зависимостей; после обновления повторно запускайте тесты и сборку.
