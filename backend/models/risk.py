from typing import Dict, Any, Optional
from pydantic import BaseModel, Field

class CheckResult(BaseModel):
    passed: bool
    detail: str

class RiskGateResult(BaseModel):
    approved: bool
    reason: Optional[str] = None
    checks: Dict[str, CheckResult] = Field(default_factory=dict)
    timestamp: str
