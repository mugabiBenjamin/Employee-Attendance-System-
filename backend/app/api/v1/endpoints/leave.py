from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from datetime import date
from app.schemas.leave import LeaveRequestCreate, LeaveRequestUpdate, LeaveRequestOut, LeaveBalanceOut
from app.services.leave_service import create_leave_request, update_leave_request, get_leave_request_by_id, get_user_leave_requests, get_leave_balance
from app.api.deps import get_db_session, get_current_active_user, get_current_manager_user
from app.models.user import User
from app.core.config import settings

router = APIRouter()

@router.post("/", response_model=LeaveRequestOut, status_code=status.HTTP_201_CREATED)
async def create_new_leave_request(
    leave_request: LeaveRequestCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user)
):
    if leave_request.user_id != current_user.user_id and not await is_manager_or_hr(db, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to create leave request for this user")
    return await create_leave_request(db, leave_request, current_user)

@router.put("/{leave_id}", response_model=LeaveRequestOut)
async def update_leave_request(
    leave_id: int,
    leave_update: LeaveRequestUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user)
):
    leave_request = await get_leave_request_by_id(db, leave_id, current_user)
    if not leave_request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Leave request not found")
    if leave_request.user_id != current_user.user_id and not await is_manager_or_hr(db, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update this leave request")
    return await update_leave_request(db, leave_id, leave_update, current_user)

@router.get("/{leave_id}", response_model=LeaveRequestOut)
async def get_leave_request(
    leave_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user)
):
    leave_request = await get_leave_request_by_id(db, leave_id, current_user)
    if not leave_request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Leave request not found")
    if leave_request.user_id != current_user.user_id and not await is_manager_or_hr(db, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view this leave request")
    return leave_request

@router.get("/user/{user_id}", response_model=List[LeaveRequestOut])
async def get_leave_request_history(
    user_id: int,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    skip: int = 0,
    limit: int = settings.DEFAULT_PAGE_SIZE,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user)
):
    if user_id != current_user.user_id and not await is_manager_or_hr(db, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view this user's leave history")
    return await get_user_leave_requests(db, user_id, start_date, end_date, skip, limit)

@router.get("/balance/{user_id}", response_model=List[LeaveBalanceOut])
async def get_user_leave_balance(
    user_id: int,
    year: Optional[int] = None,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_active_user)
):
    if user_id != current_user.user_id and not await is_manager_or_hr(db, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view this user's leave balance")
    return await get_leave_balance(db, user_id, year)

@router.post("/{leave_id}/approve", response_model=LeaveRequestOut)
async def approve_leave_request(
    leave_id: int,
    comments: Optional[str] = None,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_manager_user)
):
    leave_request = await get_leave_request_by_id(db, leave_id, current_user)
    if not leave_request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Leave request not found")
    leave_update = LeaveRequestUpdate.model_construct(status="approved", comments=comments)
    return await update_leave_request(db, leave_id, leave_update, current_user)

@router.post("/{leave_id}/reject", response_model=LeaveRequestOut)
async def reject_leave_request(
    leave_id: int,
    comments: Optional[str] = None,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_manager_user)
):
    leave_request = await get_leave_request_by_id(db, leave_id, current_user)
    if not leave_request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Leave request not found")
    leave_update = LeaveRequestUpdate.model_construct(status="rejected", comments=comments)
    return await update_leave_request(db, leave_id, leave_update, current_user)

async def is_manager_or_hr(db: AsyncSession, user: User) -> bool:
    from sqlmodel import select
    from app.models.user import user_roles, roles
    query = select(user_roles).join(roles).where(
        user_roles.user_id == user.user_id,
        roles.role_name.in_(["Manager", "HR", "Admin", "Super_Admin"])
    )
    result = await db.execute(query)
    return result.first() is not None