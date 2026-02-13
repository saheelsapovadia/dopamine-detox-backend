"""
Journal API Endpoints
=====================

Handles journal entry CRUD, listing, insights, and the voice-journal
flow (analyze transcript + save with audio).
"""

import logging
from datetime import date, datetime, timezone
from typing import Annotated, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies import CurrentUser
from app.models.journal import MoodRating
from app.schemas.journal import (
    AnalyzeRequest,
    AnalyzeResponse,
    JournalCreateResponse,
    JournalDetailResponse,
    JournalEntryCreate,
    JournalEntryUpdate,
    JournalListResponse,
    MoodType,
    VoiceJournalCreate,
    VoiceJournalResponse,
)
from app.services.audio_session_store import get_session, remove_session
from app.services.azure_storage import get_storage_service
from app.services.cache import CacheInvalidator, CacheKeys, CacheManager
from app.services.gemini_llm import get_gemini_service
from app.services.journal_service import JournalService

logger = logging.getLogger(__name__)

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


# =========================================================================
# Voice-Journal Flow Endpoints
# =========================================================================


@router.post(
    "/analyze",
    response_model=AnalyzeResponse,
)
async def analyze_transcript(
    body: AnalyzeRequest,
    current_user: CurrentUser,
):
    """
    Analyze a journal transcript with AI **before** saving.

    Returns insight tags, a mood label, and a mood category so the
    mobile client can display them on the review screen.  This is
    non-blocking — if it fails the user can still save without insights.
    """
    gemini = get_gemini_service()

    try:
        result = await gemini.analyze_journal_for_mobile(body.transcript)
    except Exception as e:
        logger.error("Gemini analysis failed: %s", e, exc_info=True)
        # Graceful fallback — don't block the user
        return AnalyzeResponse(
            insights=[],
            mood="Reflective moment",
            moodType=MoodType.NEUTRAL,
        )

    if result is None:
        return AnalyzeResponse(
            insights=[],
            mood="Reflective moment",
            moodType=MoodType.NEUTRAL,
        )

    return AnalyzeResponse(
        insights=result.get("insights", []),
        mood=result.get("mood", "Reflective moment"),
        moodType=MoodType(result.get("moodType", "neutral")),
    )


@router.get(
    "/",
    response_model=list[VoiceJournalResponse],
)
async def get_voice_journal_entries(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=50),
):
    """
    Get the authenticated user's journal entries in the mobile-friendly
    ``VoiceJournalResponse`` shape.

    Returns newest-first, paginated.
    """
    journal_service = JournalService(db)

    result = await journal_service.get_entries_paginated(
        user_id=current_user.user_id,
        page=page,
        limit=limit,
    )

    user_id_str = str(current_user.user_id)
    today = date.today()
    entries: list[VoiceJournalResponse] = []

    for entry in result["entries"]:
        # Friendly date label
        if entry.date == today:
            date_label = "Today"
        else:
            try:
                from datetime import timedelta
                if entry.date == today - timedelta(days=1):
                    date_label = "Yesterday"
                else:
                    date_label = entry.date.strftime("%b %d, %Y")
            except Exception:
                date_label = entry.date.strftime("%b %d, %Y")

        created = entry.created_at or datetime.now(timezone.utc)

        # Resolve audio duration from metrics
        audio_duration = None
        for metric in entry.metrics:
            if metric.metric_type.value == "voice_intensity":
                audio_duration = metric.duration_seconds
                break

        # Resolve AI insight tags
        ai_insights = [i.title for i in entry.insights] if entry.insights else []

        # Map MoodRating → MoodType (reverse of save mapping)
        mood_type_map = {
            "great": MoodType.ENERGIZED,
            "good": MoodType.HAPPY,
            "calm": MoodType.CALM,
            "stressed": MoodType.ANXIOUS,
            "overwhelmed": MoodType.TIRED,
        }
        mood_type = MoodType.NEUTRAL
        if entry.mood_rating:
            mood_type = mood_type_map.get(entry.mood_rating.value, MoodType.NEUTRAL)

        entries.append(VoiceJournalResponse(
            id=str(entry.entry_id),
            userId=user_id_str,
            dateLabel=date_label,
            time=created.strftime("%I:%M %p").lstrip("0"),
            mood=entry.primary_emotion or "Deep thoughts",
            moodType=mood_type,
            content=entry.entry_text or entry.transcription or "",
            audioUrl=entry.voice_recording_url,
            audioDurationSecs=float(audio_duration) if audio_duration else None,
            aiInsights=ai_insights,
            createdAt=created.isoformat(),
            updatedAt=(entry.updated_at or created).isoformat(),
        ))

    return entries


