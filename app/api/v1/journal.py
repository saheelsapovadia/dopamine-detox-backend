"""
Journal API Endpoints
=====================

Handles journal entry CRUD, listing, and insights.
"""

from datetime import date
from typing import Annotated, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies import CurrentUser
from app.models.journal import MoodRating
from app.schemas.journal import (
    JournalCreateResponse,
    JournalDetailResponse,
    JournalEntryCreate,
    JournalEntryUpdate,
    JournalListResponse,
)
from app.services.cache import CacheInvalidator, CacheKeys, CacheManager
from app.services.journal_service import JournalService

router = APIRouter()


def entry_to_list_item(entry, journal_service: JournalService) -> dict:
    """Convert journal entry to list item dict."""
    # Get audio duration from metrics if available
    audio_duration = None
    waveform_data = None
    
    for metric in entry.metrics:
        if metric.metric_type.value == "voice_intensity":
            audio_duration = metric.duration_seconds
            waveform_data = metric.metric_values
            break
    
    return {
        "entry_id": str(entry.entry_id),
        "date": entry.date.isoformat(),
        "summary": entry.summary,
        "mood_rating": entry.mood_rating.value if entry.mood_rating else None,
        "mood_icon": journal_service.get_mood_icon(entry.mood_rating),
        "primary_emotion": entry.primary_emotion,
        "audio_url": entry.voice_recording_url,
        "audio_duration_seconds": audio_duration,
        "waveform_data": waveform_data,
        "insights_count": len(entry.insights),
        "created_at": entry.created_at.isoformat(),
    }


def entry_to_detail(entry, journal_service: JournalService) -> dict:
    """Convert journal entry to detailed response dict."""
    # Get audio data from metrics
    audio_duration = None
    waveform_data = None
    
    for metric in entry.metrics:
        if metric.metric_type.value == "voice_intensity":
            audio_duration = metric.duration_seconds
            waveform_data = metric.metric_values
            break
    
    # Build analysis dict
    analysis = None
    if entry.primary_emotion or entry.secondary_emotions or entry.sentiment_score:
        analysis = {
            "primary_emotion": entry.primary_emotion,
            "secondary_emotions": entry.secondary_emotions or [],
            "mood_rating": entry.mood_rating.value if entry.mood_rating else None,
            "sentiment_score": entry.sentiment_score,
            "energy_level": None,  # TODO: Add if tracked
        }
    
    # Build insights list
    insights = [
        {
            "insight_id": str(i.insight_id),
            "insight_type": i.insight_type.value,
            "title": i.title,
            "description": i.description,
            "icon": i.icon,
            "color": i.color,
        }
        for i in entry.insights
    ]
    
    return {
        "entry_id": str(entry.entry_id),
        "date": entry.date.isoformat(),
        "entry_text": entry.entry_text,
        "transcription": entry.transcription,
        "voice_recording_url": entry.voice_recording_url,
        "audio_duration_seconds": audio_duration,
        "waveform_data": waveform_data,
        "is_voice_entry": entry.is_voice_entry,
        "analysis": analysis,
        "insights": insights,
        "summary": entry.summary,
        "created_at": entry.created_at.isoformat(),
        "updated_at": entry.updated_at.isoformat(),
    }


