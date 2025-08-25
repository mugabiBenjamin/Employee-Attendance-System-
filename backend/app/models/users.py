from sqlalchemy import Column, Integer, String, Boolean, DateTime, Date, DECIMAL, ForeignKey, CheckConstraint, Index, UniqueConstraint, text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base, ENUM_CLASSES
from app.core.enums import EmployeeType

class Users(Base):
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True)
    employee_id = Column(
        String(20),
        unique=True,
        nullable=False,
        server_default=text("'EMP' || LPAD(nextval('employee_id_seq')::TEXT, 6, '0')")
    )
    email = Column(String(255), nullable=False)
    password_hash = Column(String(255), nullable=False)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    phone = Column(String(20), nullable=True)
    job_title = Column(String(100), nullable=True)
    hire_date = Column(Date, nullable=False)
    employee_type = Column(ENUM_CLASSES['employee_type'], nullable=False, default=EmployeeType.FULL_TIME)
    salary = Column(DECIMAL(12, 2), nullable=True)
    supervisor_id = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    department_id = Column(Integer, ForeignKey("departments.department_id", ondelete="SET NULL"), nullable=True)
    is_active = Column(Boolean, default=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    last_login = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.current_timestamp())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp()
    )

    # Relationships
    user_roles = relationship(
        "UserRoles",
        back_populates="user",
        foreign_keys="[UserRoles.user_id]",
        lazy="selectin"
    )
    roles = relationship(
        "Roles",
        secondary="user_roles",
        primaryjoin="Users.user_id == UserRoles.user_id",
        secondaryjoin="Roles.role_id == UserRoles.role_id",
        back_populates="users",
        overlaps="user_roles",
        lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint("email ~ '^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$'", name="email_format"),
        CheckConstraint("phone IS NULL OR phone ~ '^[\\+]?[0-9\\s\\-\\(\\)]{1,20}$'", name="phone_format"),
        CheckConstraint("hire_date <= CURRENT_DATE", name="hire_date_valid"),
        CheckConstraint("salary IS NULL OR salary >= 0", name="salary_valid"),
        CheckConstraint("deleted_at IS NULL OR is_active = FALSE", name="soft_delete_check"),
        UniqueConstraint('email', name='unique_email'),
        Index('idx_users_employee_id', 'employee_id'),
        Index('idx_users_email', 'email'),
        Index('idx_users_supervisor_id', 'supervisor_id'),
        Index('idx_users_department_id', 'department_id'),
        Index('idx_users_employee_type', 'employee_type'),
    )