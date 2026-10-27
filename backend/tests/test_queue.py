import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import func, select, update

from app.database import Database
from app.models import TelegramUpdate
from app.queue import UpdateQueue

pytestmark = pytest.mark.integration


async def test_duplicate_webhooks_are_stored_once(system):
    app, _ = system
    queue = UpdateQueue(app.state.database)
    await asyncio.gather(*[queue.enqueue(100, {"update_id": 100}) for _ in range(12)])
    async with app.state.database.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(TelegramUpdate)) == 1


async def test_two_workers_claim_distinct_jobs(system, settings):
    app, _ = system
    other_db = Database(settings.database_url)
    first, second = UpdateQueue(app.state.database), UpdateQueue(other_db)
    try:
        for index in range(10):
            await first.enqueue(index, {"update_id": index})
        jobs = await asyncio.gather(*[(first if index % 2 else second).claim() for index in range(10)])
        assert len({job.update_id for job in jobs if job}) == 10
        assert await first.claim() is None
    finally:
        await other_db.close()


async def test_crashed_lease_is_recovered_and_stale_worker_cannot_ack(system):
    app, _ = system
    queue = UpdateQueue(app.state.database)
    await queue.enqueue(1, {"update_id": 1})
    old = await queue.claim()
    async with app.state.database.sessions.begin() as session:
        await session.execute(update(TelegramUpdate).values(locked_until=func.now() - timedelta(seconds=1)))
    new = await queue.claim()
    assert new.update_id == old.update_id
    assert new.lease_token != old.lease_token
    await queue.complete(old)
    async with app.state.database.sessions() as session:
        row = await session.get(TelegramUpdate, 1)
        assert row.processed_at is None
    await queue.complete(new)
    assert await queue.claim() is None


async def test_failed_jobs_are_visible_after_retry_limit(system):
    app, _ = system
    queue = UpdateQueue(app.state.database, max_attempts=1)
    await queue.enqueue(1, {"update_id": 1})
    job = await queue.claim()
    await queue.fail(job, "TimeoutError")
    assert await queue.claim() is None
    async with app.state.database.sessions() as session:
        row = await session.get(TelegramUpdate, 1)
        assert row.failed_at is not None
        assert row.last_error == "TimeoutError"


async def test_last_attempt_crash_is_terminalized(system):
    app, _ = system
    queue = UpdateQueue(app.state.database, max_attempts=1)
    await queue.enqueue(1, {"update_id": 1})
    await queue.claim()
    async with app.state.database.sessions.begin() as session:
        await session.execute(update(TelegramUpdate).values(locked_until=func.now() - timedelta(seconds=1)))
    assert await queue.claim() is None
    async with app.state.database.sessions() as session:
        assert (await session.get(TelegramUpdate, 1)).failed_at is not None