@router.post(
    "/entry",
    response_model=JournalCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_journal_entry(
    entry_data: JournalEntryCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Create a new journal entry (text only).
    
    Voice entries will be added in Phase 12.
    """
    journal_service = JournalService(db)
    
    # Check if entry already exists for this date
    existing = await journal_service.get_entry_by_date(
        current_user.user_id,
        entry_data.date,
    )
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "JOURNAL_001",
                "message": "Entry already exists for this date",
            },
        )
    
    # Check if date is not in the future
    if entry_data.date > date.today():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "JOURNAL_002",
                "message": "Cannot create entry for future date",
            },
        )
    
    entry = await journal_service.create_entry(
        user_id=current_user.user_id,
        entry_data=entry_data,
    )
    
    # Invalidate cache
    await CacheInvalidator.on_journal_create(
        str(current_user.user_id),
        entry_data.date.isoformat(),
    )
    
    return JournalCreateResponse(
        success=True,
        data={
            "entry_id": str(entry.entry_id),
            "date": entry.date.isoformat(),
            "entry_text": entry.entry_text,
            "mood_rating": entry.mood_rating.value if entry.mood_rating else None,
            "is_voice_entry": entry.is_voice_entry,
            "created_at": entry.created_at.isoformat(),
        },
        message="Journal entry created successfully",
    )


@router.get(
    "/entries",
    response_model=JournalListResponse,
)
async def get_journal_entries(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1, le=50),
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    mood_filter: Optional[MoodRating] = None,
):
    """
    Get paginated list of journal entries.
    
    Supports filtering by date range and mood.
    """
    user_id_str = str(current_user.user_id)
    
    # Build filter key for cache
    filter_key = f"{from_date or ''}-{to_date or ''}-{mood_filter.value if mood_filter else ''}"
    cache_key = CacheKeys.journal_list(user_id_str, page, filter_key)
    
    # Try cache
    cached = await CacheManager.get(cache_key)
    if cached:
        return JournalListResponse(success=True, data=cached)
    
    journal_service = JournalService(db)
    
    result = await journal_service.get_entries_paginated(
        user_id=current_user.user_id,
        page=page,
        limit=limit,
        from_date=from_date,
        to_date=to_date,
        mood_filter=mood_filter,
    )
    
    response_data = {
        "entries": [
            entry_to_list_item(e, journal_service) for e in result["entries"]
        ],
        "pagination": result["pagination"],
    }
    
    # Cache
    await CacheManager.set(cache_key, response_data, ttl=CacheManager.TTL_MEDIUM)
    
    return JournalListResponse(success=True, data=response_data)


@router.get(
    "/entries/{entry_id}",
    response_model=JournalDetailResponse,
)
async def get_journal_entry(
    entry_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Get detailed journal entry by ID.
    """
    # Try cache
    cache_key = CacheKeys.journal_entry(str(entry_id))
    cached = await CacheManager.get(cache_key)
    if cached:
        return JournalDetailResponse(success=True, data=cached)
    
    journal_service = JournalService(db)
    
    entry = await journal_service.get_entry_by_id(entry_id, current_user.user_id)
    
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "JOURNAL_003",
                "message": "Journal entry not found",
            },
        )
    
    response_data = entry_to_detail(entry, journal_service)
    
    # Cache
    await CacheManager.set(cache_key, response_data, ttl=CacheManager.TTL_LONG)
    
    return JournalDetailResponse(success=True, data=response_data)


@router.put(
    "/entries/{entry_id}",
)
async def update_journal_entry(
    entry_id: uuid.UUID,
    entry_data: JournalEntryUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Update a journal entry.
    """
    journal_service = JournalService(db)
    
    entry = await journal_service.get_entry_by_id(entry_id, current_user.user_id)
    
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "JOURNAL_003",
                "message": "Journal entry not found",
            },
        )
    
    updated_entry = await journal_service.update_entry(entry, entry_data)
    
    # Invalidate cache
    await CacheManager.delete(CacheKeys.journal_entry(str(entry_id)))
    await CacheManager.delete(CacheKeys.journal_recent(str(current_user.user_id)))
    await CacheManager.delete_pattern(f"cache:journal:list:{current_user.user_id}:*")
    
    return {
        "success": True,
        "data": entry_to_detail(updated_entry, journal_service),
        "message": "Journal entry updated successfully",
    }


@router.delete(
    "/entries/{entry_id}",
)
async def delete_journal_entry(
    entry_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Delete a journal entry.
    """
    journal_service = JournalService(db)
    
    entry = await journal_service.get_entry_by_id(entry_id, current_user.user_id)
    
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "JOURNAL_003",
                "message": "Journal entry not found",
            },
        )
    
    await journal_service.delete_entry(entry)
    
    # Invalidate cache
    await CacheManager.delete(CacheKeys.journal_entry(str(entry_id)))
    await CacheManager.delete(CacheKeys.journal_recent(str(current_user.user_id)))
    await CacheManager.delete_pattern(f"cache:journal:list:{current_user.user_id}:*")
    
    return {
        "success": True,
        "message": "Journal entry deleted successfully",
    }


@router.get(
    "/mood-distribution",
)
async def get_mood_distribution(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    days: int = Query(default=30, ge=7, le=365),
):
    """
    Get mood distribution for the specified period.
    """
    journal_service = JournalService(db)
    distribution = await journal_service.get_mood_distribution(
        current_user.user_id,
        days,
    )
    
    return {
        "success": True,
        "data": {
            "period_days": days,
            "distribution": distribution,
        },
    }
