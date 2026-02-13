### 1. WebSocket — `ws://.../api/v1/journal/stream`

**Connection URL:**
```
ws://<host>/api/v1/journal/stream?token=<jwt>
```

On resume (after pause), append the session:
```
ws://<host>/api/v1/journal/stream?token=<jwt>&sessionId=<sessionId>
```

**Server → Client messages:**

| type | Fields | Description |
|------|--------|-------------|
| `ready` | `sessionId: string` | Backend is ready to receive audio. Client stores `sessionId` and starts streaming. |
| `transcript` | `text: string`, `is_final: boolean` | Live transcription result. `is_final=true` means this segment is complete. |
| `error` | `message: string`, `code?: string` | Server-side error during streaming. |

**Client → Server messages:**

| type | Fields | Description |
|------|--------|-------------|
| *(audio)* | `audio: string` (base64) | Raw audio chunk from `LiveAudioStream`. |
| `stop` | `type: "stop"` | Client signals end of audio stream. Backend finalises the audio session. |

**Backend responsibility:** Accumulate all audio chunks for the `sessionId`. On resume connections with the same `sessionId`, append new chunks to the existing session's audio buffer.

---

### 2. Analyze Transcript — `POST /api/v1/users/{userId}/journal/analyze`

Called when user taps "Done Recording" to get AI insights *before* saving. Non-blocking — if this fails, the user can still save without insights.

**Request:**
```json
{
  "transcript": "I've been thinking about how much time I spend on my phone...",
  "sessionId": "abc123-def456",
  "audioDurationSecs": 42
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `transcript` | `string` | Yes | The full transcribed text from the recording session. |
| `sessionId` | `string` | No | Links to the accumulated audio from the WebSocket session. |
| `audioDurationSecs` | `number` | No | Total recording duration in seconds. |

**Response:**
```json
{
  "insights": ["Deep Reflection", "Evening Calm", "Digital Detox"],
  "mood": "Feeling contemplative",
  "moodType": "deep"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `insights` | `string[]` | AI-generated insight tags (e.g. themes, emotions detected). |
| `mood` | `string` | Human-readable mood label. |
| `moodType` | `MoodType` | One of: `energized`, `tired`, `deep`, `calm`, `anxious`, `happy`, `neutral`. |

---

### 3. Create (Save) Journal Entry — `POST /api/v1/users/{userId}/journal`

Called when the user taps "Save". Persists the journal entry with transcript, AI insights, and a reference to the accumulated audio.

**Request:**
```json
{
  "content": "I've been thinking about how much time I spend on my phone...",
  "audioDurationSecs": 42,
  "mood": "Feeling contemplative",
  "moodType": "deep",
  "aiInsights": ["Deep Reflection", "Evening Calm", "Digital Detox"],
  "sessionId": "abc123-def456"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `content` | `string` | Yes | The full journal transcript text. |
| `audioDurationSecs` | `number` | No | Total recording duration in seconds. |
| `mood` | `string` | No | Mood label (from analysis or default `"Deep thoughts"`). |
| `moodType` | `MoodType` | No | Mood category (from analysis or default `"deep"`). |
| `aiInsights` | `string[]` | No | AI insight tags returned by the analyze endpoint. |
| `sessionId` | `string` | No | References the audio accumulated during WebSocket streaming. Backend uses this to locate the audio buffer, generate a permanent `audioUrl`, and link it to the entry. |
| `audioUrl` | `string` | No | Direct audio URL (unused in this flow — backend generates it from `sessionId`). |

**Response:** Full `JournalEntry` object:
```json
{
  "id": "entry_abc123",
  "userId": "user_xyz",
  "dateLabel": "Today",
  "time": "10:23 PM",
  "mood": "Feeling contemplative",
  "moodType": "deep",
  "content": "I've been thinking about how much time I spend on my phone...",
  "audioUrl": "https://storage.example.com/audio/abc123-def456.wav",
  "audioDurationSecs": 42,
  "aiInsights": ["Deep Reflection", "Evening Calm", "Digital Detox"],
  "createdAt": "2026-02-13T22:23:00.000Z",
  "updatedAt": "2026-02-13T22:23:00.000Z"
}
```

**Backend responsibility:**
1. Look up the accumulated audio buffer by `sessionId`
2. Encode/store the audio permanently (e.g. to S3/GCS) and generate `audioUrl`
3. Persist the journal entry with all fields (content, mood, insights, audioUrl)
4. Return the complete `JournalEntry`