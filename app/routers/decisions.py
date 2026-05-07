from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import DecisionPayload
from app.service import BehaviorService

router = APIRouter(prefix="/decisions", tags=["Decisions"])


@router.get("/{user_id}", response_model=DecisionPayload)
async def get_user_decision(user_id: str, db: AsyncSession = Depends(get_db)):
    if not user_id.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="user_id must not be blank.",
        )
    service = BehaviorService(db)
    return await service.get_decision(user_id.strip())