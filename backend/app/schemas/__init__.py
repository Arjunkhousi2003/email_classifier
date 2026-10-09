import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class DevLoginRequest(BaseModel):
    email: EmailStr
    name: str | None = None


class ImapConnectRequest(BaseModel):
    host: str | None = None
    port: int = 993
    username: str
    password: str
    use_ssl: bool = True


class MailboxLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)
    host: str | None = None
    port: int = Field(default=993, ge=1, le=65535)


class FetchRequest(BaseModel):
    limit: int = Field(default=25, ge=1, le=100)


class FilterRequest(BaseModel):
    email_ids: list[uuid.UUID] | None = None


class CategoryUpdate(BaseModel):
    category: str


class ImportedMessage(BaseModel):
    sender: str = ""
    subject: str = ""
    body: str = ""
    received_at: datetime | None = None


class ImportRequest(BaseModel):
    messages: list[ImportedMessage] = Field(min_length=1, max_length=100)


class RuleCreate(BaseModel):
    category: str
    field: str = "any"
    operator: str = "contains"
    pattern: str
    priority: int = 50
