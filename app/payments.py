from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4


@dataclass(frozen=True)
class PaymentRequest:
    provider: str
    reference: str


class PaymentGateway(Protocol):
    def create_payment(self, order_id: int, amount: str) -> PaymentRequest: ...


class DemoPaymentGateway:
    def create_payment(self, order_id: int, amount: str) -> PaymentRequest:
        return PaymentRequest(provider="demo", reference=f"demo-{order_id}-{uuid4().hex}")


def get_payment_gateway() -> PaymentGateway:
    return DemoPaymentGateway()
