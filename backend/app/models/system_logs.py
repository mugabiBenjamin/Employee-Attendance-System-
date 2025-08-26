from sqlalchemy import CheckConstraint, Column, Integer, String, DateTime, ForeignKey, Boolean, Index
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB, INET
from app.core.database import Base, ENUM_CLASSES

class SystemLogs(Base):
    __tablename__ = "system_logs"
    
    log_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.user_id', ondelete='SET NULL'))
    action = Column(ENUM_CLASSES['system_action'], nullable=False)
    table_affected = Column(String(50))
    record_id = Column(Integer)
    old_values = Column(JSONB)
    new_values = Column(JSONB)
    ip_address = Column(INET)
    user_agent = Column(String(255))
    request_id = Column(String(36))
    timestamp = Column(DateTime(timezone=True), server_default=func.current_timestamp())
    is_active = Column(Boolean, nullable=False, default=True)
    deleted_at = Column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("deleted_at IS NULL OR is_active = FALSE", name="soft_delete_check"),
        Index('idx_system_logs_user_id', 'user_id'),
        Index('idx_system_logs_action', 'action'),
        Index('idx_system_logs_timestamp', 'timestamp'),
    )