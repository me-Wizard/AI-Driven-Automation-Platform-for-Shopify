from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CartStatus, Event, EventType
from app.repository import CartRepository, EventRepository, SessionRepository
from app.schemas import CartItemOut, DecisionPayload, EventIn


class BehaviorService:

    def __init__(self, db: AsyncSession) -> None:
        self._events = EventRepository(db)
        self._cart = CartRepository(db)
        self._sessions = SessionRepository(db)
        self._db = db

    async def ingest(self, payload: EventIn) -> tuple[Event, bool]:
        idem_key = payload.derive_idempotency_key()
        if idem_key and await self._events.idempotency_key_exists(idem_key):
            existing = Event(
                user_id=payload.user_id,
                event_type=payload.event_type,
                product_id=payload.product_id,
                idempotency_key=idem_key,
            )
            return existing, True

        now = datetime.now(timezone.utc)
        event_timestamp = payload.timestamp if payload.timestamp is not None else now

        event = Event(
            user_id=payload.user_id,
            event_type=payload.event_type,
            product_id=payload.product_id,
            email=payload.email,
            timestamp=event_timestamp,
            idempotency_key=idem_key,
        )
        await self._events.save(event)
        await self._apply_cart_mutation(payload)
        cart_status = await self._derive_cart_status(payload.user_id, payload.event_type)
        await self._sessions.upsert(
            user_id=payload.user_id,
            email=payload.email,
            cart_status=cart_status,
            last_event_at=event_timestamp,
        )
        await self._db.commit()
        return event, False

    async def get_decision(self, user_id: str) -> DecisionPayload:
        session = await self._sessions.get(user_id)
        active_items = await self._cart.get_active_items(user_id)
        has_purchased = await self._events.has_purchase(user_id)

        cart_status = self._resolve_cart_status(session, active_items, has_purchased)

        return DecisionPayload(
            user_id=user_id,
            email=session.email if session else None,
            has_purchased=has_purchased,
            cart_status=cart_status,
            cart_items=[
                CartItemOut(
                    product_id=item.product_id,
                    quantity=item.quantity,
                    added_at=item.added_at,
                )
                for item in active_items
            ],
            cart_item_count=sum(item.quantity for item in active_items),
            last_event_at=session.last_event_at if session else None,
        )

    async def _apply_cart_mutation(self, payload: EventIn) -> None:
        match payload.event_type:
            case EventType.add_to_cart:
                await self._cart.add_or_increment(payload.user_id, payload.product_id)
            case EventType.remove_from_cart:
                await self._cart.decrement_or_remove(payload.user_id, payload.product_id)
            case EventType.purchase:
                await self._cart.mark_all_purchased(payload.user_id)
            case _:
                pass

    async def _derive_cart_status(self, user_id: str, event_type: EventType) -> CartStatus:
        if event_type == EventType.purchase:
            return CartStatus.purchased
        if event_type == EventType.checkout_started:
            return CartStatus.checkout_started
        active_items = await self._cart.get_active_items(user_id)
        return CartStatus.active if active_items else CartStatus.empty

    def _resolve_cart_status(self, session, active_items: list, has_purchased: bool) -> CartStatus:
        if has_purchased and not active_items:
            return CartStatus.purchased
        if active_items:
            if session and session.cart_status == CartStatus.checkout_started:
                return CartStatus.checkout_started
            return CartStatus.active
        return CartStatus.empty