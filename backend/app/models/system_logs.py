from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB, INET
from app.core.database import Base
from app.core.db_enums import system_action_enum

class SystemLogs(Base):
    __tablename__ = "system_logs"
    
    log_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.user_id', ondelete='SET NULL'))
    action = Column(system_action_enum, nullable=False)
    table_affected = Column(String(50))
    record_id = Column(Integer)
    old_values = Column(JSONB)
    new_values = Column(JSONB)
    ip_address = Column(INET)
    user_agent = Column(Text)
    timestamp = Column(DateTime(timezone=True), server_default=func.current_timestamp())