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
    employee_id: str | None = None
    department_id: int | None = None
    is_active: bool
    
    model_config = ConfigDict(from_attributes=True)