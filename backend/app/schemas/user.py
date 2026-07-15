from pydantic import BaseModel, Field
from typing import Optional, Literal


class UserProfile(BaseModel):
    id: str
    email: str
    line_user_id: Optional[str] = None
    is_active: bool = True
    min_confidence: str = "All"


class ConnectLineRequest(BaseModel):
    # LINE user ids are a 'U' followed by 32 hex chars. Constrained so the value
    # can't be used to smuggle arbitrary content into the push API payload.
    line_user_id: str = Field(pattern=r"^U[0-9a-f]{32}$")


class UpdateNotificationPreferenceRequest(BaseModel):
    min_confidence: Literal["All", "High", "Medium"]
