from pydantic import BaseModel
from typing import Optional, Literal


class UserProfile(BaseModel):
    id: str
    email: str
    line_user_id: Optional[str] = None
    is_active: bool = True
    min_confidence: str = "All"


class ConnectLineRequest(BaseModel):
    line_user_id: str


class UpdateNotificationPreferenceRequest(BaseModel):
    min_confidence: Literal["All", "High", "Medium"]
