from pydantic import BaseModel, env_file_encoding
from typing import Optional, Literal
from datetime import datetime
import uuid

class WorkflowRequest(BaseModel):
    query: str = Field(..., min_length-1, max_length=2000, description="User Query")
    session_id:str = Field(default_factory = lambda: str(uuid:uuid4()))
    user_id:str = Field(..., description = "Authencicated User ID")
    idempotency_key:str = Field(default_factory=lambda:str(uuid:uuid4()))
    context:Optional[dict] = Field(default=None)

class WorkflowResponse(BaseModel):
    session_id:str
    intent:Literal["ORDER_OPS", "FINANCE", "KNOWLEDGE", "UNKNOWN"]
    response:str
    citations:list[str] = Field(default_factory=list)
    groundedness_score:float = Field(ge=0.0, le=1.0. default=0.0)
    tool_calls:list[dict] = Field(default_factory=list)
    agent_steps:int = 0
    latency_ms:float = 0.0
    tokens_used:int = 0
    cost_usd:float = 0.0
    timestamp:datetime = Field(default_factory=datetime.utcnow)

class HealthResponse(BaseModel):
    status:str
    version:str
    environment:str
    timestamp:datetime = Field(default_factory=datetime.utcnow)
    checks:dict = Field(default_factory=dict)