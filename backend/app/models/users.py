from sqlalchemy import Column, Integer, String, Boolean, DateTime, Date, DECIMAL, ForeignKey, CheckConstraint
from sqlalchemy.sql import func, text
from sqlalchemy.dialects.postgresql import ENUM
from app.core.database import Base

employee_type_enum = ENUM('full_time', 'part_time', 'contract', 'intern', 'temporary', name='employee_type')

class Users(Base):
    __tablename__ = "users"
    
    user_id = Column(Integer, primary_key=True)
    employee_id = Column(String(20), unique=True, nullable=False, 
                        server_default=text("'EMP' || LPAD(nextval('employee_id_seq')::TEXT, 6, '0')"))
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    phone = Column(String(20))
    hire_date = Column(Date, nullable=False)
    employee_type = Column(employee_type_enum, nullable=False, default='full_time')
    salary = Column(DECIMAL(12, 2))
    manager_id = Column(Integer, ForeignKey('users.user_id', ondelete='SET NULL'))
    is_active = Column(Boolean, default=True)
    deleted_at = Column(DateTime(timezone=True))
    last_login = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.current_timestamp())
    updated_at = Column(DateTime(timezone=True), server_default=func.current_timestamp(), onupdate=func.current_timestamp())
    
    __table_args__ = (
        CheckConstraint("email ~ '^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$'", name="email_format"),
        CheckConstraint("phone IS NULL OR phone ~ '^[\\+]?[0-9\\s\\-\\(\\)]+$'", name="phone_format"),
        CheckConstraint("hire_date <= CURRENT_DATE", name="hire_date_valid"),
        CheckConstraint("salary IS NULL OR salary >= 0", name="salary_valid"),
        CheckConstraint("deleted_at IS NULL OR is_active = FALSE", name="soft_delete_check"),
    )