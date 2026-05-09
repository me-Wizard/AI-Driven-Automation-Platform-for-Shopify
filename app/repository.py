from datetime import datetime, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CartItem, CartStatus, Event, EventType, UserSession


class EventRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def save(self, event: Event) -> Event:
        self._db.add(event)
        await self._db.flush()
        return event

    async def idempotency_key_exists(self, key: str) -> bool:
        result = await self._db.execute(
            select(Event.id).where(Event.idempotency_key == key).limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def get_recent_events(self, user_id: str, limit: int = 50) -> list[Event]:
        result = await self._db.execute(
            select(Event)
            .where(Event.user_id == user_id)
            .order_by(Event.timestamp.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def has_purchase(self, user_id: str) -> bool:
        result = await self._db.execute(
            select(Event.id)
            .where(Event.user_id == user_id, Event.event_type == EventType.purchase)
            .limit(1)
        )
        return result.scalar_one_or_none() is not None


class CartRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def add_or_increment(self, user_id: str, product_id: str) -> None:
        stmt = (
            pg_insert(CartItem)
            .values(user_id=user_id, product_id=product_id, quantity=1)
            .on_conflict_do_update(
                constraint="uq_cart_user_product",
                set_={"quantity": CartItem.quantity + 1, "is_purchased": False,
                      "updated_at": datetime.now(timezone.utc)},
            )
        )
        await self._db.execute(stmt)

    async def decrement_or_remove(self, user_id: str, product_id: str) -> None:
        result = await self._db.execute(
            select(CartItem).where(
                CartItem.user_id == user_id,
                CartItem.product_id == product_id,
                CartItem.is_purchased == False,  # noqa: E712
            )
        )
        item = result.scalar_one_or_none()
        if item is None:
            return
        if item.quantity <= 1:
            await self._db.delete(item)
        else:
            item.quantity -= 1

    async def mark_all_purchased(self, user_id: str) -> None:
        await self._db.execute(
            update(CartItem)
            .where(CartItem.user_id == user_id, CartItem.is_purchased == False)  # noqa: E712
            .values(is_purchased=True)
        )

    async def get_active_items(self, user_id: str) -> list[CartItem]:
        result = await self._db.execute(
            select(CartItem).where(
                CartItem.user_id == user_id,
                CartItem.is_purchased == False,  # noqa: E712
            )
        )
        return list(result.scalars().all())


class SessionRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def upsert(
        self,
        user_id: str,
        email: str | None,
        cart_status: CartStatus,
        last_event_at: datetime,
    ) -> None:
        stmt = (
            pg_insert(UserSession)
            .values(
                user_id=user_id,
                email=email,
                cart_status=cart_status,
                last_event_at=last_event_at,
            )
            .on_conflict_do_update(
                index_elements=["user_id"],
                set_={
                    "cart_status": cart_status,
                    "last_event_at": last_event_at,
                    "updated_at": datetime.now(timezone.utc),
                    # Preserve email if already set
                    "email": (
                        pg_insert(UserSession)
                        .excluded.email
                        if email is not None
                        else UserSession.email
                    ),
                },
            )
        )
        await self._db.execute(stmt)

    async def get(self, user_id: str) -> UserSession | None:
        result = await self._db.execute(
            select(UserSession).where(UserSession.user_id == user_id)
        )
        return result.scalar_one_or_none()