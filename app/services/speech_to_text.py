"""
Speech-to-Text Service
======================

Integration with Google Cloud Speech-to-Text for voice transcription.
"""

from typing import Optional

import httpx

from app.config import settings


class SpeechToTextService:
    """
    Service for transcribing audio using Google Cloud Speech-to-Text.
    
    Supports multiple languages and audio formats.
    """
    
    # Supported languages
    SUPPORTED_LANGUAGES = {
        "en-US": "English (United States)",
        "en-GB": "English (United Kingdom)",
        "es-ES": "Spanish (Spain)",
        "hi-IN": "Hindi (India)",
        "fr-FR": "French (France)",
        "de-DE": "German (Germany)",
    }
    
    def __init__(self):
        self.credentials_path = settings.GOOGLE_APPLICATION_CREDENTIALS
        self.project_id = settings.GOOGLE_CLOUD_PROJECT
        self._client = None
    
    async def transcribe_audio(
        self,
        audio_content: bytes,
        language_code: str = "en-US",
        audio_format: str = "mp3",
    ) -> dict:
        """
        Transcribe audio content using Google Cloud Speech-to-Text.
        
        Args:
            audio_content: Binary audio content
            language_code: Language code (e.g., "en-US")
            audio_format: Audio format (mp3, wav, m4a)
            
        Returns:
            Dict with transcription, confidence, and metadata
        """
        try:
            # Import here to avoid import errors if not configured
            from google.cloud import speech_v1p1beta1 as speech
            from google.oauth2 import service_account
            
            # Initialize client
            if self.credentials_path:
                credentials = service_account.Credentials.from_service_account_file(
                    self.credentials_path
                )
                client = speech.SpeechClient(credentials=credentials)
            else:
                # Use default credentials (Application Default Credentials)
                client = speech.SpeechClient()
            
            # Map audio format to encoding
            encoding_map = {
                "mp3": speech.RecognitionConfig.AudioEncoding.MP3,
                "wav": speech.RecognitionConfig.AudioEncoding.LINEAR16,
                "m4a": speech.RecognitionConfig.AudioEncoding.MP3,  # Treat as MP3
                "ogg": speech.RecognitionConfig.AudioEncoding.OGG_OPUS,
            }
            
            encoding = encoding_map.get(
                audio_format,
                speech.RecognitionConfig.AudioEncoding.MP3,
            )
            
            # Configure recognition
            audio = speech.RecognitionAudio(content=audio_content)
            config = speech.RecognitionConfig(
                encoding=encoding,
                sample_rate_hertz=16000,  # Default sample rate
                language_code=language_code,
                enable_automatic_punctuation=True,
                use_enhanced=True,  # Better accuracy
                model="default",
            )
            
            # Perform transcription
            response = client.recognize(config=config, audio=audio)
            
            if not response.results:
                return {
                    "success": False,
                    "transcription": "",
                    "confidence": 0.0,
                    "error": "No speech detected",
                }
            
            # Combine results
            transcription = ""
            total_confidence = 0.0
            
            for result in response.results:
                alternative = result.alternatives[0]
                transcription += alternative.transcript + " "
                total_confidence += alternative.confidence
            
            avg_confidence = total_confidence / len(response.results)
            
            return {
                "success": True,
                "transcription": transcription.strip(),
                "confidence": round(avg_confidence, 2),
                "language": language_code,
                "word_count": len(transcription.split()),
            }
            
        except ImportError:
            # Google Cloud SDK not installed
            return await self._transcribe_fallback(audio_content, language_code)
        except Exception as e:
            print(f"Speech-to-Text error: {e}")
            return {
                "success": False,
                "transcription": "",
                "confidence": 0.0,
                "error": str(e),
            }
    
    async def transcribe_from_url(
        self,
        audio_url: str,
        language_code: str = "en-US",
        audio_format: str = "mp3",
    ) -> dict:
        """
        Transcribe audio from a URL.
        
        Args:
            audio_url: URL to the audio file
            language_code: Language code
            audio_format: Audio format
            
        Returns:
            Dict with transcription result
        """
        try:
            # Download audio
            async with httpx.AsyncClient() as client:
                response = await client.get(audio_url, timeout=30.0)
                response.raise_for_status()
                audio_content = response.content
            
            return await self.transcribe_audio(
                audio_content,
                language_code,
                audio_format,
            )
            
        except httpx.HTTPError as e:
            return {
                "success": False,
                "transcription": "",
                "confidence": 0.0,
                "error": f"Failed to download audio: {e}",
            }
    
    async def _transcribe_fallback(
        self,
        audio_content: bytes,
        language_code: str,
    ) -> dict:
        """
        Fallback transcription method when Google Cloud SDK is not available.
        
        In production, you might use:
        - Direct REST API call to Google Cloud
        - Alternative speech-to-text service
        - Whisper API
        """
        # For development/testing without Google Cloud
        return {
            "success": False,
            "transcription": "",
            "confidence": 0.0,
            "error": "Speech-to-Text service not configured. Install google-cloud-speech.",
        }
    
    async def transcribe_long_audio(
        self,
        audio_url: str,
        language_code: str = "en-US",
    ) -> dict:
        """
        Transcribe long audio files (>1 minute) using async recognition.
        
        Note: Requires audio file to be in Google Cloud Storage (gs:// URL).
        For Azure-hosted files, download and use regular transcription.
        """
        try:
            from google.cloud import speech_v1p1beta1 as speech
            from google.oauth2 import service_account
            
            # Initialize client
            if self.credentials_path:
                credentials = service_account.Credentials.from_service_account_file(
                    self.credentials_path
                )
                client = speech.SpeechClient(credentials=credentials)
            else:
                client = speech.SpeechClient()
            
            # For non-GCS URLs, download and use regular transcription
            if not audio_url.startswith("gs://"):
                return await self.transcribe_from_url(audio_url, language_code)
            
            audio = speech.RecognitionAudio(uri=audio_url)
            config = speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.MP3,
                sample_rate_hertz=16000,
                language_code=language_code,
                enable_automatic_punctuation=True,
            )
            
            # Start long-running operation
            operation = client.long_running_recognize(config=config, audio=audio)
            
            # Wait for completion (timeout: 5 minutes)
            response = operation.result(timeout=300)
            
            transcription = " ".join([
                result.alternatives[0].transcript
                for result in response.results
            ])
            
            return {
                "success": True,
                "transcription": transcription,
                "language": language_code,
            }
            
        except Exception as e:
            return {
                "success": False,
                "transcription": "",
                "confidence": 0.0,
                "error": str(e),
            }


# Singleton instance
_speech_service: Optional[SpeechToTextService] = None


def get_speech_service() -> SpeechToTextService:
    """Get or create speech service instance."""
    global _speech_service
    
    if _speech_service is None:
        _speech_service = SpeechToTextService()
    
    return _speech_service
