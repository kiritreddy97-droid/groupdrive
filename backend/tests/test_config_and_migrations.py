import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from app import security
from app.config import Settings
from app.db import Base


def test_models_match_migrations(migrated_engine):
    with migrated_engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == [], "models changed without an Alembic migration: run `alembic revision --autogenerate`"


def test_production_refuses_unsafe_config():
    with pytest.raises(RuntimeError) as e:
        Settings(app_env="production", jwt_secret="short", payment_webhook_secret="").validate()
    for expected in ("JWT_SECRET", "PAYMENT_WEBHOOK_SECRET", "OTP_SENDER", "PAYMENT_PROVIDER"):
        assert expected in str(e.value)
    Settings(app_env="dev").validate()
    Settings(app_env="production", jwt_secret="x" * 40, payment_webhook_secret="s", otp_sender="sms",
             payment_provider="aggregator").validate()


def test_password_and_phone_helpers():
    h = security.hash_password("hunter2hunter2")
    assert security.verify_password("hunter2hunter2", h) and not security.verify_password("x", h)
    assert not security.verify_password("x", "garbage")
    assert security.normalize_phone("+91 98765-43210") == "9876543210"
    with pytest.raises(ValueError):
        security.normalize_phone("1234567890")
