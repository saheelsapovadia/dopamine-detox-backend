"""
Journal Schemas
===============

Pydantic schemas for journal entry endpoints.
"""

from datetime import date, datetime
from typing import Any, Optional
import uuid

from pydantic import BaseModel, Field

from app.models.journal import MoodRating


class JournalEntryCreate(BaseModel):
    """Request schema for creating a journal entry."""
    
    date: date
    entry_text: Optional[str] = None
    mood_rating: Optional[MoodRating] = None


class JournalEntryUpdate(BaseModel):
    """Request schema for updating a journal entry."""
    
    entry_text: Optional[str] = None
    mood_rating: Optional[MoodRating] = None


class JournalInsightResponse(BaseModel):
    """Response schema for journal insights."""
    
    insight_id: uuid.UUID
    insight_type: str
    title: str
    description: str
    icon: Optional[str] = None
    color: Optional[str] = None
    
    class Config:
        from_attributes = True


class JournalEntryResponse(BaseModel):
    """Response schema for a journal entry."""
    
    entry_id: uuid.UUID
    date: date
    entry_text: Optional[str] = None
    transcription: Optional[str] = None
    mood_rating: Optional[str] = None
    primary_emotion: Optional[str] = None
    summary: Optional[str] = None
    voice_recording_url: Optional[str] = None
    is_voice_entry: bool = False
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class JournalListItem(BaseModel):
    """Journal entry item for list response."""
    
    entry_id: uuid.UUID
    date: date
    summary: Optional[str] = None
    mood_rating: Optional[str] = None
    mood_icon: Optional[str] = None
    primary_emotion: Optional[str] = None
    audio_url: Optional[str] = None
    audio_duration_seconds: Optional[int] = None
    waveform_data: Optional[list[float]] = None
    insights_count: int = 0
    created_at: datetime


class JournalEntryDetail(BaseModel):
    """Detailed journal entry response."""
    
    entry_id: uuid.UUID
    date: date
    entry_text: Optional[str] = None
    transcription: Optional[str] = None
    voice_recording_url: Optional[str] = None
    audio_duration_seconds: Optional[int] = None
    waveform_data: Optional[list[float]] = None
    is_voice_entry: bool
    analysis: Optional[dict[str, Any]] = None
    insights: list[JournalInsightResponse] = []
    summary: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class PaginationInfo(BaseModel):
    """Pagination information."""
    
    current_page: int
    total_pages: int
    total_entries: int
    per_page: int
    has_next: bool
    has_previous: bool


class JournalListResponse(BaseModel):
    """Response schema for journal entries list."""
    
    success: bool = True
    data: dict[str, Any]


class JournalCreateResponse(BaseModel):
    """Response for journal creation."""
    
    success: bool = True
    data: dict[str, Any]
    message: str = "Journal entry created successfully"


class JournalDetailResponse(BaseModel):
    """Response for journal detail."""
    
    success: bool = True
    data: dict[str, Any]
