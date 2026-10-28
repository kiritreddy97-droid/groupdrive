import logging
from typing import Protocol

log = logging.getLogger("groupdrive.otp")


class OtpSender(Protocol):
    def send(self, phone: str, code: str) -> None: ...


class ConsoleOtpSender:
    """Development only: writes the code to the log instead of sending an SMS."""

    def send(self, phone: str, code: str) -> None:
        log.warning("DEV OTP for %s is %s", phone, code)


class MemoryOtpSender:
    """Test double that remembers the last code sent to each phone."""

    def __init__(self) -> None:
        self.codes: dict[str, str] = {}

    def send(self, phone: str, code: str) -> None:
        self.codes[phone] = code


def build_sender(name: str) -> OtpSender:
    if name == "console":
        return ConsoleOtpSender()
    raise RuntimeError(f"unknown OTP_SENDER {name!r}; implement the OtpSender interface for your SMS provider")
