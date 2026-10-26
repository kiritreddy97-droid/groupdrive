"""Deposit handling behind an interface so a licensed payment aggregator can be plugged in later.

The platform never touches funds directly: `hold` places the token deposit in the aggregator's escrow/nodal
account, `refund` returns it, `apply` releases it towards the buyer's purchase with the winning dealer.
All calls are idempotent on the reference they return.
"""
import itertools
from dataclasses import dataclass
from typing import Protocol


class PaymentError(Exception):
    pass


@dataclass(frozen=True)
class HoldResult:
    ref: str
    status: str  # "held" (funds confirmed now) or "pending" (a webhook will confirm)


class PaymentGateway(Protocol):
    def hold(self, membership_id: int, amount_rupees: int) -> HoldResult: ...
    def refund(self, ref: str) -> None: ...
    def apply(self, ref: str) -> None: ...


class FakeGateway:
    """Deterministic in-memory gateway for dev and tests. Holds succeed immediately unless `pending` is set."""

    def __init__(self, pending: bool = False) -> None:
        self.pending = pending
        self.fail_refunds = False
        self.calls: list[tuple[str, str]] = []
        self._ids = itertools.count(1)

    def hold(self, membership_id: int, amount_rupees: int) -> HoldResult:
        ref = f"fake_{next(self._ids)}_{membership_id}"
        self.calls.append(("hold", ref))
        return HoldResult(ref, "pending" if self.pending else "held")

    def refund(self, ref: str) -> None:
        if self.fail_refunds:
            raise PaymentError("fake gateway refund failure")
        self.calls.append(("refund", ref))

    def apply(self, ref: str) -> None:
        self.calls.append(("apply", ref))


def build_gateway(provider: str) -> PaymentGateway:
    if provider == "fake":
        return FakeGateway()
    raise RuntimeError(f"unknown PAYMENT_PROVIDER {provider!r}; implement PaymentGateway for your aggregator")
