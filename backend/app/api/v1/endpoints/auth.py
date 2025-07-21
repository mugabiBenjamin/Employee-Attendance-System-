from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.user import UserAuth, Token
from app.services.auth_service import login_for_access_token, refresh_access_token
from app.api.deps import get_db_session

router = APIRouter()

@router.post("/token", response_model=Token)
async def login(user_auth: UserAuth, db: AsyncSession = Depends(get_db_session)):
    return await login_for_access_token(db, user_auth)

@router.post("/refresh", response_model=Token)
async def refresh_token(refresh_token: str, db: AsyncSession = Depends(get_db_session)):
    return await refresh_access_token(db, refresh_token)