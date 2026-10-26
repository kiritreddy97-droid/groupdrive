import os
from dataclasses import dataclass, field


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    app_env: str = field(default_factory=lambda: os.getenv("APP_ENV", "dev"))
    jwt_secret: str = field(default_factory=lambda: os.getenv("JWT_SECRET", ""))
    jwt_ttl_minutes: int = field(default_factory=lambda: int(os.getenv("JWT_TTL_MINUTES", "120")))
    otp_ttl_seconds: int = field(default_factory=lambda: int(os.getenv("OTP_TTL_SECONDS", "300")))
    otp_max_attempts: int = field(default_factory=lambda: int(os.getenv("OTP_MAX_ATTEMPTS", "5")))
    otp_sender: str = field(default_factory=lambda: os.getenv("OTP_SENDER", "console"))
    admin_phones: frozenset[str] = field(
        default_factory=lambda: frozenset(p.strip() for p in os.getenv("ADMIN_PHONES", "").split(",") if p.strip())
    )
    payment_provider: str = field(default_factory=lambda: os.getenv("PAYMENT_PROVIDER", "fake"))
    payment_webhook_secret: str = field(default_factory=lambda: os.getenv("PAYMENT_WEBHOOK_SECRET", ""))
    deposit_rupees: int = field(default_factory=lambda: int(os.getenv("DEPOSIT_RUPEES", "1000")))
    success_fee_rupees: int = field(default_factory=lambda: int(os.getenv("SUCCESS_FEE_RUPEES", "6000")))
    rate_limit_enabled: bool = field(default_factory=lambda: _bool("RATE_LIMIT_ENABLED", True))
    rate_limit_per_minute: int = field(default_factory=lambda: int(os.getenv("RATE_LIMIT_PER_MINUTE", "120")))
    trust_proxy: bool = field(default_factory=lambda: _bool("TRUST_PROXY", False))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    def validate(self) -> None:
        """Fail fast on unsafe production configuration."""
        if not self.is_production:
            return
        problems = []
        if len(self.jwt_secret) < 32:
            problems.append("JWT_SECRET must be set to at least 32 characters")
        if not self.payment_webhook_secret:
            problems.append("PAYMENT_WEBHOOK_SECRET must be set")
        if self.otp_sender == "console":
            problems.append("OTP_SENDER=console is not allowed in production; implement and select an SMS sender")
        if self.payment_provider == "fake":
            problems.append("PAYMENT_PROVIDER=fake is not allowed in production")
        if problems:
            raise RuntimeError("unsafe production configuration: " + "; ".join(problems))


def get_settings() -> Settings:
    return Settings()
