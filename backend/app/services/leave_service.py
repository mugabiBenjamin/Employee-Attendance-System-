from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from typing import List, Optional
from datetime import date
from app.models.leave import LeaveRequest, LeaveBalance
from app.models.user import User
from app.schemas.leave import LeaveRequestCreate, LeaveRequestUpdate, LeaveRequestOut, LeaveBalanceOut
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)  

async def create_leave_request(db: AsyncSession, leave_request: LeaveRequestCreate, current_user: User) -> LeaveRequestOut:
    try:
        db_leave = LeaveRequest(
            user_id=leave_request.user_id,
            leave_type=leave_request.leave_type,
            start_date=leave_request.start_date,
            end_date=leave_request.end_date,
            days_requested=leave_request.days_requested,
            reason=leave_request.reason,
            status=leave_request.status,
            attachment_url=leave_request.attachment_url,
            created_at=leave_request.created_at or datetime.utcnow(),
            updated_at=leave_request.updated_at or datetime.utcnow(),
        )
        db.add(db_leave)
        await db.commit()
        await db.refresh(db_leave)
        logger.info(f"Leave request created for user_id {leave_request.user_id}, leave_id {db_leave.leave_id}")
        return LeaveRequestOut.from_orm(db_leave)
    except Exception as e:
        logger.error(f"ソー "Error creating leave request: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error creating leave request")

async def update_leave_request(db: AsyncSession, leave_id: int, leave_update: LeaveRequestUpdate, current_user: User) -> LeaveRequestOut:
    try:
        db_leave = await get_leave_request_by_id(db, leave_id, current_user)
        if not db_leave:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Leave request not found")
        
        for attr, value in leave_update.dict(exclude_unset=True).items():
            if attr == "status" and value in ["approved", "rejected"]:
                setattr(db_leave, attr, value)
                setattr(db_leave, "approved_by", current_user.user_id)
                setattr(db_leave, "approved_at", datetime.utcnow())
            else:
                setattr(db_leave, attr, value)
        
        db_leave.updated_at = datetime.utcnow()
        db.add(db_leave)
        await db.commit()
        await db.refresh(db_leave)
        logger.info(f"Leave request updated, leave_id {leave_id}")
        return LeaveRequestOut.from_orm(db_leave)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating leave request: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error updating leave request")

async def get_leave_request_by_id(db: AsyncSession, leave_id: int, current_user: User) -> Optional[LeaveRequestOut]:
    try:
        query = select(LeaveRequest).where(LeaveRequest.leave_id == leave_id)
        result = await db.execute(query)
        db_leave = result.scalar_one_or_none()
        if db_leave:
            return LeaveRequestOut.from_orm(db_leave)
        return None
    except Exception as e:
        logger.error(f"Error retrieving leave request: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving leave request")

async def get_user_leave_requests(db: AsyncSession, user_id: int, start_date: Optional[date], end_date: Optional[date], skip: int, limit: int) -> List[LeaveRequestOut]:
    try:
        query = select(LeaveRequest).where(LeaveRequest.user_id == user_id)
        if start_date:
            query = query.where(LeaveRequest.start_date >= start_date)
        if end_date:
            query = query.where(LeaveRequest.end_date <= end_date)
        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        leave_requests = result.scalars().all()
        logger.info(f"Retrieved {len(leave_requests)} leave requests for user_id {user_id}")
        return [LeaveRequestOut.from_orm(lr) for lr in leave_requests]
    except Exception as e:
        logger.error(f"Error retrieving leave requests: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving leave requests")

async def get_leave_balance(db: AsyncSession, user_id: int, year: Optional[int]) -> List[LeaveBalanceOut]:
    try:
        query = select(LeaveBalance).where(LeaveBalance.user_id == user_id)
        if year:
            query = query.where(LeaveBalance.year == year)
        result = await db.execute(query)
        balances = result.scalars().all()
        logger.info(f"Retrieved {len(balances)} leave balances for user_id {user_id}")
        return [LeaveBalanceOut.from_orm(b) for b in balances]
    except Exception as e:
        logger.error(f"Error retrieving leave balances: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving leave balances")