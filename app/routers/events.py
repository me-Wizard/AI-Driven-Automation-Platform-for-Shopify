from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import EventIn, EventResponse
from app.service import BehaviorService

router = APIRouter(prefix="/events", tags=["Events"])


@router.post("", response_model=EventResponse, status_code=status.HTTP_202_ACCEPTED)
async def ingest_event(payload: EventIn, db: AsyncSession = Depends(get_db)):
    service = BehaviorService(db)
    try:
        event, is_duplicate = await service.ingest(payload)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Event processing failed.",
        ) from exc

    if is_duplicate:
        return EventResponse(
            event_id=event.id if event.id else __import__("uuid").uuid4(),
            status="duplicate",
            message="Event already processed; idempotency key matched.",
        )

    return EventResponse(
        event_id=event.id,
        status="accepted",
        message="Event ingested successfully.",
    )