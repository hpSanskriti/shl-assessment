"""Pydantic models for the SHL Assessment Recommender API."""
from pydantic import BaseModel, Field


class Message(BaseModel):
    role: str = Field(..., description="Either 'user' or 'assistant'")
    content: str = Field(..., description="The message content")


class ChatRequest(BaseModel):
    messages: list[Message] = Field(..., description="Full conversation history")


class Recommendation(BaseModel):
    name: str = Field(..., description="Assessment name from SHL catalog")
    url: str = Field(..., description="URL to the assessment in SHL catalog")
    test_type: str = Field(..., description="Test type code (e.g. K, P, A, B, C, E, S)")


class ChatResponse(BaseModel):
    reply: str = Field(..., description="Agent's text response")
    recommendations: list[Recommendation] = Field(
        default_factory=list,
        description="1-10 recommended assessments when agent has enough context, empty otherwise"
    )
    end_of_conversation: bool = Field(
        default=False,
        description="True only when the agent considers the task complete"
    )
