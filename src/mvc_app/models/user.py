from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    name: str = Field(min_length=2, max_length=100)


class UserRead(BaseModel):
    id: str
    email: EmailStr
    name: str