@router.post(
    "/",
    response_model=VoiceJournalResponse,
    status_code=status.HTTP_201_CREATED,
)
async def save_voice_journal(
    body: VoiceJournalCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Save a voice-journal entry.

    1. Looks up accumulated audio by ``sessionId`` from the WebSocket
       streaming session.
    2. Uploads the audio to Azure Blob Storage to generate a permanent
       ``audioUrl``.
    3. Persists the journal entry with transcript, mood, insights, and
       audio reference.
    4. Returns the complete ``JournalEntry`` object.
    """
    journal_service = JournalService(db)
    user_id = current_user.user_id

    # ------------------------------------------------------------------
    # 1. Resolve audio from session buffer → upload to Azure
    # ------------------------------------------------------------------
    audio_url: Optional[str] = body.audioUrl

    if body.sessionId and not audio_url:
        audio_session = get_session(body.sessionId)
        if audio_session and audio_session.total_bytes > 0:
            try:
                storage = get_storage_service()
                upload_result = await storage.upload_voice_recording(
                    user_id=str(user_id),
                    file_content=audio_session.get_audio(),
                    recording_type="journal",
                    file_format="wav",
                    reference_id=body.sessionId,
                )
                audio_url = upload_result.get("sas_url") or upload_result.get("blob_url")
                logger.info(
                    "Uploaded journal audio for session %s (%d bytes)",
                    body.sessionId,
                    audio_session.total_bytes,
                )
            except Exception as e:
                logger.error(
                    "Failed to upload audio for session %s: %s",
                    body.sessionId,
                    e,
                    exc_info=True,
                )
                # Non-fatal — save the entry without audio
            finally:
                # Free memory regardless of upload success
                remove_session(body.sessionId)

    # ------------------------------------------------------------------
    # 2. Persist the journal entry
    # ------------------------------------------------------------------
    entry = await journal_service.create_voice_entry(
        user_id=user_id,
        content=body.content,
        audio_url=audio_url,
        audio_duration_secs=body.audioDurationSecs,
        mood_label=body.mood,
        mood_type=body.moodType.value if body.moodType else None,
        ai_insights=body.aiInsights,
    )

    await db.commit()

    # ------------------------------------------------------------------
    # 3. Invalidate cache
    # ------------------------------------------------------------------
    user_id_str = str(user_id)
    await CacheInvalidator.on_journal_create(
        user_id_str,
        entry.date.isoformat(),
    )

    # ------------------------------------------------------------------
    # 4. Build response in the shape the mobile app expects
    # ------------------------------------------------------------------
    now = entry.created_at or datetime.now(timezone.utc)

    # Friendly date label
    today = date.today()
    if entry.date == today:
        date_label = "Today"
    elif entry.date == today.replace(day=today.day - 1) if today.day > 1 else today:
        date_label = "Yesterday"
    else:
        date_label = entry.date.strftime("%b %d, %Y")

    return VoiceJournalResponse(
        id=str(entry.entry_id),
        userId=user_id_str,
        dateLabel=date_label,
        time=now.strftime("%I:%M %p").lstrip("0"),
        mood=body.mood or "Deep thoughts",
        moodType=body.moodType or MoodType.DEEP,
        content=body.content,
        audioUrl=audio_url,
        audioDurationSecs=body.audioDurationSecs,
        aiInsights=body.aiInsights or [],
        createdAt=now.isoformat(),
        updatedAt=now.isoformat(),
    )


# =========================================================================
# Existing CRUD Endpoints
# =========================================================================


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
