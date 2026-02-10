"""
Journal Service
===============

Business logic for journal entries, insights, and analysis.
"""

from datetime import date, datetime, timezone
from typing import Optional
import uuid

from sqlalchemy import func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.journal import JournalEntry, JournalInsight, DailyMetric, MoodRating
from app.schemas.journal import JournalEntryCreate, JournalEntryUpdate


MOOD_ICONS = {
    MoodRating.GREAT: "😄",
    MoodRating.GOOD: "😊",
    MoodRating.CALM: "😌",
    MoodRating.STRESSED: "😟",
    MoodRating.OVERWHELMED: "😰",
}


class JournalService:
    """Service for journal operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_entry_by_id(
        self,
        entry_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Optional[JournalEntry]:
        """Get journal entry by ID ensuring it belongs to user."""
        stmt = (
            select(JournalEntry)
            .where(
                JournalEntry.entry_id == entry_id,
                JournalEntry.user_id == user_id,
            )
            .options(
                selectinload(JournalEntry.insights),
                selectinload(JournalEntry.metrics),
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_entry_by_date(
        self,
        user_id: uuid.UUID,
        entry_date: date,
    ) -> Optional[JournalEntry]:
        """Get journal entry for a specific date."""
        stmt = (
            select(JournalEntry)
            .where(
                JournalEntry.user_id == user_id,
                JournalEntry.date == entry_date,
            )
            .options(
                selectinload(JournalEntry.insights),
                selectinload(JournalEntry.metrics),
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def create_entry(
        self,
        user_id: uuid.UUID,
        entry_data: JournalEntryCreate,
    ) -> JournalEntry:
        """Create a new journal entry (text only)."""
        entry = JournalEntry(
            user_id=user_id,
            date=entry_data.date,
            entry_text=entry_data.entry_text,
            mood_rating=entry_data.mood_rating,
            is_voice_entry=False,
        )
        self.db.add(entry)
        await self.db.flush()
        
        return entry

    async def update_entry(
        self,
        entry: JournalEntry,
        entry_data: JournalEntryUpdate,
    ) -> JournalEntry:
        """Update an existing journal entry."""
        if entry_data.entry_text is not None:
            entry.entry_text = entry_data.entry_text
        if entry_data.mood_rating is not None:
            entry.mood_rating = entry_data.mood_rating
        
        await self.db.flush()
        return entry

    async def delete_entry(self, entry: JournalEntry) -> None:
        """Delete a journal entry."""
        await self.db.delete(entry)
        await self.db.flush()

    async def get_entries_paginated(
        self,
        user_id: uuid.UUID,
        page: int = 1,
        limit: int = 10,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        mood_filter: Optional[MoodRating] = None,
    ) -> dict:
        """
        Get paginated journal entries with filters.
        
        Returns entries and pagination metadata.
        """
        # Build conditions
        conditions = [JournalEntry.user_id == user_id]
        
        if from_date:
            conditions.append(JournalEntry.date >= from_date)
        if to_date:
            conditions.append(JournalEntry.date <= to_date)
        if mood_filter:
            conditions.append(JournalEntry.mood_rating == mood_filter)
        
        # Count total
        count_stmt = select(func.count()).select_from(JournalEntry).where(
            and_(*conditions)
        )
        count_result = await self.db.execute(count_stmt)
        total = count_result.scalar() or 0
        
        # Calculate pagination
        total_pages = (total + limit - 1) // limit if total > 0 else 1
        offset = (page - 1) * limit
        
        # Get entries
        entries_stmt = (
            select(JournalEntry)
            .where(and_(*conditions))
            .options(selectinload(JournalEntry.insights))
            .order_by(JournalEntry.date.desc())
            .offset(offset)
            .limit(limit)
        )
        entries_result = await self.db.execute(entries_stmt)
        entries = entries_result.scalars().all()
        
        return {
            "entries": entries,
            "pagination": {
                "current_page": page,
                "total_pages": total_pages,
                "total_entries": total,
                "per_page": limit,
                "has_next": page < total_pages,
                "has_previous": page > 1,
            },
        }

    async def get_recent_entries(
        self,
        user_id: uuid.UUID,
        limit: int = 5,
    ) -> list[JournalEntry]:
        """Get most recent journal entries."""
        stmt = (
            select(JournalEntry)
            .where(JournalEntry.user_id == user_id)
            .options(selectinload(JournalEntry.insights))
            .order_by(JournalEntry.date.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_entry_count_for_month(
        self,
        user_id: uuid.UUID,
        year: int,
        month: int,
    ) -> int:
        """Get count of journal entries for a specific month."""
        # Build date range for the month
        from calendar import monthrange
        
        first_day = date(year, month, 1)
        last_day = date(year, month, monthrange(year, month)[1])
        
        stmt = select(func.count()).select_from(JournalEntry).where(
            JournalEntry.user_id == user_id,
            JournalEntry.date >= first_day,
            JournalEntry.date <= last_day,
        )
        result = await self.db.execute(stmt)
        return result.scalar() or 0

    def get_mood_icon(self, mood: Optional[MoodRating]) -> Optional[str]:
        """Get emoji icon for mood rating."""
        if mood is None:
            return None
        return MOOD_ICONS.get(mood)

    async def add_insight(
        self,
        entry_id: uuid.UUID,
        insight_type: str,
        title: str,
        description: str,
        icon: Optional[str] = None,
        color: Optional[str] = None,
    ) -> JournalInsight:
        """Add an insight to a journal entry."""
        from app.models.journal import InsightType
        
        insight = JournalInsight(
            entry_id=entry_id,
            insight_type=InsightType(insight_type),
            title=title,
            description=description,
            icon=icon,
            color=color,
        )
        self.db.add(insight)
        await self.db.flush()
        return insight

    async def get_mood_distribution(
        self,
        user_id: uuid.UUID,
        days: int = 30,
    ) -> dict:
        """Get mood distribution for the last N days."""
        from datetime import timedelta
        
        start_date = date.today() - timedelta(days=days)
        
        stmt = (
            select(
                JournalEntry.mood_rating,
                func.count().label("count"),
            )
            .where(
                JournalEntry.user_id == user_id,
                JournalEntry.date >= start_date,
                JournalEntry.mood_rating.isnot(None),
            )
            .group_by(JournalEntry.mood_rating)
        )
        result = await self.db.execute(stmt)
        rows = result.all()
        
        distribution = {mood.value: 0 for mood in MoodRating}
        for row in rows:
            if row.mood_rating:
                distribution[row.mood_rating.value] = row.count
        
        return distribution
