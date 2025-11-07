from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

# Each chat message
class Message(BaseModel):
    role: str  # "user" or "assistant"
    content: str

# Incoming request from the client
class QueryRequest(BaseModel):
    query: str
    history: List[Message] = Field(default_factory=list)
    state: Optional[Dict[str, Any]] = Field(default_factory=dict)
    session_id: Optional[str] = None  # Optional field if you want multi-user sessions

# Outgoing response back to the client
class QueryResponse(BaseModel):
    response: str  # main bot reply message
    history: List[Message] = Field(default_factory=list)
    params: Optional[Dict[str, Any]] = None
    current_endpoint: Optional[str] = None
    completed_calculations: List[str] = Field(default_factory=list)
