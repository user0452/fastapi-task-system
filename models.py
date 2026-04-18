from pydantic import BaseModel
from typing import Optional


class Task(BaseModel):
    id: int
    title: str
    description: str
    status: str
    priority: str


class TaskCreate(BaseModel):
    title: str
    description: str
    status: str = "todo"
    priority: str = "medium"


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None


class UserRegister(BaseModel):
    username: str
    password: str


class UserLogin(BaseModel):
    username: str
    password: str

class AICommandRequest(BaseModel):
    text: str