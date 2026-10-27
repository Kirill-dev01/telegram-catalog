"""Create local secrets without overwriting an existing environment file."""
import os
import secrets
from pathlib import Path

path = Path(__file__).resolve().parents[1] / ".env"
if path.exists():
    raise SystemExit(".env already exists; left unchanged.")
content = "\n".join([
    "# Local credentials. Never commit this file.",
    f"POSTGRES_PASSWORD={secrets.token_hex(24)}",
    f"INTERNAL_API_TOKEN={secrets.token_hex(32)}",
    "S3_ACCESS_KEY=catalog-admin",
    f"S3_SECRET_KEY={secrets.token_hex(32)}",
    f"WEBHOOK_SECRET={secrets.token_hex(32)}",
    "BOT_TOKEN=", "ADMIN_IDS=", "PUBLIC_BASE_URL=http://localhost:8080", "PORT=8080", "",
])
descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
    stream.write(content)
print("Created .env. Secrets were not printed. You can now start Docker Compose.")
