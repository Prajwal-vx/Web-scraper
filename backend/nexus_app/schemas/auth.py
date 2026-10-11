from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime

class UserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None

class UserCreate(UserBase):
    password: str = Field(..., min_length=6)

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserOut(UserBase):
    id: str
    is_active: bool
    is_superuser: bool
    created_at: datetime

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut

class TokenData(BaseModel):
    user_id: Optional[str] = None
    email: Optional[str] = None

class APIKeyCreate(BaseModel):
    name: str

class APIKeyOut(BaseModel):
    id: str
    name: str
    key_prefix: str
    created_at: datetime
    last_used_at: Optional[datetime] = None
    is_revoked: bool

    class Config:
        from_attributes = True

class APIKeyCreatedOut(APIKeyOut):
    api_key: str  # Only returned once upon creation
