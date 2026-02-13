"""
Journal Schemas
===============

Pydantic schemas for journal entry endpoints.
"""

from datetime import date, datetime
from enum import Enum
from typing import Any, Optional
import uuid

from pydantic import BaseModel, Field

from app.models.journal import MoodRating


# ---------------------------------------------------------------------------
# MoodType – simplified mood enum used by the mobile voice-journal flow
# ---------------------------------------------------------------------------

class MoodType(str, Enum):
    """Simplified mood categories for the voice-journal UI."""

    ENERGIZED = "energized"
    TIRED = "tired"
    DEEP = "deep"
    CALM = "calm"
    ANXIOUS = "anxious"
    HAPPY = "happy"
    NEUTRAL = "neutral"


# ---------------------------------------------------------------------------
# Text-journal schemas (existing)
# ---------------------------------------------------------------------------

class JournalEntryCreate(BaseModel):
    """Request schema for creating a text journal entry."""
    
    date: date
    entry_text: Optional[str] = None
    mood_rating: Optional[MoodRating] = None


class JournalEntryUpdate(BaseModel):
    """Request schema for updating a journal entry."""
    
    entry_text: Optional[str] = None
    mood_rating: Optional[MoodRating] = None


# ---------------------------------------------------------------------------
# Analyze endpoint schemas
# ---------------------------------------------------------------------------

class AnalyzeRequest(BaseModel):
    """Request for POST /journal/analyze – AI analysis before saving."""

    transcript: str = Field(..., min_length=1, description="Full transcribed text from the recording session.")
    sessionId: Optional[str] = Field(default=None, description="Links to the accumulated WebSocket audio session.")
    audioDurationSecs: Optional[float] = Field(default=None, ge=0, description="Total recording duration in seconds.")


class AnalyzeResponse(BaseModel):
    """Response for POST /journal/analyze."""

    insights: list[str] = Field(default_factory=list, description="AI-generated insight tags.")
    mood: str = Field(description="Human-readable mood label.")
    moodType: MoodType = Field(description="Mood category.")


# ---------------------------------------------------------------------------
# Voice-journal save schemas
# ---------------------------------------------------------------------------

class VoiceJournalCreate(BaseModel):
    """Request for POST /journal/ – save a voice journal entry."""

    content: str = Field(..., min_length=1, description="Full journal transcript text.")
    audioDurationSecs: Optional[float] = Field(default=None, ge=0, description="Total recording duration in seconds.")
    mood: Optional[str] = Field(default="Deep thoughts", description="Mood label from analysis or default.")
    moodType: Optional[MoodType] = Field(default=MoodType.DEEP, description="Mood category from analysis or default.")
    aiInsights: Optional[list[str]] = Field(default=None, description="AI insight tags returned by the analyze endpoint.")
    sessionId: Optional[str] = Field(default=None, description="References the audio session from WebSocket streaming.")
    audioUrl: Optional[str] = Field(default=None, description="Direct audio URL (unused; backend generates from sessionId).")


class VoiceJournalResponse(BaseModel):
    """Full JournalEntry object returned after saving."""

    id: str
    userId: str
    dateLabel: str
    time: str
    mood: str
    moodType: MoodType
    content: str
    audioUrl: Optional[str] = None
    audioDurationSecs: Optional[float] = None
    aiInsights: list[str] = Field(default_factory=list)
    createdAt: str
    updatedAt: str


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
