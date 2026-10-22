"""
Self-contained test fixtures: SQLite (aiosqlite) instead of Postgres, an
in-memory Redis stub, and OTP capture — so `pytest` runs with no services.
"""

import os
import tempfile
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import BigInteger, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from app.core.deps import get_redis
from app.db.session import Base, get_db
from app.main import app
from app.models.models import DoctorProfile, Facility, PatientProfile, User, UserRole


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):
    return "JSON"


@compiles(BigInteger, "sqlite")
def _bigint_on_sqlite(type_, compiler, **kw):
    # SQLite only autoincrements INTEGER PRIMARY KEY columns.
    return "INTEGER"


class FakeRedis:
    def __init__(self):
        self.store = {}

    async def incr(self, key):
        self.store[key] = int(self.store.get(key, 0)) + 1
        return self.store[key]

    async def expire(self, key, seconds):
        return True

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ex=None, **kw):
        self.store[key] = value
        return True

    async def setex(self, key, seconds, value):
        self.store[key] = value
        return True

    async def delete(self, *keys):
        for k in keys:
            self.store.pop(k, None)
        return len(keys)


@pytest.fixture
async def session_factory():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()
    os.remove(path)


@pytest.fixture
async def client(session_factory, monkeypatch):
    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    fake_redis = FakeRedis()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = lambda: fake_redis

    sent = {}

    async def capture_otp(phone, otp):
        sent[phone] = otp

    monkeypatch.setattr("app.api.v1.endpoints.auth.send_otp_sms", capture_otp)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
        c.sent_otps = sent
        yield c
    app.dependency_overrides.clear()


async def login(client, session_factory, phone, name, role, facility_id=None):
    """Create a user with `role` and log them in through the real OTP flow."""
    async with session_factory() as s:
        s.add(User(phone=phone, name=name, role=role, facility_id=facility_id))
        await s.commit()
    r = await client.post("/api/v1/auth/otp/request", json={"phone": phone})
    assert r.status_code == 200, r.text
    r = await client.post("/api/v1/auth/otp/verify", json={"phone": phone, "otp": client.sent_otps[phone]})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
async def auth_headers(client, session_factory):
    return await login(client, session_factory, "+919988776655", "Test CHW", UserRole.chw)


class World:
    """A small pilot deployment: two facilities, staff, and two patients."""


@pytest.fixture
async def world(client, session_factory):
    w = World()
    async with session_factory() as s:
        w.fac_a, w.fac_b = Facility(id=uuid.uuid4(), name="PHC A"), Facility(id=uuid.uuid4(), name="PHC B")
        s.add_all([w.fac_a, w.fac_b])
        await s.commit()

    w.admin = await login(client, session_factory, "+911000000001", "Admin", UserRole.admin)
    w.chw = await login(client, session_factory, "+911000000002", "CHW A", UserRole.chw, w.fac_a.id)
    w.chw_b = await login(client, session_factory, "+911000000003", "CHW B", UserRole.chw, w.fac_b.id)
    w.doctor = await login(client, session_factory, "+911000000004", "Dr A", UserRole.doctor)
    w.pat1 = await login(client, session_factory, "+911000000005", "Asha", UserRole.patient)
    w.pat2 = await login(client, session_factory, "+911000000006", "Ravi", UserRole.patient)

    async with session_factory() as s:
        users = {u.phone: u for u in (await s.execute(select(User))).scalars()}
        w.doctor_profile = DoctorProfile(id=uuid.uuid4(), user_id=users["+911000000004"].id)
        w.p1 = PatientProfile(id=uuid.uuid4(), user_id=users["+911000000005"].id, facility_id=w.fac_a.id)
        w.p2 = PatientProfile(id=uuid.uuid4(), user_id=users["+911000000006"].id, facility_id=w.fac_b.id)
        s.add_all([w.doctor_profile, w.p1, w.p2])
        await s.commit()
    return w
