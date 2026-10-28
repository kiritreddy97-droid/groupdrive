import os
import tempfile

# set TEST_DATABASE_URL to run the whole suite against Postgres (CI does)
os.environ["DATABASE_URL"] = os.getenv("TEST_DATABASE_URL") or f"sqlite:///{tempfile.mkdtemp()}/test.db"
os.environ["APP_ENV"] = "test"
os.environ["ADMIN_PHONES"] = "9999999999"
os.environ["PAYMENT_WEBHOOK_SECRET"] = "whsec_test_secret"
os.environ["RATE_LIMIT_PER_MINUTE"] = "10000"

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app import ratelimit  # noqa: E402
from app.db import Base  # noqa: E402
from app.db import engine as app_engine
from app.deps import otp_sender_dep, payments_dep  # noqa: E402
from app.main import app  # noqa: E402
from app.otp import MemoryOtpSender  # noqa: E402
from app.payments import FakeGateway  # noqa: E402


@pytest.fixture
def db():
    """In-memory database for service-level tests."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False)()
    yield session
    session.close()


@pytest.fixture
def payments():
    return FakeGateway()


@pytest.fixture(scope="session")
def migrated_engine():
    """The app's own database, built by the real Alembic migrations rather than create_all."""
    command.upgrade(Config("alembic.ini"), "head")
    return app_engine


@pytest.fixture
def client(migrated_engine, payments):
    """API client against the migrated database, with a clean slate, a capturing OTP sender and a fake gateway."""
    with migrated_engine.begin() as conn:
        names = ", ".join(t.name for t in Base.metadata.sorted_tables)
        if conn.dialect.name == "postgresql":
            conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
        else:
            conn.execute(text("UPDATE campaigns SET winning_offer_id = NULL"))
            for table in reversed(Base.metadata.sorted_tables):
                conn.execute(table.delete())
    ratelimit.limiter.reset()
    sender = MemoryOtpSender()
    app.dependency_overrides[otp_sender_dep] = lambda: sender
    app.dependency_overrides[payments_dep] = lambda: payments
    with TestClient(app) as c:
        c.otp_sender = sender
        yield c
    app.dependency_overrides.clear()
