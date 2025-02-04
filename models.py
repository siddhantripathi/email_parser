from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class EmailResponse(BaseModel):
    reply_type: str
    proposed_time: Optional[datetime] = None
    meeting_link: Optional[str] = None
    delegate_to: Optional[str] = None
    additional_notes: Optional[str] = None 