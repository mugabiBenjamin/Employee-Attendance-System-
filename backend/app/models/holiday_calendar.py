from sqlalchemy import Column, Integer, String, Boolean, DateTime, Date, ForeignKey, CheckConstraint, UniqueConstraint
from sqlalchemy.sql import func
from app.core.database import Base

class HolidayCalendar(Base):
    __tablename__ = "holiday_calendar"
    
    holiday_id = Column(Integer, primary_key=True)
    holiday_name = Column(String(100), nullable=False)
    holiday_date = Column(Date, nullable=False)
    is_recurring = Column(Boolean, default=False)
    applies_to_all = Column(Boolean, default=True)
    department_id = Column(Integer, ForeignKey('departments.department_id', ondelete='CASCADE'))
    year = Column(Integer, nullable=False, server_default=func.extract('year', func.current_date()))
    is_active = Column(Boolean, default=True)  # Added missing column
    deleted_at = Column(DateTime(timezone=True), nullable=True)  # Added missing column
    created_at = Column(DateTime(timezone=True), server_default=func.current_timestamp())
    updated_at = Column(DateTime(timezone=True), onupdate=func.current_timestamp())  # Also added for completeness
    
    __table_args__ = (
        CheckConstraint("year >= 2020 AND year <= 2050", name="year_valid"),
        UniqueConstraint('holiday_date', 'department_id', name='unique_holiday_date'),
    )