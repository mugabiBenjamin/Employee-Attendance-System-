from typing import List, Optional
from pydantic import BaseModel, EmailStr, ConfigDict

class LoginCredentials(BaseModel):
    email: EmailStr
    password: str

class RefreshTokenRequest(BaseModel):
    refresh_token: str

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 1800
    
    model_config = ConfigDict(from_attributes=True)

class UserProfile(BaseModel):
    user_id: int
    email: EmailStr
    first_name: str
    last_name: str
    employee_id: Optional[str] = None
    department_id: Optional[int] = None
    is_active: bool
    roles: Optional[List[str]] = None
    permissions: Optional[List[str]] = None
    
    model_config = ConfigDict(from_attributes=True)