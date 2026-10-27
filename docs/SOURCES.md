# Официальная документация

Проверена при подготовке проекта 26 октября 2026 года.

- Next.js App Router: https://nextjs.org/docs/app
- Self-hosting и несколько экземпляров: https://nextjs.org/docs/app/guides/self-hosting
- FastAPI lifespan: https://fastapi.tiangolo.com/advanced/events/
- aiogram 3 webhook: https://docs.aiogram.dev/en/latest/dispatcher/webhook.html
- Telegram Bot API, setWebhook: https://core.telegram.org/bots/api#setwebhook
- Telegram Mini Apps: https://core.telegram.org/bots/webapps
- PostgreSQL SELECT / SKIP LOCKED: https://www.postgresql.org/docs/current/sql-select.html
- SQLAlchemy asyncio: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
- Alembic: https://alembic.sqlalchemy.org/en/latest/
- MinIO Community upstream: https://github.com/minio/minio
- Зафиксированный release MinIO: https://github.com/minio/minio/releases/tag/RELEASE.2025-10-15T17-29-55Z
- Nginx upstream: https://nginx.org/en/docs/http/ngx_http_upstream_module.html
- Docker Compose: https://docs.docker.com/compose/
- Cloudflare development tunnel: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/trycloudflare/

MinIO Community upstream сообщает о переходе к распространению исходников.
Поэтому образ в этом проекте собирается из фиксированной версии исходного кода,
а не полагается на плавающий `minio/minio:latest`.
