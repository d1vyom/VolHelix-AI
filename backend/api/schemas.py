from pydantic import BaseModel, Field

class LogMessage(BaseModel):
    agent: str
    message: str
    level: str = Field(default="INFO")
