import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.models import CartStatus, EventType


# ── Inbound ──────────────────────────────────────────────────────────────────

class EventIn(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=255)
    event_type: EventType
    product_id: str | None = Field(default=None, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    timestamp: datetime | None = None
    idempotency_key: str | None = Field(default=None, max_length=512)

    PRODUCT_REQUIRED_EVENTS: frozenset[EventType] = frozenset({
        EventType.product_view,
        EventType.add_to_cart,
        EventType.remove_from_cart,
    })

    @field_validator("user_id")
    @classmethod
    def strip_user_id(cls, v: str) -> str:
        return v.strip()

    @field_validator("timestamp", mode="before")
    @classmethod
    def default_timestamp(cls, v: Any) -> datetime:
        if v is None:
            return datetime.now(timezone.utc)
        return v

    @model_validator(mode="after")
    def validate_product_id_presence(self) -> "EventIn":
        if self.event_type in self.PRODUCT_REQUIRED_EVENTS and not self.product_id:
            raise ValueError(f"product_id is required for event type '{self.event_type}'")
        return self

    def derive_idempotency_key(self) -> str | None:
        """Auto-derive a key when not supplied, for natural dedup."""
        if self.idempotency_key:
            return self.idempotency_key
        if self.event_type in (EventType.product_view,):
            # Views are intentionally not deduped by default
            return None
        raw = f"{self.user_id}:{self.event_type}:{self.product_id}:{self.timestamp.isoformat()}"
        return hashlib.sha256(raw.encode()).hexdigest()


# ── Outbound ─────────────────────────────────────────────────────────────────

class EventOut(BaseModel):
    id: uuid.UUID
    user_id: str
    event_type: EventType
    product_id: str | None
    timestamp: datetime

    model_config = {"from_attributes": True}


class CartItemOut(BaseModel):
    product_id: str
    quantity: int
    added_at: datetime

    model_config = {"from_attributes": True}


class DecisionPayload(BaseModel):
    user_id: str
    email: str | None
    has_purchased: bool
    cart_status: CartStatus
    cart_items: list[CartItemOut]
    cart_item_count: int
    last_event_at: datetime | None
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EventResponse(BaseModel):
    event_id: uuid.UUID
    status: str
    message: str


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))