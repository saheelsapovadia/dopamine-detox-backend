"""
Gemini LLM Service
==================

Integration with Google Gemini via LangChain for:
- Task extraction from voice transcriptions
- Journal entry analysis and emotion detection
"""

import json
import logging
from typing import Any, Optional

from app.config import settings

logger = logging.getLogger(__name__)


class GeminiLLMService:
    """
    Service for LLM operations using Google Gemini via LangChain.
    
    Features:
    - Task extraction from natural language
    - Emotion and mood analysis
    - Insight generation
    """
    
    def __init__(self):
        self.api_key = settings.GOOGLE_GEMINI_API_KEY
        self.model_name = settings.GEMINI_MODEL
        self._llm = None
    
    @property
    def llm(self):
        """Get or create LLM instance."""
        if self._llm is None:
            if not self.api_key:
                raise ValueError(
                    "Gemini API not configured. "
                    "Set GOOGLE_GEMINI_API_KEY environment variable."
                )
            
            try:
                from langchain_google_genai import ChatGoogleGenerativeAI
                
                self._llm = ChatGoogleGenerativeAI(
                    model=self.model_name,
                    google_api_key=self.api_key,
                    temperature=0.7,
                    max_tokens=2048,
                    timeout=30,
                    max_retries=2,
                )
            except ImportError:
                raise ImportError(
                    "langchain-google-genai not installed. "
                    "Run: pip install langchain-google-genai"
                )
        
        return self._llm
    
    async def extract_tasks_from_transcription(
        self,
        transcription: str,
    ) -> list[dict]:
        """
        Extract tasks from voice transcription using Gemini.
        
        Args:
            transcription: Transcribed text from voice input
            
        Returns:
            List of extracted tasks with title, category, and confidence
        """
        prompt = f"""You are an AI assistant helping users plan their day by extracting tasks from voice transcriptions.

Transcription: {transcription}

Extract all tasks mentioned and categorize them:
- non_negotiable: Must-do tasks, high priority, deadlines, work commitments
- important: Should-do tasks, significant but flexible timing
- optional: Nice-to-do tasks, low priority, can be skipped

For each task, provide:
1. title: A clear, concise task title (max 50 characters)
2. category: One of non_negotiable, important, or optional
3. confidence: How confident you are about this extraction (0.0 to 1.0)

Respond ONLY with a valid JSON array. No additional text or explanation.

Example output:
[
  {{"title": "Complete quarterly report", "category": "non_negotiable", "confidence": 0.95}},
  {{"title": "Team sync meeting", "category": "important", "confidence": 0.88}},
  {{"title": "Reply to emails", "category": "optional", "confidence": 0.75}}
]

Extract tasks from the transcription:"""
        
        try:
            response = await self.llm.ainvoke(prompt)
            
            # Parse JSON response
            content = response.content.strip()
            
            # Handle potential markdown code blocks
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            
            tasks = json.loads(content)
            
            # Validate and clean tasks
            validated_tasks = []
            for i, task in enumerate(tasks):
                validated_tasks.append({
                    "temp_id": f"temp_{i+1}",
                    "title": task.get("title", "")[:200],
                    "category": task.get("category", "important"),
                    "confidence": float(task.get("confidence", 0.7)),
                    "order_index": i,
                })
            
            return validated_tasks
            
        except json.JSONDecodeError as e:
            print(f"JSON parsing error: {e}")
            return []
        except Exception as e:
            print(f"Task extraction error: {e}")
            return []
    
    async def analyze_journal_entry(
        self,
        transcription: str,
    ) -> Optional[dict]:
        """
        Analyze journal entry for emotions, mood, and insights.
        
        Args:
            transcription: Journal entry text
            
        Returns:
            Analysis dict with emotions, mood, insights, and summary
        """
        prompt = f"""You are an empathetic AI coach analyzing a dopamine detox journal entry.

Journal Entry: {transcription}

Analyze the entry and provide:
1. primary_emotion: The main emotion detected (e.g., overwhelmed, anxious, calm, happy, frustrated, hopeful)
2. secondary_emotions: List of up to 3 additional emotions detected
3. mood_rating: Overall mood - must be one of: great, good, calm, stressed, overwhelmed
4. sentiment_score: A score from -1.0 (very negative) to 1.0 (very positive)
5. behavioral_patterns: List of detected patterns (e.g., "trigger avoidance", "healthy coping", "progress made")
6. insights: Array of 2-3 supportive insights, each with:
   - insight_type: One of (pattern_detected, emotional_awareness, positive_behavior, energetic_morning, midday_stress, evening_calm)
   - title: Short insight title (max 30 characters)
   - description: Supportive insight description (max 100 characters)
   - icon: Icon name (growth, brain, star, shield, heart)
   - color: Color code (#34C759 for positive, #5856D6 for awareness, #FF9500 for motivation)
7. summary: A supportive 2-3 sentence summary acknowledging their experience and encouraging growth

Be supportive, non-judgmental, and focus on growth. Respond ONLY with valid JSON.

Example output:
{{
  "primary_emotion": "overwhelmed",
  "secondary_emotions": ["determined", "hopeful"],
  "mood_rating": "calm",
  "sentiment_score": 0.3,
  "behavioral_patterns": ["trigger awareness", "healthy coping"],
  "insights": [
    {{
      "insight_type": "positive_behavior",
      "title": "Positive Progress",
      "description": "You recognized your triggers and chose a healthier response",
      "icon": "growth",
      "color": "#34C759"
    }}
  ],
  "summary": "You showed remarkable self-awareness today. Recognizing your triggers is a significant step."
}}"""
        
        try:
            response = await self.llm.ainvoke(prompt)
            
            content = response.content.strip()
            
            # Handle markdown code blocks
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            
            analysis = json.loads(content)
            
            # Validate required fields
            required_fields = [
                "primary_emotion",
                "mood_rating",
                "sentiment_score",
                "insights",
                "summary",
            ]
            
            for field in required_fields:
                if field not in analysis:
                    print(f"Missing field in analysis: {field}")
                    return None
            
            return analysis
            
        except json.JSONDecodeError as e:
            print(f"JSON parsing error in journal analysis: {e}")
            return None
        except Exception as e:
            print(f"Journal analysis error: {e}")
            return None
    
    async def analyze_journal_for_mobile(
        self,
        transcript: str,
    ) -> Optional[dict]:
        """
        Lightweight journal analysis for the mobile voice-journal flow.

        Returns a simplified response suitable for the mobile UI:
        ``{"insights": [...], "mood": "...", "moodType": "..."}``

        *moodType* is one of: energized, tired, deep, calm, anxious, happy, neutral.
        """
        prompt = f"""You are an empathetic AI coach for a dopamine-detox / mindfulness app.
Analyze the following journal transcript and return a JSON object with exactly
these three fields:

1. "insights" – a JSON array of 2-4 short insight tags (strings, max 25 chars each)
   that capture the key themes, emotions, or patterns.  Examples: "Deep Reflection",
   "Evening Calm", "Digital Detox", "Growth Mindset".

2. "mood" – a short human-readable mood label (max 40 chars).
   Examples: "Feeling contemplative", "Energized and hopeful".

3. "moodType" – exactly one of: energized, tired, deep, calm, anxious, happy, neutral

Respond ONLY with a valid JSON object.  No markdown, no explanation.

Transcript:
{transcript}"""

        try:
            response = await self.llm.ainvoke(prompt)
            content = response.content.strip()

            # Strip markdown fences if present
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]

            result = json.loads(content)

            # Validate required keys
            for key in ("insights", "mood", "moodType"):
                if key not in result:
                    logger.warning("Missing key '%s' in mobile analysis", key)
                    return None

            # Clamp moodType to allowed values
            allowed = {"energized", "tired", "deep", "calm", "anxious", "happy", "neutral"}
            if result["moodType"] not in allowed:
                result["moodType"] = "neutral"

            return result

        except json.JSONDecodeError as e:
            logger.error("JSON parse error in mobile journal analysis: %s", e)
            return None
        except Exception as e:
            logger.error("Mobile journal analysis error: %s", e)
            return None


# Singleton instance
_gemini_service: Optional[GeminiLLMService] = None


def get_gemini_service() -> GeminiLLMService:
    """Get or create Gemini service instance."""
    global _gemini_service
    
    if _gemini_service is None:
        _gemini_service = GeminiLLMService()
    
    return _gemini_service
