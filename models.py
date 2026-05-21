from pydantic import BaseModel,Field
from typing import Optional,Literal


class Task(BaseModel):
    id: int
    title: str
    description: str
    status: str
    priority: str


class TaskCreate(BaseModel):
    title: str = Field(...,min_length=1,max_length=100)
    description: Optional[str] = Field(default="",max_length=500)
    status: Optional[Literal["todo","doing","done"]] = None
    priority: Optional[Literal["low", "medium", "high"]] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(default=None,min_length=1,max_length=100)
    description: Optional[str] = Field(default=None,max_length=500)
    status: Optional[Literal["todo","doing","done"]] = None
    priority: Optional[Literal["low", "medium", "high"]] = None


class UserRegister(BaseModel):
    username: str = Field(...,min_length=3,max_length=30)
    password: str = Field(...,min_length=6,max_length=30)


class UserLogin(BaseModel):
    username: str = Field(...,min_length=3,max_length=30)
    password: str = Field(...,min_length=6,max_length=30)

class AICommandRequest(BaseModel):
    text: str = Field(...,min_length=1,max_length=500)