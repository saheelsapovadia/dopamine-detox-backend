"""
Deepgram Streaming Service
==========================

Real-time speech-to-text using Deepgram's v5 async WebSocket API.
Provides a configured AsyncDeepgramClient for live transcription.
"""

import logging

from deepgram import AsyncDeepgramClient

from app.config import settings

logger = logging.getLogger(__name__)


def get_deepgram_client() -> AsyncDeepgramClient:
    """
    Create a configured Deepgram async client.

    Reads the API key from settings (DEEPGRAM_API_KEY env var).
    """
    if not settings.DEEPGRAM_API_KEY:
        raise RuntimeError("DEEPGRAM_API_KEY is not configured")

    return AsyncDeepgramClient(api_key=settings.DEEPGRAM_API_KEY)
