from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from datetime import datetime, date
from app.models.attendance import Attendance
from app.models.user import User
from app.schemas.attendance import AttendanceCreate, AttendanceUpdate, AttendanceOut
from app.core.config import settings

async def create_attendance(db: AsyncSession, attendance_create: AttendanceCreate, current_user: User) -> AttendanceOut:
    if attendance_create.user_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to clock in for another user")
    
    query = select(Attendance).where(Attendance.user_id == attendance_create.user_id, Attendance.date == attendance_create.date)
    result = await db.execute(query)
    if result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Attendance already recorded for this date")
    
    db_attendance = Attendance(**attendance_create.dict())
    db.add(db_attendance)
    await db.commit()
    await db.refresh(db_attendance)
    return AttendanceOut.from_orm(db_attendance)

async def update_attendance(db: AsyncSession, attendance_id: int, attendance_update: AttendanceUpdate, current_user: User) -> AttendanceOut:
    query = select(Attendance).where(Attendance.attendance_id == attendance_id)
    result = await db.execute(query)
    attendance = result.scalar_one_or_none()
    
    if not attendance:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attendance record not found")
    
    if attendance.user_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update this attendance")
    
    update_data = attendance_update.dict(exclude_unset=True)
    if "clock_out_time" in update_data and update_data["clock_out_time"]:
        if update_data["clock_out_time"] <= attendance.clock_in_time:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Clock out time must be after clock in time")
        total_hours = (update_data["clock_out_time"] - attendance.clock_in_time).total_seconds() / 3600
        update_data["total_hours"] = round(total_hours - (attendance.break_duration / 60), 2)
    
    for key, value in update_data.items():
        setattr(attendance, key, value)
    
    attendance.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(attendance)
    return AttendanceOut.from_orm(attendance)

async def get_attendance_by_id(db: AsyncSession, attendance_id: int, current_user: User) -> AttendanceOut:
    query = select(Attendance).where(Attendance.attendance_id == attendance_id)
    result = await db.execute(query)
    attendance = result.scalar_one_or_none()
    
    if not attendance:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attendance record not found")
    
    if attendance.user_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view this attendance")
    
    return AttendanceOut.from_orm(attendance)

async def get_user_attendance(db: AsyncSession, user_id: int, start_date: Optional[date] = None, 
                            end_date: Optional[date] = None, skip: int = 0, limit: int = settings.DEFAULT_PAGE_SIZE) -> List[AttendanceOut]:
    query = select(Attendance).where(Attendance.user_id == user_id)
    
    if start_date:
        query = query.where(Attendance.date >= start_date)
    if end_date:
        query = query.where(Attendance.date <= end_date)
    
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    attendances = result.scalars().all()
    return [AttendanceOut.from_orm(attendance) for attendance in attendances]