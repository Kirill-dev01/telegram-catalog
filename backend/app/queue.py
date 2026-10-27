from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert

from app.database import Database
from app.models import TelegramUpdate


@dataclass(frozen=True)
class Job:
    update_id: int
    payload: dict
    attempts: int
    lease_token: UUID


class UpdateQueue:
    def __init__(self, database: Database, lease_seconds: int = 120, max_attempts: int = 8):
        self.database = database
        self.lease_seconds = lease_seconds
        self.max_attempts = max_attempts

    async def enqueue(self, update_id: int, payload: dict) -> None:
        async with self.database.sessions.begin() as session:
            await session.execute(insert(TelegramUpdate).values(
                update_id=update_id, payload=payload,
            ).on_conflict_do_nothing(index_elements=[TelegramUpdate.update_id]))

    async def claim(self) -> Job | None:
        async with self.database.sessions.begin() as session:
            now = func.now()
            # Terminalize leases abandoned during their last permitted attempt.
            await session.execute(update(TelegramUpdate).where(
                TelegramUpdate.processed_at.is_(None), TelegramUpdate.failed_at.is_(None),
                TelegramUpdate.attempts >= self.max_attempts,
                or_(TelegramUpdate.locked_until.is_(None), TelegramUpdate.locked_until < now),
            ).values(failed_at=now, locked_until=None, lease_token=None, last_error="Attempts exhausted"))
            candidate = select(TelegramUpdate.update_id).where(
                TelegramUpdate.processed_at.is_(None), TelegramUpdate.failed_at.is_(None),
                TelegramUpdate.available_at <= now, TelegramUpdate.attempts < self.max_attempts,
                or_(TelegramUpdate.locked_until.is_(None), TelegramUpdate.locked_until < now),
            ).order_by(TelegramUpdate.update_id).limit(1).with_for_update(skip_locked=True).scalar_subquery()
            lease_token = uuid4()
            row = (await session.execute(update(TelegramUpdate).where(
                TelegramUpdate.update_id == candidate,
            ).values(
                lease_token=lease_token, locked_until=now + timedelta(seconds=self.lease_seconds),
                attempts=TelegramUpdate.attempts + 1,
            ).returning(TelegramUpdate))).scalar_one_or_none()
            if row is None:
                return None
            return Job(row.update_id, row.payload, row.attempts, lease_token)

    @staticmethod
    def owned(job: Job):
        return and_(TelegramUpdate.update_id == job.update_id,
                    TelegramUpdate.lease_token == job.lease_token,
                    TelegramUpdate.processed_at.is_(None))

    async def complete(self, job: Job) -> None:
        async with self.database.sessions.begin() as session:
            await session.execute(update(TelegramUpdate).where(self.owned(job)).values(
                processed_at=func.now(), locked_until=None, lease_token=None,
                payload={}, last_error=None,
            ))

    async def fail(self, job: Job, error_name: str, retry_after: int | None = None) -> None:
        delay = max(min(2 ** job.attempts, 300), retry_after or 0)
        async with self.database.sessions.begin() as session:
            await session.execute(update(TelegramUpdate).where(self.owned(job)).values(
                locked_until=None, lease_token=None, last_error=error_name[:100],
                available_at=func.now() + timedelta(seconds=delay),
                failed_at=func.now() if job.attempts >= self.max_attempts else None,
            ))
