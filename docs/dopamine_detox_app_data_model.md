# Dopamine Detox App - Data Model

## Overview
This document defines the complete data model for a dopamine detox and mindfulness application with journaling, habit tracking, progress monitoring, and voice-enabled daily planning features.

---

## Core Entities

### 1. User
Stores user account and profile information.

**Fields:**
- `user_id` (UUID, Primary Key)
- `email` (String, Unique, Required)
- `password_hash` (String, Required)
- `full_name` (String)
- `created_at` (Timestamp)
- `updated_at` (Timestamp)
- `last_login` (Timestamp)
- `onboarding_completed` (Boolean, Default: false)
- `timezone` (String)
- `notification_preferences` (JSON)

**Relationships:**
- One-to-Many with JournalEntry
- One-to-Many with DailyPlan
- One-to-Many with Task
- One-to-Many with TriggerActivity
- One-to-One with UserProgress
- One-to-One with Subscription (Default: free tier)
- One-to-Many with Affirmation

---

### 2. JournalEntry
Stores daily journal entries with voice transcriptions and mood tracking.

**Fields:**
- `entry_id` (UUID, Primary Key)
- `user_id` (UUID, Foreign Key → User)
- `date` (Date, Required)
- `entry_text` (Text)
- `voice_recording_url` (String) - URL to audio file storage
- `transcription` (Text) - Voice-to-text transcription
- `mood_rating` (Integer, 1-5 or enum)
- `created_at` (Timestamp)
- `updated_at` (Timestamp)
- `is_voice_entry` (Boolean, Default: false)

**Relationships:**
- Many-to-One with User
- One-to-Many with JournalInsight
- One-to-Many with DailyMetric

**Indexes:**
- `user_id, date` (Composite, Unique)
- `user_id, created_at`

---

### 3. JournalInsight
Stores AI-generated insights from journal entries (shown in Daily Summary).

**Fields:**
- `insight_id` (UUID, Primary Key)
- `entry_id` (UUID, Foreign Key → JournalEntry)
- `insight_type` (Enum: 'energetic_morning', 'midday_stress', 'evening_calm', 'pattern_detected')
- `title` (String) - e.g., "Energetic Morning"
- `description` (String) - e.g., "High focus & motivation detected"
- `icon` (String) - Icon identifier
- `color` (String) - Color code for UI
- `created_at` (Timestamp)

**Relationships:**
- Many-to-One with JournalEntry

---

### 4. DailyMetric
Tracks quantitative daily metrics shown in journal history (audio waveform visualization).

**Fields:**
- `metric_id` (UUID, Primary Key)
- `entry_id` (UUID, Foreign Key → JournalEntry)
- `metric_type` (Enum: 'voice_intensity', 'energy_level', 'stress_level')
- `metric_values` (JSON Array) - For waveform data points
- `duration_seconds` (Integer) - For voice recordings
- `created_at` (Timestamp)

**Relationships:**
- Many-to-One with JournalEntry

---

### 5. DailyPlan
Stores daily plans created through voice input.

**Fields:**
- `plan_id` (UUID, Primary Key)
- `user_id` (UUID, Foreign Key → User)
- `date` (Date, Required)
- `voice_input_url` (String) - Original voice recording
- `transcription` (Text) - "I want to focus on deep work this morning..."
- `parsed_goal` (Text) - Extracted main goal
- `created_at` (Timestamp)
- `updated_at` (Timestamp)
- `completed` (Boolean, Default: false)

**Relationships:**
- Many-to-One with User
- One-to-Many with Task

**Indexes:**
- `user_id, date` (Composite, Unique)

---

### 6. Task
Individual tasks extracted from daily plans or manually created.

**Fields:**
- `task_id` (UUID, Primary Key)
- `plan_id` (UUID, Foreign Key → DailyPlan, Nullable)
- `user_id` (UUID, Foreign Key → User)
- `title` (String, Required) - e.g., "Deep work: Project Alpha strategy"
- `description` (Text)
- `category` (Enum: 'non_negotiable', 'important', 'optional')
- `order_index` (Integer) - For sorting
- `completed` (Boolean, Default: false)
- `completed_at` (Timestamp)
- `due_date` (Date)
- `created_at` (Timestamp)
- `updated_at` (Timestamp)

**Relationships:**
- Many-to-One with DailyPlan
- Many-to-One with User

**Indexes:**
- `user_id, due_date`
- `plan_id, order_index`

---

### 7. TriggerActivity
Activities users identify as addictive triggers (from onboarding).

**Fields:**
- `trigger_id` (UUID, Primary Key)
- `user_id` (UUID, Foreign Key → User)
- `activity_name` (String) - e.g., "Social media, snacks & doomscrolling"
- `category` (Enum: 'social_media', 'food', 'gaming', 'shopping', 'video', 'other')
- `identified_at` (Timestamp)
- `is_active` (Boolean, Default: true) - User can deactivate triggers

**Relationships:**
- Many-to-One with User

---

### 8. UserProgress
Aggregated progress metrics shown in "Look How Far You've Come" screen.

**Fields:**
- `progress_id` (UUID, Primary Key)
- `user_id` (UUID, Foreign Key → User, Unique)
- `total_tasks_completed` (Integer, Default: 0)
- `total_days_active` (Integer, Default: 0)
- `current_focus_streak` (Integer, Default: 0)
- `longest_focus_streak` (Integer, Default: 0)
- `last_active_date` (Date)
- `updated_at` (Timestamp)

**Relationships:**
- One-to-One with User

---

### 9. Affirmation
Daily affirmations and motivational messages.

**Fields:**
- `affirmation_id` (UUID, Primary Key)
- `user_id` (UUID, Foreign Key → User, Nullable) - Null for system affirmations
- `text` (Text, Required) - e.g., "Every small action I take moves me forward."
- `category` (Enum: 'encouragement', 'progress', 'mindfulness', 'focus')
- `is_system_affirmation` (Boolean, Default: true)
- `created_at` (Timestamp)

**Relationships:**
- Many-to-One with User (for custom affirmations)

---

### 10. OnboardingStep
Tracks user progress through onboarding flow.

**Fields:**
- `step_id` (UUID, Primary Key)
- `user_id` (UUID, Foreign Key → User)
- `step_name` (Enum: 'breathing_exercise', 'consistency_message', 'progress_tracking', 'momentum_building', 'trigger_identification')
- `completed` (Boolean, Default: false)
- `completed_at` (Timestamp)
- `step_data` (JSON) - Additional data captured during step

**Relationships:**
- Many-to-One with User

**Indexes:**
- `user_id, step_name` (Composite, Unique)

---

### 11. DailyCheckIn
Tracks daily check-ins from the home screen.

**Fields:**
- `checkin_id` (UUID, Primary Key)
- `user_id` (UUID, Foreign Key → User)
- `date` (Date, Required)
- `status` (Enum: 'completed', 'planned', 'skipped')
- `completion_icon` (String) - Sun, star, cloud icons
- `created_at` (Timestamp)

**Relationships:**
- Many-to-One with User

**Indexes:**
- `user_id, date` (Composite, Unique)

---

## Supporting Entities

### 12. VoiceRecording
Metadata for voice recordings (separate from journal/plan tables for flexibility).

**Fields:**
- `recording_id` (UUID, Primary Key)
- `user_id` (UUID, Foreign Key → User)
- `file_url` (String, Required) - Cloud storage URL
- `file_size_bytes` (BigInteger)
- `duration_seconds` (Integer)
- `format` (String) - e.g., "mp3", "wav"
- `transcription_status` (Enum: 'pending', 'processing', 'completed', 'failed')
- `created_at` (Timestamp)

**Relationships:**
- Many-to-One with User

---

### 13. Subscription
Stores user subscription information with RevenueCat integration.

**Fields:**
- `subscription_id` (UUID, Primary Key)
- `user_id` (UUID, Foreign Key → User, Unique)
- `tier` (Enum: 'free', 'monthly', 'annual', Default: 'free')
- `status` (Enum: 'active', 'expired', 'cancelled', 'trial', Default: 'active')
- `started_at` (Timestamp)
- `expires_at` (Timestamp, Nullable) - Null for free tier
- `auto_renew` (Boolean, Default: false)
- `trial_end_date` (Timestamp, Nullable)
- `cancelled_at` (Timestamp, Nullable)
- `created_at` (Timestamp)
- `updated_at` (Timestamp)

**RevenueCat Integration Fields:**
- `revenuecat_subscriber_id` (String, Unique, Nullable) - RC Customer ID
- `revenuecat_original_app_user_id` (String, Nullable)
- `revenuecat_entitlements` (JSON Array) - Active entitlements from RC
- `last_revenuecat_sync` (Timestamp) - Last webhook sync time

**Payment/Order Fields:**
- `original_purchase_date` (Timestamp, Nullable)
- `latest_purchase_date` (Timestamp, Nullable)
- `platform` (Enum: 'ios', 'android', 'web', Nullable)
- `product_identifier` (String) - e.g., "monthly_premium_799"
- `price_paid` (Decimal, Nullable) - Actual amount paid
- `currency` (String, Nullable) - e.g., "USD"
- `store_transaction_id` (String, Nullable) - App Store/Play Store transaction ID
- `store_original_transaction_id` (String, Nullable)

**Relationships:**
- One-to-One with User
- One-to-Many with SubscriptionHistory

**Indexes:**
- `user_id` (Unique)
- `revenuecat_subscriber_id` (Unique, Nullable)
- `status, expires_at`
- `tier, status`

---

### 14. SubscriptionHistory
Tracks all subscription events and changes for audit trail.

**Fields:**
- `history_id` (UUID, Primary Key)
- `subscription_id` (UUID, Foreign Key → Subscription)
- `user_id` (UUID, Foreign Key → User)
- `event_type` (Enum: 'purchase', 'renewal', 'cancellation', 'expiration', 'reactivation', 'upgrade', 'downgrade', 'refund', 'billing_issue')
- `previous_tier` (Enum: 'free', 'monthly', 'annual', Nullable)
- `new_tier` (Enum: 'free', 'monthly', 'annual')
- `previous_status` (String, Nullable)
- `new_status` (String)
- `price_paid` (Decimal, Nullable)
- `currency` (String, Nullable)
- `revenuecat_event_data` (JSON) - Raw webhook payload from RevenueCat
- `store_transaction_id` (String, Nullable)
- `created_at` (Timestamp)

**Relationships:**
- Many-to-One with Subscription
- Many-to-One with User

**Indexes:**
- `subscription_id, created_at DESC`
- `user_id, event_type`
- `event_type, created_at`

---

### 15. SystemMessage
Pre-defined system messages and coaching prompts.

**Fields:**
- `message_id` (UUID, Primary Key)
- `context` (Enum: 'welcome', 'plan_start', 'completion', 'encouragement')
- `message_text` (Text) - e.g., "You're in control today."
- `icon` (String)
- `created_at` (Timestamp)

---

## Enumerations

### SubscriptionTier
- `free` - Basic features with limitations
- `monthly` - Monthly premium subscription ($8/month)
- `annual` - Annual premium subscription ($70/year, 25% discount)

### SubscriptionStatus
- `active` - Subscription is active and valid
- `trial` - In trial period
- `expired` - Subscription has expired
- `cancelled` - Cancelled but still active until expiry
- `billing_issue` - Payment failed, grace period

### SubscriptionFeatureLimits

**Free Tier:**
```json
{
  "journals_per_month": 1,
  "ai_insights": false,
  "ai_analysis": false,
  "progress_reports": false,
  "unlimited_tasks": true,
  "voice_transcription": false,
  "ads_enabled": true,
  "advanced_analytics": false,
  "priority_support": false
}
```

**Monthly Tier ($8/month):**
```json
{
  "journals_per_month": -1,  // Unlimited
  "ai_insights": true,
  "ai_analysis": true,
  "progress_reports": true,
  "unlimited_tasks": true,
  "voice_transcription": true,
  "ads_enabled": false,
  "advanced_analytics": true,
  "priority_support": false
}
```

**Annual Tier ($70/year - 25% savings):**
```json
{
  "journals_per_month": -1,  // Unlimited
  "ai_insights": true,
  "ai_analysis": true,
  "progress_reports": true,
  "unlimited_tasks": true,
  "voice_transcription": true,
  "ads_enabled": false,
  "advanced_analytics": true,
  "priority_support": true
}
```

### MoodRating
- `great` (5)
- `good` (4)
- `calm` (3)
- `stressed` (2)
- `overwhelmed` (1)

### InsightType
- `energetic_morning` - High focus & motivation detected
- `midday_stress` - Spike in typing speed & errors
- `evening_calm` - Lower voice pitch recorded
- `pattern_detected` - Custom patterns

### TaskCategory
- `non_negotiable` - Must-do tasks
- `important` - Should-do tasks
- `optional` - Nice-to-do tasks

### TriggerCategory
- `social_media`
- `food` (snacks, comfort eating)
- `gaming`
- `shopping`
- `video` (streaming, doomscrolling)
- `other`

### OnboardingStepName
- `breathing_exercise` - Mindful breathing intro
- `consistency_message` - "You're Showing Up"
- `progress_tracking` - "Look How Far You've Come"
- `momentum_building` - "You're Building Momentum"
- `trigger_identification` - Identifying addictive triggers
- `intentional_planning` - "Plan your day intentionally"

---

## Relationships Summary

```
User (1) ────── (Many) JournalEntry
User (1) ────── (Many) DailyPlan
User (1) ────── (Many) Task
User (1) ────── (Many) TriggerActivity
User (1) ────── (1) UserProgress
User (1) ────── (1) Subscription
User (1) ────── (Many) SubscriptionHistory
User (1) ────── (Many) Affirmation
User (1) ────── (Many) OnboardingStep
User (1) ────── (Many) DailyCheckIn
User (1) ────── (Many) VoiceRecording

JournalEntry (1) ────── (Many) JournalInsight
JournalEntry (1) ────── (Many) DailyMetric

DailyPlan (1) ────── (Many) Task

Subscription (1) ────── (Many) SubscriptionHistory
```

---

## Indexes for Performance

### Critical Indexes
1. `users.email` - Login queries
2. `journal_entries(user_id, date)` - Daily journal retrieval
3. `journal_entries(user_id, created_at DESC)` - Past journals list
4. `daily_plans(user_id, date)` - Today's plan
5. `tasks(user_id, due_date)` - Task lists
6. `tasks(plan_id, order_index)` - Ordered task retrieval
7. `daily_checkins(user_id, date)` - Check-in status

---

## Data Storage Considerations

### Cloud Storage (AWS S3, Google Cloud Storage, etc.)
- Voice recordings (audio files)
- Profile pictures (if added)
- File structure: `{user_id}/recordings/{recording_id}.{format}`

### Database (PostgreSQL recommended)
- All structured data
- JSON fields for flexible data (insights, metrics, notification preferences)

### Caching Layer (Redis)
- User sessions
- Today's plan (frequently accessed)
- Recent journal entries
- User progress stats

---

## Privacy & Security

### Data Retention
- Journal entries: Indefinite (user-controlled deletion)
- Voice recordings: 30 days auto-delete after transcription (configurable)
- Deleted accounts: 30-day soft delete, then permanent deletion

### Encryption
- Passwords: bcrypt/Argon2 hashing
- Voice recordings: Encrypted at rest
- Journal entries: Consider end-to-end encryption for sensitive content
- API communications: TLS 1.3

### GDPR Compliance
- User data export capability
- Right to deletion (cascade delete on user)
- Consent tracking for voice recordings

---

## API Endpoints Specification

### Authentication

**Note**: On user registration, automatically create a free tier subscription record.

#### Register User
**Endpoint**: `POST /api/v1/auth/register`

**Request**:
```http
POST /api/v1/auth/register
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "SecurePass123!",
  "full_name": "John Doe",
  "timezone": "Asia/Kolkata"
}
```

**Response** (201 Created):
```json
{
  "success": true,
  "data": {
    "user": {
      "user_id": "uuid",
      "email": "user@example.com",
      "full_name": "John Doe",
      "created_at": "2025-01-29T10:00:00Z"
    },
    "subscription": {
      "tier": "free",
      "status": "active",
      "feature_limits": {
        "journals_per_month": 1,
        "ai_insights": false,
        "unlimited_tasks": true,
        "ads_enabled": true
      }
    },
    "tokens": {
      "access_token": "jwt_token_here",
      "refresh_token": "refresh_token_here",
      "expires_in": 86400
    }
  },
  "message": "Account created successfully"
}
```

**Processing Flow**:
1. Validate email format and uniqueness
2. Hash password (bcrypt/Argon2)
3. Create user record
4. **Automatically create free tier subscription**:
   ```sql
   INSERT INTO subscriptions (
     subscription_id, user_id, tier, status, started_at
   ) VALUES (
     UUID(), user_id, 'free', 'active', NOW()
   )
   ```
5. Create UserProgress record
6. Generate JWT tokens
7. Return response

---

#### Login
**Endpoint**: `POST /api/v1/auth/login`

**Request**:
```http
POST /api/v1/auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "SecurePass123!"
}
```

**Response** (200 OK):
```json
{
  "success": true,
  "data": {
    "user": {
      "user_id": "uuid",
      "email": "user@example.com",
      "full_name": "John Doe"
    },
    "subscription": {
      "tier": "annual",
      "status": "active",
      "expires_at": "2026-01-29T23:59:59Z"
    },
    "tokens": {
      "access_token": "jwt_token_here",
      "refresh_token": "refresh_token_here",
      "expires_in": 86400
    }
  }
}
```

---

#### Logout
**Endpoint**: `POST /api/v1/auth/logout`

---

#### Refresh Token
**Endpoint**: `POST /api/v1/auth/refresh-token`

---

## MODULE 1: ONBOARDING

### 1.1 Record, Transcribe & Save Onboarding Step Response

**Endpoint**: `POST /api/v1/onboarding/record-step`

**Description**: Records user's voice response to onboarding questions/steps, transcribes it using speech-to-text, and saves the response.

**Request**:
```http
POST /api/v1/onboarding/record-step
Content-Type: multipart/form-data
Authorization: Bearer {jwt_token}

{
  "step_name": "trigger_identification", // Enum: breathing_exercise, consistency_message, etc.
  "audio_file": <binary_audio_file>, // Format: mp3, wav, m4a
  "audio_duration_seconds": 45
}
```

**Response** (200 OK):
```json
{
  "success": true,
  "data": {
    "step_id": "uuid",
    "step_name": "trigger_identification",
    "transcription": "Social media, snacks, and doomscrolling are my biggest triggers...",
    "audio_url": "https://storage.example.com/recordings/user_id/step_xyz.mp3",
    "completed_at": "2025-01-29T10:30:00Z",
    "next_step": "intentional_planning" // Null if last step
  },
  "message": "Onboarding step recorded successfully"
}
```

**Caching Strategy**:
- Cache user's onboarding progress: `cache:onboarding:{user_id}` (TTL: 1 hour)

**Error Responses**:
- 400: Invalid audio format or step_name
- 413: Audio file too large (max 10MB)
- 503: Transcription service unavailable

---

## MODULE 2: HOME (STORIES & TASKS)

### 2.1 Get Daily Stories/Insights

**Endpoint**: `GET /api/v1/home/stories`

**Description**: Returns 4 story cards with summarized insights about tasks completed, significant events, motivational messages, and problems overcome.

**Request**:
```http
GET /api/v1/home/stories
Authorization: Bearer {jwt_token}
Query Parameters:
  - date (optional): YYYY-MM-DD (default: today)
```

**Response** (200 OK):
```json
{
  "success": true,
  "data": {
    "stories": [
      {
        "story_id": "uuid",
        "type": "task_completion",
        "title": "Productive Morning Sprint",
        "summary": "You completed 5 out of 6 non-negotiable tasks before noon. Your focus was exceptional!",
        "icon": "star",
        "color": "#FF9500",
        "metric": {
          "label": "Tasks Completed",
          "value": 5,
          "total": 6
        },
        "created_at": "2025-01-29T12:00:00Z"
      },
      {
        "story_id": "uuid",
        "type": "milestone",
        "title": "7-Day Streak Unlocked!",
        "summary": "You've maintained consistency for a full week. Your commitment is building real momentum.",
        "icon": "trophy",
        "color": "#34C759",
        "metric": {
          "label": "Current Streak",
          "value": 7,
          "unit": "days"
        },
        "created_at": "2025-01-29T08:00:00Z"
      },
      {
        "story_id": "uuid",
        "type": "challenge_overcome",
        "title": "Resisted Social Media",
        "summary": "You identified the urge to scroll and chose reading instead. That's 45 minutes reclaimed!",
        "icon": "shield",
        "color": "#5856D6",
        "metric": {
          "label": "Time Saved",
          "value": 45,
          "unit": "minutes"
        },
        "created_at": "2025-01-28T16:30:00Z"
      },
      {
        "story_id": "uuid",
        "type": "motivation",
        "title": "You're Building Momentum",
        "summary": "Small consistent actions compound. Every day you return, your mind learns to trust you more.",
        "icon": "growth",
        "color": "#FF9500",
        "affirmation": "I choose progress over pressure.",
        "created_at": "2025-01-29T07:00:00Z"
      }
    ],
    "page": 1,
    "total_pages": 4,
    "has_more": true
  }
}
```

**Caching Strategy**:
- Cache today's stories: `cache:stories:{user_id}:{date}` (TTL: 15 minutes)
- Invalidate on: new task completion, journal entry, or milestone achievement

**Error Responses**:
- 404: No stories found for the specified date

---

### 2.2 Get Today's Tasks

**Endpoint**: `GET /api/v1/home/tasks/today`

**Description**: Returns all tasks for today, grouped by category and sorted by order.

**Request**:
```http
GET /api/v1/home/tasks/today
Authorization: Bearer {jwt_token}
Query Parameters:
  - include_completed (optional): boolean (default: true)
```

**Response** (200 OK):
```json
{
  "success": true,
  "data": {
    "date": "2025-01-29",
    "plan_exists": true,
    "plan_id": "uuid",
    "tasks_by_category": {
      "non_negotiable": [
        {
          "task_id": "uuid",
          "title": "Deep work: Project Alpha strategy",
          "description": null,
          "completed": false,
          "order_index": 0,
          "created_at": "2025-01-29T06:00:00Z"
        },
        {
          "task_id": "uuid",
          "title": "Review Q1 Marketing deck",
          "completed": true,
          "completed_at": "2025-01-29T10:30:00Z",
          "order_index": 1
        }
      ],
      "important": [
        {
          "task_id": "uuid",
          "title": "Quick sync with design team",
          "completed": false,
          "order_index": 0
        }
      ],
      "optional": [
        {
          "task_id": "uuid",
          "title": "Reply to pending emails",
          "completed": false,
          "order_index": 0
        }
      ]
    },
    "summary": {
      "total_tasks": 6,
      "completed_tasks": 2,
      "completion_percentage": 33
    }
  }
}
```

**Caching Strategy**:
- Cache today's tasks: `cache:tasks:today:{user_id}` (TTL: 5 minutes)
- Invalidate on: task creation, update, deletion, or completion

**Error Responses**:
- 404: No tasks found for today

---

## MODULE 3: TASK PLANNING

### 3.1 Plan the Day with Voice

**Endpoint**: `POST /api/v1/tasks/plan-day`

**Description**: User records their daily plan via voice. The API transcribes the audio, extracts tasks using LLM (Gemini), and returns structured tasks for user review/editing before saving.

**Request**:
```http
POST /api/v1/tasks/plan-day
Content-Type: multipart/form-data
Authorization: Bearer {jwt_token}

{
  "date": "2025-01-29", // YYYY-MM-DD
  "audio_file": <binary_audio_file>,
  "audio_duration_seconds": 68
}
```

**Response** (200 OK):
```json
{
  "success": true,
  "data": {
    "plan_id": "uuid",
    "date": "2025-01-29",
    "transcription": "I want to focus on deep work this morning and finally finish the quarterly report. I also need to review the Q1 marketing deck, have a quick sync with the design team, reply to pending emails, and prepare a healthy lunch.",
    "audio_url": "https://storage.example.com/recordings/user_id/plan_abc.mp3",
    "extracted_tasks": [
      {
        "temp_id": "temp_1", // Temporary ID for frontend reference
        "title": "Deep work: Project Alpha strategy",
        "category": "non_negotiable",
        "order_index": 0,
        "confidence": 0.95 // LLM confidence score
      },
      {
        "temp_id": "temp_2",
        "title": "Finish quarterly report",
        "category": "non_negotiable",
        "order_index": 1,
        "confidence": 0.92
      },
      {
        "temp_id": "temp_3",
        "title": "Review Q1 Marketing deck",
        "category": "important",
        "order_index": 0,
        "confidence": 0.88
      },
      {
        "temp_id": "temp_4",
        "title": "Quick sync with design team",
        "category": "important",
        "order_index": 1,
        "confidence": 0.85
      },
      {
        "temp_id": "temp_5",
        "title": "Reply to pending emails",
        "category": "optional",
        "order_index": 0,
        "confidence": 0.80
      },
      {
        "temp_id": "temp_6",
        "title": "Prepare healthy lunch",
        "category": "optional",
        "order_index": 1,
        "confidence": 0.78
      }
    ],
    "requires_confirmation": true, // User must review and save
    "created_at": "2025-01-29T06:00:00Z"
  },
  "message": "Tasks extracted successfully. Please review and confirm."
}
```

**Processing Flow**:
1. Upload audio to cloud storage
2. Transcribe audio using Google Speech-to-Text / AWS Transcribe
3. Send transcription to Gemini API for task extraction
4. Parse LLM response into structured tasks
5. Return for user review (not saved yet)

**Note**: Tasks are NOT saved to database yet. User must call the confirmation endpoint after editing.

---

### 3.2 Confirm & Save Daily Plan

**Endpoint**: `POST /api/v1/tasks/plan-day/confirm`

**Description**: After user reviews and edits extracted tasks, this endpoint saves the final plan and tasks to the database.

**Request**:
```http
POST /api/v1/tasks/plan-day/confirm
Content-Type: application/json
Authorization: Bearer {jwt_token}

{
  "plan_id": "uuid", // From previous response
  "tasks": [
    {
      "temp_id": "temp_1", // Match with extracted task
      "title": "Deep work: Project Alpha strategy", // User can edit
      "category": "non_negotiable",
      "order_index": 0
    },
    {
      "temp_id": "temp_2",
      "title": "Complete quarterly report", // Edited by user
      "category": "non_negotiable",
      "order_index": 1
    },
    // ... user can add/remove/edit tasks
  ]
}
```

**Response** (200 OK):
```json
{
  "success": true,
  "data": {
    "plan_id": "uuid",
    "date": "2025-01-29",
    "tasks_saved": 5,
    "tasks": [
      {
        "task_id": "uuid",
        "title": "Deep work: Project Alpha strategy",
        "category": "non_negotiable",
        "completed": false,
        "order_index": 0
      },
      // ... all saved tasks
    ]
  },
  "message": "Daily plan saved successfully"
}
```

**Caching Strategy**:
- Invalidate: `cache:tasks:today:{user_id}`
- Invalidate: `cache:stories:{user_id}:{date}`

---

### 3.3 Complete a Task

**Endpoint**: `POST /api/v1/tasks/{task_id}/complete`

**Description**: Mark a task as completed and update user progress.

**Request**:
```http
POST /api/v1/tasks/{task_id}/complete
Authorization: Bearer {jwt_token}
```

**Response** (200 OK):
```json
{
  "success": true,
  "data": {
    "task_id": "uuid",
    "title": "Deep work: Project Alpha strategy",
    "completed": true,
    "completed_at": "2025-01-29T14:30:00Z",
    "celebration": {
      "message": "Beautifully done.",
      "sub_message": "Take a deep breath.",
      "icon": "star",
      "animation": "confetti" // Frontend animation trigger
    },
    "progress_update": {
      "total_tasks_completed": 13,
      "today_completed": 3,
      "today_total": 6
    }
  },
  "message": "Task completed successfully"
}
```

**Side Effects**:
1. Update `user_progress.total_tasks_completed`
2. Check for milestone achievements (streaks, totals)
3. Generate story entry if milestone reached
4. Invalidate caches

**Caching Strategy**:
- Invalidate: `cache:tasks:today:{user_id}`
- Invalidate: `cache:progress:{user_id}`
- Invalidate: `cache:stories:{user_id}:{date}`

---

## MODULE 4: JOURNAL

### 4.1 Create Journal Entry with Voice Analysis

**Endpoint**: `POST /api/v1/journal/entry`

**Description**: Captures user's audio journal, transcribes it, analyzes emotion/mood/category using Gemini API, and generates AI insights.

**Request**:
```http
POST /api/v1/journal/entry
Content-Type: multipart/form-data
Authorization: Bearer {jwt_token}

{
  "date": "2025-01-29", // YYYY-MM-DD
  "audio_file": <binary_audio_file>,
  "audio_duration_seconds": 124,
  "entry_text": null // Optional: for text-only entries
}
```

**Response** (200 OK):
```json
{
  "success": true,
  "data": {
    "entry_id": "uuid",
    "date": "2025-01-29",
    "transcription": "I'm feeling a bit overwhelmed today, but taking this moment helps. I managed to replace scrolling with reading this morning. Felt the dopamine cravings but pushed through.",
    "audio_url": "https://storage.example.com/recordings/user_id/journal_xyz.mp3",
    "analysis": {
      "primary_emotion": "overwhelmed",
      "secondary_emotions": ["determined", "mindful"],
      "mood_rating": "calm", // Enum: great, good, calm, stressed, overwhelmed
      "sentiment_score": 0.6, // -1 to 1 (negative to positive)
      "energy_level": "medium"
    },
    "insights": [
      {
        "insight_id": "uuid",
        "insight_type": "pattern_detected",
        "title": "Positive Behavior Change",
        "description": "You successfully replaced scrolling with reading - building healthier habits!",
        "icon": "growth",
        "color": "#34C759"
      },
      {
        "insight_id": "uuid",
        "insight_type": "emotional_awareness",
        "title": "Self-Awareness Growing",
        "description": "Recognizing dopamine cravings shows increased mindfulness",
        "icon": "brain",
        "color": "#5856D6"
      }
    ],
    "summary": "Today you demonstrated strong self-control by choosing reading over scrolling despite feeling overwhelmed. Your awareness of dopamine patterns is a significant step in breaking the cycle.",
    "waveform_data": [0.2, 0.4, 0.6, 0.8, 0.5, 0.7, ...], // Voice intensity visualization
    "created_at": "2025-01-29T20:30:00Z"
  },
  "message": "Journal entry created successfully"
}
```

**Processing Flow**:
1. Upload audio to cloud storage
2. Extract waveform/voice metrics
3. Transcribe audio using Speech-to-Text
4. Send transcription to Gemini API with prompt:
   ```
   Analyze this journal entry:
   - Identify primary and secondary emotions
   - Rate overall mood (great/good/calm/stressed/overwhelmed)
   - Calculate sentiment score
   - Detect behavioral patterns (triggers, coping mechanisms)
   - Generate 2-3 personalized insights
   - Create a brief summary (2-3 sentences)
   ```
5. Save entry, analysis, and insights to database
6. Return complete response

**Caching Strategy**:
- Cache recent journal entries: `cache:journal:recent:{user_id}` (TTL: 10 minutes)
- Invalidate on: new entry creation

**Error Responses**:
- 400: Invalid audio format or date
- 409: Entry already exists for this date
- 503: AI analysis service unavailable

---

### 4.2 Get Past Journal Entries

**Endpoint**: `GET /api/v1/journal/entries`

**Description**: Returns paginated list of past journal entries with audio links and summaries.

**Request**:
```http
GET /api/v1/journal/entries
Authorization: Bearer {jwt_token}
Query Parameters:
  - page: integer (default: 1)
  - limit: integer (default: 10, max: 50)
  - from_date: YYYY-MM-DD (optional)
  - to_date: YYYY-MM-DD (optional)
  - mood_filter: string (optional) - Enum: great, good, calm, stressed, overwhelmed
```

**Response** (200 OK):
```json
{
  "success": true,
  "data": {
    "entries": [
      {
        "entry_id": "uuid",
        "date": "2025-01-29",
        "summary": "Today you demonstrated strong self-control by choosing reading over scrolling despite feeling overwhelmed.",
        "mood_rating": "calm",
        "mood_icon": "😌",
        "primary_emotion": "overwhelmed",
        "audio_url": "https://storage.example.com/recordings/user_id/journal_xyz.mp3",
        "audio_duration_seconds": 124,
        "waveform_data": [0.2, 0.4, 0.6, ...],
        "insights_count": 2,
        "created_at": "2025-01-29T20:30:00Z"
      },
      {
        "entry_id": "uuid",
        "date": "2025-01-28",
        "summary": "Hard morning. The silence was loud. I need to find better offline hobbies to fill the gaps.",
        "mood_rating": "stressed",
        "mood_icon": "😟",
        "primary_emotion": "anxious",
        "audio_url": "https://storage.example.com/recordings/user_id/journal_abc.mp3",
        "audio_duration_seconds": 98,
        "waveform_data": [0.3, 0.5, 0.4, ...],
        "insights_count": 1,
        "created_at": "2025-01-28T21:00:00Z"
      }
      // ... more entries
    ],
    "pagination": {
      "current_page": 1,
      "total_pages": 5,
      "total_entries": 42,
      "per_page": 10,
      "has_next": true,
      "has_previous": false
    }
  }
}
```

**Caching Strategy**:
- Cache paginated results: `cache:journal:list:{user_id}:page:{page}:{filters}` (TTL: 15 minutes)
- Cache individual entries: `cache:journal:entry:{entry_id}` (TTL: 30 minutes)

**Error Responses**:
- 404: No journal entries found

---

### 4.3 Get Single Journal Entry Details

**Endpoint**: `GET /api/v1/journal/entries/{entry_id}`

**Description**: Returns complete details of a specific journal entry including full transcription and insights.

**Request**:
```http
GET /api/v1/journal/entries/{entry_id}
Authorization: Bearer {jwt_token}
```

**Response** (200 OK):
```json
{
  "success": true,
  "data": {
    "entry_id": "uuid",
    "date": "2025-01-29",
    "transcription": "I'm feeling a bit overwhelmed today, but taking this moment helps...",
    "audio_url": "https://storage.example.com/recordings/user_id/journal_xyz.mp3",
    "audio_duration_seconds": 124,
    "waveform_data": [0.2, 0.4, 0.6, ...],
    "analysis": {
      "primary_emotion": "overwhelmed",
      "secondary_emotions": ["determined", "mindful"],
      "mood_rating": "calm",
      "sentiment_score": 0.6,
      "energy_level": "medium"
    },
    "insights": [
      {
        "insight_id": "uuid",
        "insight_type": "pattern_detected",
        "title": "Positive Behavior Change",
        "description": "You successfully replaced scrolling with reading - building healthier habits!",
        "icon": "growth",
        "color": "#34C759"
      }
    ],
    "summary": "Today you demonstrated strong self-control...",
    "created_at": "2025-01-29T20:30:00Z",
    "updated_at": "2025-01-29T20:30:00Z"
  }
}
```

**Caching Strategy**:
- Cache: `cache:journal:entry:{entry_id}` (TTL: 30 minutes)

---

## MODULE 5: PROFILE

### 5.1 Get User Profile

**Endpoint**: `GET /api/v1/profile`

**Description**: Returns complete user profile including subscription status, progress stats, and preferences.

**Request**:
```http
GET /api/v1/profile
Authorization: Bearer {jwt_token}
```

**Response** (200 OK):
```json
{
  "success": true,
  "data": {
    "user": {
      "user_id": "uuid",
      "email": "user@example.com",
      "full_name": "John Doe",
      "created_at": "2025-01-22T10:00:00Z",
      "timezone": "Asia/Kolkata",
      "onboarding_completed": true
    },
    "subscription": {
      "status": "active", // Enum: free, active, expired, cancelled
      "tier": "premium", // Enum: free, basic, premium, lifetime
      "started_at": "2025-01-25T00:00:00Z",
      "expires_at": "2025-02-25T23:59:59Z",
      "auto_renew": true,
      "revenuecat_subscriber_id": "rc_xxxxxxxxxxxx"
    },
    "progress": {
      "total_tasks_completed": 42,
      "total_days_active": 12,
      "current_focus_streak": 5,
      "longest_focus_streak": 8,
      "total_journal_entries": 10,
      "last_active_date": "2025-01-29"
    },
    "triggers": [
      {
        "trigger_id": "uuid",
        "activity_name": "Social media scrolling",
        "category": "social_media",
        "is_active": true
      },
      {
        "trigger_id": "uuid",
        "activity_name": "Snacking when bored",
        "category": "food",
        "is_active": true
      }
    ],
    "preferences": {
      "notifications_enabled": true,
      "daily_reminder_time": "07:00",
      "evening_reflection_time": "20:00",
      "voice_language": "en-US"
    }
  }
}
```

**Caching Strategy**:
- Cache profile data: `cache:profile:{user_id}` (TTL: 5 minutes)
- Cache subscription status separately: `cache:subscription:{user_id}` (TTL: 1 hour)
- Invalidate on: profile update, subscription change, progress update

---

### 5.2 Update User Profile

**Endpoint**: `PUT /api/v1/profile`

**Description**: Updates user profile information and preferences.

**Request**:
```http
PUT /api/v1/profile
Content-Type: application/json
Authorization: Bearer {jwt_token}

{
  "full_name": "John Doe",
  "timezone": "Asia/Kolkata",
  "preferences": {
    "notifications_enabled": true,
    "daily_reminder_time": "07:00",
    "evening_reflection_time": "20:00",
    "voice_language": "en-US"
  }
}
```

**Response** (200 OK):
```json
{
  "success": true,
  "data": {
    "user_id": "uuid",
    "full_name": "John Doe",
    "timezone": "Asia/Kolkata",
    "updated_at": "2025-01-29T15:45:00Z"
  },
  "message": "Profile updated successfully"
}
```

**Caching Strategy**:
- Invalidate: `cache:profile:{user_id}`

---

## MODULE 6: SUBSCRIPTION

### 6.1 Get Subscription Packages

**Endpoint**: `GET /api/v1/subscription/packages`

**Description**: Returns available subscription tiers/packages with pricing and features.

**Request**:
```http
GET /api/v1/subscription/packages
Authorization: Bearer {jwt_token}
Query Parameters:
  - platform: string (ios | android | web) - Required for platform-specific pricing
```

**Response** (200 OK):
```json
{
  "success": true,
  "data": {
    "packages": [
      {
        "package_id": "free",
        "tier": "free",
        "name": "Free",
        "description": "Basic features to get started",
        "price": 0,
        "currency": "USD",
        "billing_period": "lifetime",
        "revenuecat_identifier": null,
        "features": [
          "1 journal entry per month",
          "Unlimited daily tasks",
          "Basic progress tracking",
          "Limited ads included"
        ],
        "limitations": [
          "No AI insights",
          "No voice transcription",
          "No advanced analytics",
          "Advertisement supported"
        ],
        "trial_available": false,
        "is_default": true
      },
      {
        "package_id": "monthly_premium",
        "tier": "monthly",
        "name": "Monthly Premium",
        "description": "Full AI-powered experience",
        "price": 8.00,
        "currency": "USD",
        "billing_period": "monthly",
        "revenuecat_identifier": "rc_monthly_premium_800",
        "product_identifier": "monthly_premium_800",
        "features": [
          "Unlimited journal entries",
          "AI-powered insights & analysis",
          "Voice transcription",
          "Progress reports & analytics",
          "Ad-free experience",
          "Daily motivation & coaching"
        ],
        "trial_available": true,
        "trial_duration_days": 7,
        "savings": null
      },
      {
        "package_id": "annual_premium",
        "tier": "annual",
        "name": "Annual Premium",
        "description": "Save 25% with yearly billing",
        "price": 70.00,
        "currency": "USD",
        "billing_period": "annual",
        "revenuecat_identifier": "rc_annual_premium_7000",
        "product_identifier": "annual_premium_7000",
        "features": [
          "All Monthly Premium features",
          "Priority customer support",
          "Early access to new features",
          "25% savings vs monthly ($96/year → $70/year)"
        ],
        "trial_available": true,
        "trial_duration_days": 7,
        "badge": "Best Value",
        "savings": {
          "percentage": 25,
          "amount": 26.00,
          "comparison": "vs Monthly ($8 × 12 = $96)"
        }
      }
    ],
    "current_subscription": {
      "tier": "free",
      "status": "active",
      "expires_at": null
    },
    "feature_comparison": {
      "free": {
        "journals_per_month": 1,
        "ai_insights": false,
        "voice_transcription": false,
        "unlimited_tasks": true,
        "progress_reports": false,
        "ads": true,
        "priority_support": false
      },
      "monthly": {
        "journals_per_month": "unlimited",
        "ai_insights": true,
        "voice_transcription": true,
        "unlimited_tasks": true,
        "progress_reports": true,
        "ads": false,
        "priority_support": false
      },
      "annual": {
        "journals_per_month": "unlimited",
        "ai_insights": true,
        "voice_transcription": true,
        "unlimited_tasks": true,
        "progress_reports": true,
        "ads": false,
        "priority_support": true
      }
    }
  }
}
```

**Caching Strategy**:
- Cache packages: `cache:subscription:packages:{platform}` (TTL: 1 hour)
- Update cache when pricing changes in RevenueCat

---

### 6.2 Purchase Subscription (RevenueCat Integration)

**Endpoint**: `POST /api/v1/subscription/purchase`

**Description**: Initiates subscription purchase via RevenueCat. The actual payment is handled by RevenueCat SDK on the client side. This endpoint verifies the purchase with RevenueCat and activates the subscription, storing all order data.

**Request**:
```http
POST /api/v1/subscription/purchase
Content-Type: application/json
Authorization: Bearer {jwt_token}

{
  "package_id": "annual_premium",
  "revenuecat_subscriber_id": "rc_xxxxxxxxxxxxxx", // From RevenueCat SDK
  "platform": "ios", // or "android"
  "product_identifier": "annual_premium_7000"
}
```

**Response** (200 OK):
```json
{
  "success": true,
  "data": {
    "subscription": {
      "subscription_id": "uuid",
      "user_id": "uuid",
      "tier": "annual",
      "status": "active",
      "started_at": "2025-01-29T16:00:00Z",
      "expires_at": "2026-01-29T23:59:59Z",
      "auto_renew": true,
      "trial_end_date": "2025-02-05T23:59:59Z",
      "revenuecat_subscriber_id": "rc_xxxxxxxxxxxxxx",
      "revenuecat_original_app_user_id": "user_uuid",
      "revenuecat_entitlements": [
        "premium_features",
        "ai_insights",
        "unlimited_journals",
        "priority_support"
      ],
      "platform": "ios",
      "product_identifier": "annual_premium_7000",
      "price_paid": 70.00,
      "currency": "USD",
      "store_transaction_id": "1000000123456789",
      "store_original_transaction_id": "1000000123456789",
      "original_purchase_date": "2025-01-29T16:00:00Z",
      "latest_purchase_date": "2025-01-29T16:00:00Z"
    },
    "unlocked_features": {
      "journals_per_month": "unlimited",
      "ai_insights": true,
      "ai_analysis": true,
      "progress_reports": true,
      "voice_transcription": true,
      "ads_enabled": false,
      "advanced_analytics": true,
      "priority_support": true
    },
    "revenuecat_order_data": {
      "subscriber_id": "rc_xxxxxxxxxxxxxx",
      "entitlement_identifiers": ["premium"],
      "product_identifier": "annual_premium_7000",
      "purchase_date": "2025-01-29T16:00:00Z",
      "original_purchase_date": "2025-01-29T16:00:00Z",
      "expiration_date": "2026-01-29T23:59:59Z",
      "is_sandbox": false,
      "store": "app_store"
    }
  },
  "message": "Subscription activated successfully"
}
```

**Processing Flow**:
1. Receive purchase request from client
2. Verify subscriber_id with RevenueCat REST API
3. Fetch subscriber info from RevenueCat:
   ```
   GET https://api.revenuecat.com/v1/subscribers/{subscriber_id}
   Headers: X-Platform: ios/android, Authorization: Bearer {RC_API_KEY}
   ```
4. Extract subscription and transaction data from RevenueCat response
5. Create/update subscription record in database with all RevenueCat data:
   - Subscription tier and status
   - Purchase dates and transaction IDs
   - Entitlements and product identifiers
   - Price and currency information
6. Create subscription history entry
7. Update user's feature limits
8. Invalidate relevant caches
9. Return confirmation with unlocked features

**RevenueCat API Response Structure (for reference)**:
```json
{
  "subscriber": {
    "original_app_user_id": "user_uuid",
    "subscriptions": {
      "annual_premium_7000": {
        "billing_issues_detected_at": null,
        "expires_date": "2026-01-29T23:59:59Z",
        "grace_period_expires_date": null,
        "is_sandbox": false,
        "original_purchase_date": "2025-01-29T16:00:00Z",
        "period_type": "normal",
        "purchase_date": "2025-01-29T16:00:00Z",
        "store": "app_store",
        "unsubscribe_detected_at": null
      }
    },
    "entitlements": {
      "premium": {
        "expires_date": "2026-01-29T23:59:59Z",
        "grace_period_expires_date": null,
        "product_identifier": "annual_premium_7000",
        "purchase_date": "2025-01-29T16:00:00Z"
      }
    },
    "non_subscriptions": {},
    "first_seen": "2025-01-29T16:00:00Z",
    "last_seen": "2025-01-29T16:00:00Z",
    "management_url": "https://apps.apple.com/account/subscriptions",
    "original_application_version": "1.0",
    "original_purchase_date": "2025-01-29T16:00:00Z",
    "other_purchases": {}
  }
}
```

**Database Storage - Subscription Table**:
```sql
INSERT INTO subscriptions (
  subscription_id,
  user_id,
  tier,
  status,
  started_at,
  expires_at,
  auto_renew,
  trial_end_date,
  revenuecat_subscriber_id,
  revenuecat_original_app_user_id,
  revenuecat_entitlements,
  platform,
  product_identifier,
  price_paid,
  currency,
  store_transaction_id,
  store_original_transaction_id,
  original_purchase_date,
  latest_purchase_date,
  last_revenuecat_sync
) VALUES (
  'uuid',
  'user_uuid',
  'annual',
  'active',
  '2025-01-29 16:00:00',
  '2026-01-29 23:59:59',
  true,
  '2025-02-05 23:59:59',
  'rc_xxxxxxxxxxxxxx',
  'user_uuid',
  '["premium_features", "ai_insights"]',
  'ios',
  'annual_premium_7000',
  70.00,
  'USD',
  '1000000123456789',
  '1000000123456789',
  '2025-01-29 16:00:00',
  '2025-01-29 16:00:00',
  '2025-01-29 16:00:00'
);
```

**Database Storage - Subscription History**:
```sql
INSERT INTO subscription_history (
  history_id,
  subscription_id,
  user_id,
  event_type,
  previous_tier,
  new_tier,
  previous_status,
  new_status,
  price_paid,
  currency,
  revenuecat_event_data,
  store_transaction_id
) VALUES (
  'uuid',
  'subscription_uuid',
  'user_uuid',
  'purchase',
  'free',
  'annual',
  null,
  'active',
  70.00,
  'USD',
  '{...full RevenueCat response...}',
  '1000000123456789'
);
```

**Caching Strategy**:
- Invalidate: `cache:subscription:{user_id}`
- Invalidate: `cache:subscription:status:{user_id}`
- Invalidate: `cache:profile:{user_id}`

**Error Responses**:
- 400: Invalid package_id or subscriber_id
- 402: Payment failed (from RevenueCat)
- 404: Subscriber not found in RevenueCat
- 409: Subscription already active
- 503: RevenueCat API unavailable

---

### 6.3 Check Subscription Status

**Endpoint**: `GET /api/v1/subscription/status`

**Description**: Returns current subscription status by querying RevenueCat (ensures real-time accuracy) and linking with stored order data.

**Request**:
```http
GET /api/v1/subscription/status
Authorization: Bearer {jwt_token}
Query Parameters:
  - force_refresh: boolean (default: false) - Bypass cache and query RevenueCat directly
```

**Response** (200 OK):
```json
{
  "success": true,
  "data": {
    "status": "active",
    "tier": "annual",
    "started_at": "2025-01-29T16:00:00Z",
    "expires_at": "2026-01-29T23:59:59Z",
    "auto_renew": true,
    "is_in_trial": false,
    "trial_end_date": null,
    "cancelled_at": null,
    "revenuecat_subscriber_id": "rc_xxxxxxxxxxxx",
    "platform": "ios",
    "product_identifier": "annual_premium_7000",
    "price_paid": 70.00,
    "currency": "USD",
    "original_purchase_date": "2025-01-29T16:00:00Z",
    "latest_purchase_date": "2025-01-29T16:00:00Z",
    "store_transaction_id": "1000000123456789",
    "billing_issues": false,
    "active_entitlements": [
      "premium_features",
      "ai_insights",
      "unlimited_journals",
      "priority_support"
    ],
    "feature_limits": {
      "journals_per_month": "unlimited",
      "ai_insights": true,
      "ai_analysis": true,
      "progress_reports": true,
      "voice_transcription": true,
      "ads_enabled": false,
      "advanced_analytics": true,
      "priority_support": true
    },
    "next_billing_date": "2026-01-29T23:59:59Z",
    "management_url": "https://apps.apple.com/account/subscriptions"
  }
}
```

**For Free Tier Users**:
```json
{
  "success": true,
  "data": {
    "status": "active",
    "tier": "free",
    "started_at": "2025-01-22T10:00:00Z",
    "expires_at": null,
    "auto_renew": false,
    "is_in_trial": false,
    "revenuecat_subscriber_id": null,
    "platform": null,
    "feature_limits": {
      "journals_per_month": 1,
      "ai_insights": false,
      "ai_analysis": false,
      "progress_reports": false,
      "voice_transcription": false,
      "ads_enabled": true,
      "advanced_analytics": false,
      "priority_support": false
    },
    "upgrade_available": true,
    "recommended_tier": "annual"
  }
}
```

**Caching Strategy**:
- Cache status: `cache:subscription:status:{user_id}` (TTL: 5 minutes)
- Force refresh bypasses cache and queries RevenueCat directly
- Store full RevenueCat response in cache for quick access

---

### 6.4 Cancel Subscription

**Endpoint**: `POST /api/v1/subscription/cancel`

**Description**: Cancels auto-renewal of subscription (user retains access until expiration). Creates history record for audit trail.

**Request**:
```http
POST /api/v1/subscription/cancel
Content-Type: application/json
Authorization: Bearer {jwt_token}

{
  "reason": "too_expensive", // Optional: for analytics
  "feedback": "Great app, but I can't afford it right now" // Optional
}
```

**Response** (200 OK):
```json
{
  "success": true,
  "data": {
    "subscription": {
      "subscription_id": "uuid",
      "status": "cancelled",
      "tier": "annual",
      "auto_renew": false,
      "expires_at": "2026-01-29T23:59:59Z",
      "cancelled_at": "2025-02-01T17:00:00Z",
      "days_remaining": 362
    },
    "message": "Your subscription will remain active until January 29, 2026. You can reactivate anytime before then.",
    "downgrade_info": {
      "downgrade_date": "2026-01-29T23:59:59Z",
      "new_tier": "free",
      "features_to_lose": [
        "Unlimited journals (limited to 1/month)",
        "AI insights & analysis",
        "Voice transcription",
        "Ad-free experience"
      ]
    }
  },
  "message": "Subscription cancelled successfully"
}
```

**Processing Flow**:
1. Verify user has active subscription
2. Call RevenueCat API to cancel auto-renewal (if not cancelled via App Store/Play Store)
3. Update subscription record:
   ```sql
   UPDATE subscriptions 
   SET auto_renew = false, 
       cancelled_at = NOW(), 
       status = 'cancelled',
       updated_at = NOW()
   WHERE user_id = ? AND status = 'active'
   ```
4. Create subscription history entry:
   ```sql
   INSERT INTO subscription_history (
     event_type, previous_status, new_status, 
     revenuecat_event_data
   ) VALUES (
     'cancellation', 'active', 'cancelled', 
     '{"reason": "too_expensive", "feedback": "..."}'
   )
   ```
5. User retains premium access until expires_at date
6. Send confirmation email with reactivation options

**Caching Strategy**:
- Invalidate: `cache:subscription:{user_id}`
- Invalidate: `cache:subscription:status:{user_id}`

**Note**: User keeps premium features until expiration date. On expiration, a scheduled job will downgrade to free tier.

---

### 6.5 Restore Purchases (iOS/Android)

**Endpoint**: `POST /api/v1/subscription/restore`

**Description**: Restores previous purchases from App Store/Play Store via RevenueCat.

**Request**:
```http
POST /api/v1/subscription/restore
Content-Type: application/json
Authorization: Bearer {jwt_token}

{
  "platform": "ios" // or "android"
}
```

**Response** (200 OK):
```json
{
  "success": true,
  "data": {
    "restored": true,
    "subscription": {
      "tier": "annual",
      "status": "active",
      "expires_at": "2026-01-29T23:59:59Z",
      "product_identifier": "annual_premium_7000",
      "original_purchase_date": "2025-01-29T16:00:00Z"
    }
  },
  "message": "Subscription restored successfully"
}
```

**Error Responses**:
- 404: No previous purchases found

---

### 6.6 RevenueCat Webhook Handler

**Endpoint**: `POST /api/v1/webhooks/revenuecat`

**Description**: Receives and processes subscription events from RevenueCat webhooks. This endpoint handles automatic synchronization of subscription status changes.

**Webhook Events Handled**:
- `INITIAL_PURCHASE` - First time subscription purchase
- `RENEWAL` - Subscription auto-renewed
- `CANCELLATION` - User cancelled subscription
- `UNCANCELLATION` - User reactivated cancelled subscription
- `NON_RENEWING_PURCHASE` - One-time purchase
- `EXPIRATION` - Subscription expired
- `BILLING_ISSUE` - Payment failed
- `PRODUCT_CHANGE` - User upgraded/downgraded tier

**Request** (from RevenueCat):
```http
POST /api/v1/webhooks/revenuecat
Content-Type: application/json
X-Revenuecat-Signature: {webhook_signature}

{
  "api_version": "1.0",
  "event": {
    "type": "RENEWAL",
    "app_user_id": "user_uuid",
    "aliases": ["rc_xxxxxxxxxxxxxx"],
    "original_app_user_id": "user_uuid",
    "id": "webhook_event_id",
    "event_timestamp_ms": 1706524800000,
    "product_id": "annual_premium_7000",
    "period_type": "NORMAL",
    "purchased_at_ms": 1706524800000,
    "expiration_at_ms": 1738060799000,
    "environment": "PRODUCTION",
    "entitlement_id": "premium",
    "entitlement_ids": ["premium"],
    "presented_offering_id": "default",
    "transaction_id": "1000000123456789",
    "original_transaction_id": "1000000123456789",
    "is_family_share": false,
    "country_code": "US",
    "app_id": "com.dopaminedetox.app",
    "currency": "USD",
    "price": 70.00,
    "price_in_purchased_currency": 70.00,
    "subscriber_attributes": {},
    "store": "APP_STORE",
    "takehome_percentage": 0.85,
    "offer_code": null,
    "is_trial_conversion": false,
    "cancel_reason": null,
    "new_product_id": null,
    "presented_offering_identifier": null
  }
}
```

**Processing Flow by Event Type**:

**INITIAL_PURCHASE / RENEWAL**:
1. Verify webhook signature
2. Find user by app_user_id
3. Update subscription record:
   ```sql
   UPDATE subscriptions SET
     tier = (derive from product_id),
     status = 'active',
     expires_at = FROM_UNIXTIME(expiration_at_ms/1000),
     latest_purchase_date = FROM_UNIXTIME(purchased_at_ms/1000),
     store_transaction_id = transaction_id,
     price_paid = price,
     currency = currency,
     last_revenuecat_sync = NOW()
   WHERE user_id = app_user_id
   ```
4. Create subscription history entry
5. Invalidate caches

**CANCELLATION**:
1. Update subscription:
   ```sql
   UPDATE subscriptions SET
     auto_renew = false,
     cancelled_at = FROM_UNIXTIME(event_timestamp_ms/1000),
     status = 'cancelled'
   WHERE user_id = app_user_id
   ```
2. User keeps access until expiration

**EXPIRATION**:
1. Update subscription:
   ```sql
   UPDATE subscriptions SET
     status = 'expired',
     tier = 'free'
   WHERE user_id = app_user_id
   ```
2. Downgrade user to free tier
3. Apply free tier feature limits
4. Create history entry

**BILLING_ISSUE**:
1. Update subscription:
   ```sql
   UPDATE subscriptions SET
     status = 'billing_issue'
   WHERE user_id = app_user_id
   ```
2. Send notification to user
3. Grace period: Keep premium features for 3 days

**PRODUCT_CHANGE** (Upgrade/Downgrade):
1. Extract old and new product_id
2. Update subscription tier
3. Create history entry with upgrade/downgrade event
4. Apply new feature limits immediately

**Response** (200 OK):
```json
{
  "received": true
}
```

**Security**:
- Verify webhook signature using RevenueCat shared secret
- Validate event structure
- Idempotency: Check if event already processed (by event.id)
- Store raw webhook payload in subscription_history for audit

**Example Signature Verification** (Python):
```python
import hmac
import hashlib

def verify_webhook_signature(payload, signature, secret):
    expected_sig = hmac.new(
        secret.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected_sig, signature)
```

**Idempotency Check**:
```sql
SELECT 1 FROM subscription_history 
WHERE revenuecat_event_data->>'event.id' = ?
LIMIT 1
```

**Error Handling**:
- Invalid signature: Return 401
- Unknown event type: Log and return 200 (don't fail)
- Database error: Return 500, RevenueCat will retry

---

## MODULE 7: FEATURE LIMIT ENFORCEMENT

### 7.1 Check Feature Access

**Endpoint**: `GET /api/v1/features/check`

**Description**: Checks if user has access to a specific feature based on their subscription tier.

**Request**:
```http
GET /api/v1/features/check
Authorization: Bearer {jwt_token}
Query Parameters:
  - feature: string (required) - Feature to check (ai_insights, voice_transcription, unlimited_journals, etc.)
```

**Response** (200 OK):
```json
{
  "success": true,
  "data": {
    "feature": "ai_insights",
    "has_access": false,
    "current_tier": "free",
    "required_tier": "monthly",
    "reason": "This feature requires a premium subscription",
    "upgrade_url": "/subscription/packages"
  }
}
```

**For Allowed Feature**:
```json
{
  "success": true,
  "data": {
    "feature": "unlimited_tasks",
    "has_access": true,
    "current_tier": "free"
  }
}
```

---

### 7.2 Check Journal Limit

**Endpoint**: `GET /api/v1/features/journal-limit`

**Description**: Returns user's journal usage for current month and limit based on tier.

**Request**:
```http
GET /api/v1/features/journal-limit
Authorization: Bearer {jwt_token}
```

**Response** (200 OK - Free Tier):
```json
{
  "success": true,
  "data": {
    "tier": "free",
    "journals_this_month": 1,
    "journal_limit": 1,
    "remaining": 0,
    "limit_reached": true,
    "reset_date": "2025-03-01T00:00:00Z",
    "can_create_journal": false,
    "upgrade_message": "Upgrade to Premium for unlimited journal entries"
  }
}
```

**Response** (200 OK - Premium Tier):
```json
{
  "success": true,
  "data": {
    "tier": "annual",
    "journals_this_month": 15,
    "journal_limit": -1,
    "remaining": "unlimited",
    "limit_reached": false,
    "can_create_journal": true
  }
}
```

**Caching Strategy**:
- Cache: `cache:journal:limit:{user_id}:{month}` (TTL: 5 minutes)
- Invalidate on: new journal entry creation

---

### 7.3 Middleware - Feature Gate

**Implementation Reference** (Express.js example):
```javascript
// Middleware to check feature access before allowing endpoint access
async function requireFeature(featureName) {
  return async (req, res, next) => {
    const userId = req.user.user_id;
    
    // Get user's subscription from cache or DB
    const subscription = await getSubscription(userId);
    const tier = subscription.tier;
    
    // Check feature limits
    const features = FEATURE_LIMITS[tier];
    
    if (!features[featureName]) {
      return res.status(403).json({
        success: false,
        error: {
          code: 'FEATURE_LOCKED',
          message: `This feature requires a premium subscription`,
          required_tier: 'monthly',
          current_tier: tier,
          upgrade_url: '/api/v1/subscription/packages'
        }
      });
    }
    
    next();
  };
}

// Usage in routes
app.post('/api/v1/journal/entry', 
  authenticate, 
  requireFeature('ai_insights'),  // Block if free tier
  createJournalEntry
);
```

**Feature Limits Constants**:
```javascript
const FEATURE_LIMITS = {
  free: {
    journals_per_month: 1,
    ai_insights: false,
    ai_analysis: false,
    voice_transcription: false,
    progress_reports: false,
    unlimited_tasks: true,
    ads_enabled: true,
    advanced_analytics: false,
    priority_support: false
  },
  monthly: {
    journals_per_month: -1, // unlimited
    ai_insights: true,
    ai_analysis: true,
    voice_transcription: true,
    progress_reports: true,
    unlimited_tasks: true,
    ads_enabled: false,
    advanced_analytics: true,
    priority_support: false
  },
  annual: {
    journals_per_month: -1, // unlimited
    ai_insights: true,
    ai_analysis: true,
    voice_transcription: true,
    progress_reports: true,
    unlimited_tasks: true,
    ads_enabled: false,
    advanced_analytics: true,
    priority_support: true
  }
};
```

---

## REDIS CACHING STRATEGY

### Cache Key Naming Convention
```
cache:{module}:{resource}:{identifier}:{optional_params}
```

### Cache TTL Guidelines
- **User Sessions**: 24 hours
- **Profile Data**: 5 minutes
- **Subscription Status**: 1 hour (5 minutes for critical checks)
- **Today's Tasks**: 5 minutes
- **Stories/Insights**: 15 minutes
- **Journal Entries List**: 15 minutes
- **Individual Journal Entry**: 30 minutes
- **Onboarding Progress**: 1 hour
- **Subscription Packages**: 1 hour

### Critical Cache Keys

```redis
# User Profile
cache:profile:{user_id} -> JSON (TTL: 5min)

# Subscription
cache:subscription:{user_id} -> JSON (TTL: 1hr)
cache:subscription:status:{user_id} -> JSON (TTL: 5min)
cache:subscription:packages:{platform} -> JSON (TTL: 1hr)

# Tasks
cache:tasks:today:{user_id} -> JSON (TTL: 5min)
cache:tasks:plan:{plan_id} -> JSON (TTL: 10min)

# Journal
cache:journal:recent:{user_id} -> JSON Array (TTL: 10min)
cache:journal:entry:{entry_id} -> JSON (TTL: 30min)
cache:journal:list:{user_id}:page:{page}:{filters} -> JSON (TTL: 15min)

# Stories
cache:stories:{user_id}:{date} -> JSON Array (TTL: 15min)

# Progress
cache:progress:{user_id} -> JSON (TTL: 10min)

# Onboarding
cache:onboarding:{user_id} -> JSON (TTL: 1hr)
```

### Cache Invalidation Rules

**On Task Completion**:
```
DELETE cache:tasks:today:{user_id}
DELETE cache:progress:{user_id}
DELETE cache:stories:{user_id}:{date}
```

**On Journal Entry Creation**:
```
DELETE cache:journal:recent:{user_id}
DELETE cache:journal:list:{user_id}:*
DELETE cache:stories:{user_id}:{date}
```

**On Profile Update**:
```
DELETE cache:profile:{user_id}
```

**On Subscription Change**:
```
DELETE cache:subscription:{user_id}
DELETE cache:subscription:status:{user_id}
DELETE cache:profile:{user_id}
```

### Cache-Aside Pattern Implementation

```python
# Pseudocode for cache-aside pattern
def get_user_profile(user_id):
    cache_key = f"cache:profile:{user_id}"
    
    # Try to get from cache
    cached_data = redis.get(cache_key)
    if cached_data:
        return json.loads(cached_data)
    
    # Cache miss - query database
    profile_data = db.query("SELECT * FROM users WHERE user_id = ?", user_id)
    
    # Store in cache for 5 minutes
    redis.setex(cache_key, 300, json.dumps(profile_data))
    
    return profile_data
```

---

## SCHEDULED JOBS & CRON TASKS

### 1. Subscription Expiration Check (Daily)
**Frequency**: Every day at 00:00 UTC

**Purpose**: Check for expired subscriptions and downgrade users to free tier

**Process**:
```sql
-- Find expired subscriptions
SELECT subscription_id, user_id, tier 
FROM subscriptions 
WHERE status IN ('active', 'cancelled')
  AND expires_at < NOW()
  AND tier != 'free';

-- Update to free tier
UPDATE subscriptions 
SET tier = 'free', 
    status = 'expired',
    updated_at = NOW()
WHERE expires_at < NOW() 
  AND status IN ('active', 'cancelled');

-- Create history entries
INSERT INTO subscription_history (
  subscription_id, user_id, event_type,
  previous_tier, new_tier, previous_status, new_status
) 
SELECT subscription_id, user_id, 'expiration',
       tier, 'free', 'active', 'expired'
FROM subscriptions WHERE expires_at < NOW();
```

**Cache Invalidation**:
```
For each expired subscription:
  DELETE cache:subscription:{user_id}
  DELETE cache:subscription:status:{user_id}
  DELETE cache:profile:{user_id}
```

**Notification**: Send email to user about expiration and downgrade

---

### 2. Billing Issue Grace Period (Daily)
**Frequency**: Every 6 hours

**Purpose**: Check subscriptions with billing issues and handle grace period expiration

**Process**:
```sql
-- Find subscriptions with billing issues past grace period (3 days)
SELECT subscription_id, user_id 
FROM subscriptions 
WHERE status = 'billing_issue'
  AND updated_at < NOW() - INTERVAL '3 days';

-- Downgrade after grace period
UPDATE subscriptions 
SET tier = 'free', 
    status = 'expired'
WHERE status = 'billing_issue'
  AND updated_at < NOW() - INTERVAL '3 days';
```

---

### 3. RevenueCat Sync (Hourly)
**Frequency**: Every hour

**Purpose**: Sync subscription status with RevenueCat for users with active subscriptions

**Process**:
```python
async def sync_active_subscriptions():
    # Get users with active premium subscriptions
    subscriptions = db.query("""
        SELECT user_id, revenuecat_subscriber_id 
        FROM subscriptions 
        WHERE tier IN ('monthly', 'annual')
          AND status = 'active'
          AND revenuecat_subscriber_id IS NOT NULL
    """)
    
    for sub in subscriptions:
        # Query RevenueCat API
        rc_data = await revenuecat.get_subscriber(
            sub.revenuecat_subscriber_id
        )
        
        # Check if status changed
        if rc_data.status != sub.status:
            update_subscription_from_revenuecat(sub.user_id, rc_data)
```

---

### 4. Monthly Journal Limit Reset (Monthly)
**Frequency**: First day of each month at 00:00 UTC

**Purpose**: Reset journal entry counter for free tier users

**Process**:
```
For each free tier user:
  DELETE cache:journal:limit:{user_id}:{previous_month}
  # Cache will auto-populate with new month's count on first access
```

---

### 5. Subscription Analytics Aggregation (Daily)
**Frequency**: Every day at 02:00 UTC

**Purpose**: Aggregate subscription metrics for analytics dashboard

**Process**:
```sql
-- Daily subscription metrics
INSERT INTO subscription_analytics (
  date, 
  new_subscribers_monthly,
  new_subscribers_annual,
  cancellations,
  active_subscribers,
  mrr,
  churn_rate
)
SELECT 
  CURRENT_DATE,
  COUNT(*) FILTER (WHERE tier = 'monthly' AND DATE(started_at) = CURRENT_DATE),
  COUNT(*) FILTER (WHERE tier = 'annual' AND DATE(started_at) = CURRENT_DATE),
  COUNT(*) FILTER (WHERE DATE(cancelled_at) = CURRENT_DATE),
  COUNT(*) FILTER (WHERE status = 'active' AND tier != 'free'),
  SUM(CASE 
    WHEN tier = 'monthly' THEN 8.00 
    WHEN tier = 'annual' THEN 5.83  -- $70/12
    ELSE 0 
  END),
  (SELECT COUNT(*) FROM subscription_history 
   WHERE event_type = 'cancellation' 
   AND DATE(created_at) = CURRENT_DATE) * 1.0 / 
  NULLIF((SELECT COUNT(*) FROM subscriptions 
          WHERE status = 'active' AND tier != 'free'), 0)
FROM subscriptions;
```

---

## EXTERNAL SERVICE INTEGRATIONS

### 1. Speech-to-Text Services
**Options**:
- Google Cloud Speech-to-Text (Recommended)
- AWS Transcribe
- Azure Speech Services

**Configuration**:
```json
{
  "provider": "google",
  "language": "en-US",
  "encoding": "LINEAR16",
  "sample_rate": 16000,
  "enable_automatic_punctuation": true,
  "model": "default" // or "phone_call", "video", "command_and_search"
}
```

### 2. Gemini API (LLM Analysis)
**Use Cases**:
- Extract tasks from voice planning
- Analyze journal entries for emotions/insights
- Generate personalized affirmations
- Detect behavioral patterns

**Example Prompt Structure**:
```
System: You are an empathetic AI coach for a dopamine detox app.

User Journal: "{transcription}"

Tasks:
1. Identify primary emotion (overwhelmed, stressed, calm, happy, anxious)
2. List 2-3 secondary emotions
3. Detect mentioned triggers (social media, food, gaming, etc.)
4. Identify coping strategies used
5. Generate 2-3 supportive insights (max 30 words each)
6. Create a summary (2-3 sentences)

Output as JSON.
```

### 3. RevenueCat Integration
**Purpose**: Subscription management and payment processing

**Setup**:
1. Create RevenueCat project
2. Configure App Store Connect / Google Play Console
3. Create products and offerings
4. Set up webhook for subscription events

**Webhook Events to Handle**:
- `INITIAL_PURCHASE`
- `RENEWAL`
- `CANCELLATION`
- `EXPIRATION`
- `BILLING_ISSUE`

**Webhook Endpoint**: `POST /api/v1/webhooks/revenuecat`

---

## API DOCUMENTATION FOR AI CODING AGENTS

### Base URL
```
Production: https://api.dopaminedetox.app/api/v1
Staging: https://staging-api.dopaminedetox.app/api/v1
```

### Authentication
All endpoints (except registration/login) require JWT authentication.

**Header**:
```
Authorization: Bearer {jwt_token}
```

**Token Structure**:
```json
{
  "user_id": "uuid",
  "email": "user@example.com",
  "tier": "premium",
  "iat": 1706524800,
  "exp": 1706611200
}
```

### Standard Response Format
```json
{
  "success": true | false,
  "data": { ... } | null,
  "message": "Human-readable message",
  "error": { // Only on failure
    "code": "ERROR_CODE",
    "message": "Detailed error message",
    "field": "field_name" // For validation errors
  }
}
```

### HTTP Status Codes
- `200`: Success
- `201`: Created
- `400`: Bad Request (validation error)
- `401`: Unauthorized (invalid/expired token)
- `403`: Forbidden (insufficient permissions)
- `404`: Not Found
- `409`: Conflict (duplicate resource)
- `413`: Payload Too Large
- `429`: Too Many Requests (rate limit)
- `500`: Internal Server Error
- `503`: Service Unavailable (external service down)

### Rate Limiting
```
Per User:
- Authentication endpoints: 5 requests/minute
- Journal/Task creation: 30 requests/minute
- Read endpoints: 100 requests/minute
- Voice upload: 10 requests/minute (due to processing cost)

Response Header:
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 87
X-RateLimit-Reset: 1706525400
```

### File Upload Limits
- Voice recordings: Max 10MB, formats: mp3, wav, m4a, ogg
- Profile pictures: Max 5MB, formats: jpg, png, webp

### Error Codes
```
AUTH_001: Invalid credentials
AUTH_002: Token expired
AUTH_003: Account locked
TASK_001: Task not found
TASK_002: Daily plan already exists
JOURNAL_001: Entry already exists for date
JOURNAL_002: Transcription failed
SUB_001: Invalid subscription package
SUB_002: Payment processing error
SUB_003: Subscription already active
VOICE_001: Invalid audio format
VOICE_002: Audio too short (<3 seconds)
VOICE_003: Transcription service unavailable
```

---

## DATABASE QUERY OPTIMIZATION

### Indexes for Heavy Queries

```sql
-- Tasks queries
CREATE INDEX idx_tasks_user_date ON tasks(user_id, due_date);
CREATE INDEX idx_tasks_plan_order ON tasks(plan_id, order_index);
CREATE INDEX idx_tasks_completed ON tasks(user_id, completed, due_date);

-- Journal queries
CREATE INDEX idx_journal_user_date ON journal_entries(user_id, date DESC);
CREATE INDEX idx_journal_created ON journal_entries(user_id, created_at DESC);
CREATE INDEX idx_journal_mood ON journal_entries(user_id, mood_rating);

-- Stories generation
CREATE INDEX idx_checkins_user_date ON daily_checkins(user_id, date DESC);
CREATE INDEX idx_progress_user ON user_progress(user_id, last_active_date);

-- Subscription queries
CREATE INDEX idx_subscription_user ON subscriptions(user_id);
CREATE UNIQUE INDEX idx_subscription_revenuecat ON subscriptions(revenuecat_subscriber_id) 
  WHERE revenuecat_subscriber_id IS NOT NULL;
CREATE INDEX idx_subscription_status_expiry ON subscriptions(status, expires_at);
CREATE INDEX idx_subscription_tier_status ON subscriptions(tier, status);
CREATE INDEX idx_subscription_expiring_soon ON subscriptions(expires_at) 
  WHERE status = 'active' AND expires_at IS NOT NULL;

-- Subscription history
CREATE INDEX idx_sub_history_sub ON subscription_history(subscription_id, created_at DESC);
CREATE INDEX idx_sub_history_user_event ON subscription_history(user_id, event_type, created_at DESC);
CREATE INDEX idx_sub_history_event_date ON subscription_history(event_type, created_at DESC);
```


### Complex Query Examples

**Get Today's Stories (Cached)**:
```sql
-- Query 1: Task completion story
SELECT 
    COUNT(*) as completed_tasks,
    COUNT(*) FILTER (WHERE category = 'non_negotiable') as non_neg_completed
FROM tasks
WHERE user_id = $1 
  AND due_date = CURRENT_DATE 
  AND completed = true;

-- Query 2: Current streak
SELECT current_focus_streak, longest_focus_streak
FROM user_progress
WHERE user_id = $1;

-- Query 3: Recent journal insights
SELECT je.date, ji.insight_type, ji.title, ji.description
FROM journal_entries je
JOIN journal_insights ji ON je.entry_id = ji.entry_id
WHERE je.user_id = $1
  AND je.date >= CURRENT_DATE - INTERVAL '7 days'
ORDER BY je.date DESC
LIMIT 5;
```

**Get Past Journals with Pagination**:
```sql
SELECT 
    je.entry_id,
    je.date,
    je.summary,
    je.mood_rating,
    je.audio_url,
    dm.duration_seconds,
    dm.metric_values as waveform_data,
    COUNT(ji.insight_id) as insights_count
FROM journal_entries je
LEFT JOIN daily_metrics dm ON je.entry_id = dm.entry_id
LEFT JOIN journal_insights ji ON je.entry_id = ji.entry_id
WHERE je.user_id = $1
  AND ($2::date IS NULL OR je.date >= $2)
  AND ($3::date IS NULL OR je.date <= $3)
  AND ($4::text IS NULL OR je.mood_rating = $4)
GROUP BY je.entry_id, dm.metric_id
ORDER BY je.date DESC
LIMIT $5 OFFSET $6;
```

---

## TESTING REQUIREMENTS

### Unit Tests
- All API endpoints
- Database models and relationships
- Cache invalidation logic
- JWT token generation/validation
- Voice transcription service calls
- Gemini API integration

### Integration Tests
- Complete user flows (onboarding → planning → journaling)
- RevenueCat webhook handling
- External service fallbacks (speech-to-text, LLM)
- Cache consistency checks

### Load Tests
- 1000 concurrent users
- Voice upload stress test
- Database query performance under load
- Redis cache hit rate monitoring

---

## FASTAPI PROJECT STRUCTURE

```
dopamine-detox-api/
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI app initialization
│   ├── config.py                  # Configuration and environment variables
│   ├── dependencies.py            # Common dependencies (auth, db session)
│   │
│   ├── api/                       # API routes
│   │   ├── __init__.py
│   │   ├── v1/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py           # Authentication endpoints
│   │   │   ├── onboarding.py     # Onboarding endpoints
│   │   │   ├── home.py           # Home/Stories endpoints
│   │   │   ├── tasks.py          # Task planning endpoints
│   │   │   ├── journal.py        # Journal endpoints
│   │   │   ├── profile.py        # Profile endpoints
│   │   │   ├── subscription.py   # Subscription endpoints
│   │   │   ├── features.py       # Feature limit checking
│   │   │   └── webhooks.py       # RevenueCat webhooks
│   │
│   ├── models/                    # SQLAlchemy models
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── journal.py
│   │   ├── task.py
│   │   ├── subscription.py
│   │   └── ...
│   │
│   ├── schemas/                   # Pydantic schemas
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── journal.py
│   │   ├── task.py
│   │   ├── subscription.py
│   │   └── ...
│   │
│   ├── services/                  # Business logic
│   │   ├── __init__.py
│   │   ├── azure_storage.py      # Azure Blob Storage service
│   │   ├── speech_to_text.py     # Google Speech-to-Text service
│   │   ├── gemini_llm.py         # Gemini LLM via LangChain
│   │   ├── revenuecat.py         # RevenueCat integration
│   │   ├── cache.py              # Redis cache service
│   │   ├── auth_service.py       # Authentication logic
│   │   └── ...
│   │
│   ├── core/                      # Core functionality
│   │   ├── __init__.py
│   │   ├── security.py           # JWT, password hashing
│   │   ├── rate_limit.py         # Rate limiting
│   │   └── feature_limits.py     # Feature limit enforcement
│   │
│   ├── db/                        # Database
│   │   ├── __init__.py
│   │   ├── session.py            # Database session
│   │   └── base.py               # Base model
│   │
│   ├── middleware/                # Custom middleware
│   │   ├── __init__.py
│   │   └── cors.py               # CORS configuration
│   │
│   └── utils/                     # Utility functions
│       ├── __init__.py
│       ├── validators.py
│       └── helpers.py
│
├── alembic/                       # Database migrations
│   ├── versions/
│   ├── env.py
│   └── script.py.mako
│
├── tests/                         # Test suite
│   ├── __init__.py
│   ├── conftest.py               # Pytest configuration
│   ├── test_auth.py
│   ├── test_journal.py
│   ├── test_tasks.py
│   └── ...
│
├── scripts/                       # Utility scripts
│   ├── seed_data.py
│   └── migrate_users.py
│
├── .env.example                   # Environment variables template
├── .gitignore
├── alembic.ini                    # Alembic configuration
├── pyproject.toml                 # Python project configuration
├── requirements.txt               # Python dependencies
├── Dockerfile                     # Docker configuration
├── docker-compose.yml             # Local development
└── README.md
```

### Key Files Content

**app/main.py**:
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.v1 import (
    auth, onboarding, home, tasks, 
    journal, profile, subscription, webhooks
)
from app.db.session import init_db
from app.services.cache import init_redis, close_redis

app = FastAPI(
    title="Dopamine Detox API",
    description="Backend API for Dopamine Detox App",
    version="1.0.0",
    docs_url="/docs" if settings.ENVIRONMENT == "development" else None
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(onboarding.router, prefix="/api/v1/onboarding", tags=["onboarding"])
app.include_router(home.router, prefix="/api/v1/home", tags=["home"])
app.include_router(tasks.router, prefix="/api/v1/tasks", tags=["tasks"])
app.include_router(journal.router, prefix="/api/v1/journal", tags=["journal"])
app.include_router(profile.router, prefix="/api/v1/profile", tags=["profile"])
app.include_router(subscription.router, prefix="/api/v1/subscription", tags=["subscription"])
app.include_router(webhooks.router, prefix="/api/v1/webhooks", tags=["webhooks"])

@app.on_event("startup")
async def startup():
    await init_redis()
    await init_db()

@app.on_event("shutdown")
async def shutdown():
    await close_redis()

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
```

**requirements.txt**:
```
# FastAPI
fastapi==0.115.0
uvicorn[standard]==0.30.0
python-multipart==0.0.9

# Database
sqlalchemy==2.0.30
asyncpg==0.29.0
alembic==1.13.0

# Supabase
supabase==2.7.0

# Redis
redis[hiredis]==5.0.7

# Azure Storage
azure-storage-blob==12.19.0
azure-identity==1.16.0

# Google Cloud
google-cloud-speech==2.26.0
google-auth==2.29.0

# LangChain & Gemini
langchain==0.2.0
langchain-google-genai==1.0.5

# Authentication
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4

# RevenueCat
requests==2.31.0

# Utilities
python-dotenv==1.0.1
pydantic==2.7.0
pydantic-settings==2.2.1
```

**Dockerfile**:
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Expose port
EXPOSE 8000

# Run with uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**docker-compose.yml** (for local development):
```yaml
version: '3.8'

services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - ENVIRONMENT=development
      - REDIS_URL=redis://redis:6379
    env_file:
      - .env
    depends_on:
      - redis
    volumes:
      - .:/app
    command: uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

volumes:
  redis_data:
```

---

## DEPLOYMENT CHECKLIST

### Environment Variables
```bash
# Database - Supabase PostgreSQL
SUPABASE_URL=https://[PROJECT-REF].supabase.co
SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
SUPABASE_DATABASE_URL=postgresql://postgres:[PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres

# Redis Cache
REDIS_URL=redis://:[PASSWORD]@[HOST]:[PORT]/0
# Or for Azure Redis Cache:
# REDIS_URL=[CACHE-NAME].redis.cache.windows.net:6380,password=[KEY],ssl=True,abortConnect=False

# Azure Blob Storage
AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;AccountName=[NAME];AccountKey=[KEY];EndpointSuffix=core.windows.net
AZURE_STORAGE_ACCOUNT_NAME=[ACCOUNT_NAME]
AZURE_STORAGE_ACCOUNT_KEY=[ACCOUNT_KEY]
AZURE_STORAGE_CONTAINER=dopamine-detox-prod

# Google Cloud Speech-to-Text
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json
GOOGLE_CLOUD_PROJECT=[PROJECT_ID]

# Google Gemini LLM (via LangChain)
GOOGLE_GEMINI_API_KEY=AIzaSyXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
GEMINI_MODEL=gemini-1.5-flash  # or gemini-1.5-pro

# Authentication - Google OAuth via Supabase
GOOGLE_OAUTH_CLIENT_ID=[CLIENT_ID].apps.googleusercontent.com
GOOGLE_OAUTH_CLIENT_SECRET=[CLIENT_SECRET]

# RevenueCat
REVENUECAT_API_KEY=sk_XXXXXXXXXXXXXXXXXXXX
REVENUECAT_WEBHOOK_SECRET=whsec_XXXXXXXXXXXXXXXXXXXX
REVENUECAT_PUBLIC_KEY=public_XXXXXXXXXXXXXXXXXXXX

# App Configuration
ENVIRONMENT=production  # or development, staging
API_BASE_URL=https://api.dopaminedetox.app
FRONTEND_URL=https://dopaminedetox.app
MAX_VOICE_UPLOAD_SIZE_MB=10
ALLOWED_AUDIO_FORMATS=mp3,wav,m4a,ogg

# Security
JWT_SECRET=your-secret-key-min-32-chars
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=1440  # 24 hours
JWT_REFRESH_TOKEN_EXPIRE_DAYS=30

# Feature Flags
ENABLE_AI_INSIGHTS=true
ENABLE_VOICE_TRANSCRIPTION=true
ENABLE_GEMINI_ANALYSIS=true
```

### Pre-launch Tasks
- [ ] Database migrations applied on Supabase
- [ ] Redis cache configured
- [ ] Azure Blob Storage containers created
- [ ] Google Cloud Speech-to-Text API enabled
- [ ] Google Gemini API key obtained
- [ ] Google OAuth credentials configured in Supabase
- [ ] RevenueCat products created (Free, Monthly $8, Annual $70)
- [ ] RevenueCat webhook endpoint configured
- [ ] SSL certificates installed
- [ ] Rate limiting configured in Redis
- [ ] Backup strategy implemented (Supabase auto-backups)
- [ ] Load testing completed
- [ ] API documentation published
- [ ] Environment variables set in production
- [ ] FastAPI app deployed to Azure App Service / Cloud Run

---

This comprehensive API specification is designed to be directly used by AI coding agents for backend development, with clear structures, caching strategies, and integration guidelines.

---

## Sample JSON Structures

### Journal Entry Response
```json
{
  "entry_id": "uuid",
  "date": "2024-10-24",
  "entry_text": "Managed to replace scrolling with reading. Felt the dopamine cravings...",
  "mood_rating": "calm",
  "insights": [
    {
      "insight_type": "energetic_morning",
      "title": "Energetic Morning",
      "description": "High focus & motivation detected",
      "icon": "star"
    }
  ],
  "metrics": {
    "voice_intensity": [0.2, 0.4, 0.6, 0.8, 0.5, ...],
    "duration_seconds": 124
  },
  "created_at": "2024-10-24T08:30:00Z"
}
```

### Daily Plan Response
```json
{
  "plan_id": "uuid",
  "date": "2025-01-29",
  "transcription": "I want to focus on deep work this morning and finally finish the quarterly report...",
  "tasks": [
    {
      "task_id": "uuid",
      "title": "Deep work: Project Alpha strategy",
      "category": "non_negotiable",
      "completed": false,
      "order_index": 0
    },
    {
      "task_id": "uuid",
      "title": "Review Q1 Marketing deck",
      "category": "non_negotiable",
      "completed": false,
      "order_index": 1
    }
  ],
  "created_at": "2025-01-29T06:00:00Z"
}
```

### User Progress Response
```json
{
  "total_tasks_completed": 12,
  "total_days_active": 5,
  "current_focus_streak": 3,
  "longest_focus_streak": 7,
  "achievements": [
    {
      "type": "consistency",
      "title": "5 Day Streak",
      "unlocked_at": "2025-01-28"
    }
  ]
}
```

---

## Migration Strategy

### Phase 1: Core Features
1. User authentication
2. Basic journaling (text only)
3. Task management
4. Progress tracking

### Phase 2: Voice Features
1. Voice recording infrastructure
2. Speech-to-text integration
3. Voice journaling
4. Voice-based planning

### Phase 3: Intelligence Layer
1. AI insight generation
2. Pattern detection
3. Personalized affirmations
4. Smart notifications

### Phase 4: Advanced Features
1. Analytics dashboard
2. Trigger pattern analysis
3. Habit formation tracking
4. Social/accountability features (optional)

---

## Technology Recommendations

### Backend
- **Framework**: Python FastAPI 0.115+
- **Database**: PostgreSQL 14+ (Supabase hosted) with JSONB support
- **Cache**: Redis (Cloud provider or Azure Cache for Redis)
- **Storage**: Azure Blob Storage for voice recordings and media files
- **Voice Processing**: Google Cloud Speech-to-Text API
- **LLM**: Google Gemini via LangChain
- **Authentication**: Google OAuth 2.0

### Frontend
- **Mobile**: React Native or Flutter
- **State Management**: Redux/Zustand or Riverpod
- **Voice Recording**: expo-av (React Native) or audio_recorder (Flutter)

### Infrastructure
- **Hosting**: Azure App Service or Google Cloud Run
- **Authentication**: Google OAuth 2.0 with Supabase Auth
- **API**: RESTful with FastAPI
- **Subscription**: RevenueCat

---

## DETAILED TECHNOLOGY STACK IMPLEMENTATION

### 1. Azure Blob Storage Configuration

**Purpose**: Store voice recordings, profile pictures, and media files

**Container Structure**:
```
dopamine-detox-prod/
├── voice-recordings/
│   ├── {user_id}/
│   │   ├── journals/{journal_entry_id}.mp3
│   │   ├── plans/{plan_id}.mp3
│   │   └── onboarding/{step_name}.mp3
├── profile-pictures/
│   └── {user_id}/avatar.jpg
└── temp-uploads/
    └── {upload_id}.tmp
```

**Python SDK Setup (FastAPI)**:
```python
from azure.storage.blob import BlobServiceClient, BlobClient, ContainerClient
from azure.identity import DefaultAzureCredential
import os

# Configuration
AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
AZURE_STORAGE_ACCOUNT_NAME = os.getenv("AZURE_STORAGE_ACCOUNT_NAME")
AZURE_STORAGE_ACCOUNT_KEY = os.getenv("AZURE_STORAGE_ACCOUNT_KEY")
AZURE_STORAGE_CONTAINER = "dopamine-detox-prod"

# Initialize Blob Service Client
blob_service_client = BlobServiceClient.from_connection_string(
    AZURE_STORAGE_CONNECTION_STRING
)

async def upload_voice_recording(
    user_id: str, 
    file_content: bytes, 
    file_name: str,
    recording_type: str  # 'journal', 'plan', 'onboarding'
) -> str:
    """
    Upload voice recording to Azure Blob Storage
    Returns: Blob URL
    """
    blob_path = f"voice-recordings/{user_id}/{recording_type}/{file_name}"
    
    blob_client = blob_service_client.get_blob_client(
        container=AZURE_STORAGE_CONTAINER,
        blob=blob_path
    )
    
    # Upload with metadata
    await blob_client.upload_blob(
        file_content,
        overwrite=True,
        metadata={
            "user_id": user_id,
            "recording_type": recording_type,
            "upload_timestamp": datetime.utcnow().isoformat()
        },
        content_settings=ContentSettings(content_type="audio/mpeg")
    )
    
    # Generate SAS URL with 1 year expiry
    from azure.storage.blob import generate_blob_sas, BlobSasPermissions
    from datetime import datetime, timedelta
    
    sas_token = generate_blob_sas(
        account_name=AZURE_STORAGE_ACCOUNT_NAME,
        container_name=AZURE_STORAGE_CONTAINER,
        blob_name=blob_path,
        account_key=AZURE_STORAGE_ACCOUNT_KEY,
        permission=BlobSasPermissions(read=True),
        expiry=datetime.utcnow() + timedelta(days=365)
    )
    
    blob_url = f"https://{AZURE_STORAGE_ACCOUNT_NAME}.blob.core.windows.net/{AZURE_STORAGE_CONTAINER}/{blob_path}?{sas_token}"
    
    return blob_url

async def delete_voice_recording(blob_url: str):
    """Delete voice recording from Azure Blob Storage"""
    blob_client = BlobServiceClient.from_connection_string(
        AZURE_STORAGE_CONNECTION_STRING
    ).get_blob_client_from_url(blob_url)
    
    await blob_client.delete_blob()
```

**CORS Configuration** (for direct browser uploads):
```python
from azure.storage.blob import CorsRule

cors_rule = CorsRule(
    allowed_origins=["https://dopaminedetox.app"],
    allowed_methods=["GET", "PUT", "POST"],
    allowed_headers=["*"],
    exposed_headers=["*"],
    max_age_in_seconds=3600
)

blob_service_client.set_service_properties(cors=[cors_rule])
```

---

### 2. Google Cloud Speech-to-Text Integration

**Purpose**: Transcribe voice recordings for journals, plans, and onboarding

**Python SDK Setup (FastAPI)**:
```python
from google.cloud import speech_v1p1beta1 as speech
from google.oauth2 import service_account
import os

# Configuration
GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
credentials = service_account.Credentials.from_service_account_file(
    GOOGLE_CREDENTIALS_PATH
)

speech_client = speech.SpeechClient(credentials=credentials)

async def transcribe_audio(
    audio_url: str,
    language_code: str = "en-US"
) -> dict:
    """
    Transcribe audio file using Google Cloud Speech-to-Text
    Returns: Transcription text and confidence score
    """
    
    # Download audio from Azure Blob Storage
    import aiohttp
    async with aiohttp.ClientSession() as session:
        async with session.get(audio_url) as response:
            audio_content = await response.read()
    
    # Configure audio
    audio = speech.RecognitionAudio(content=audio_content)
    
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.MP3,
        sample_rate_hertz=16000,
        language_code=language_code,
        enable_automatic_punctuation=True,
        enable_word_time_offsets=False,
        model="default",  # or "phone_call", "video"
        use_enhanced=True,  # Use enhanced model for better accuracy
        audio_channel_count=1,
        # Enable speaker diarization for multi-speaker scenarios (optional)
        # diarization_config=speech.SpeakerDiarizationConfig(
        #     enable_speaker_diarization=True,
        #     min_speaker_count=1,
        #     max_speaker_count=1
        # )
    )
    
    # Perform transcription
    try:
        response = speech_client.recognize(config=config, audio=audio)
        
        if not response.results:
            return {
                "success": False,
                "transcription": "",
                "confidence": 0.0,
                "error": "No speech detected"
            }
        
        # Get best transcription
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
            "language": language_code
        }
        
    except Exception as e:
        return {
            "success": False,
            "transcription": "",
            "confidence": 0.0,
            "error": str(e)
        }

# For long audio files (>1 minute), use async recognition
async def transcribe_long_audio(
    audio_url: str,
    language_code: str = "en-US"
) -> dict:
    """
    Transcribe long audio files using async Speech-to-Text
    """
    from google.cloud.speech_v1p1beta1 import types
    
    audio = types.RecognitionAudio(uri=audio_url)  # Must be gs:// URL
    
    config = types.RecognitionConfig(
        encoding=types.RecognitionConfig.AudioEncoding.MP3,
        sample_rate_hertz=16000,
        language_code=language_code,
        enable_automatic_punctuation=True,
    )
    
    operation = speech_client.long_running_recognize(config=config, audio=audio)
    
    # Wait for operation to complete
    response = operation.result(timeout=300)  # 5 min timeout
    
    transcription = " ".join([
        result.alternatives[0].transcript 
        for result in response.results
    ])
    
    return {
        "success": True,
        "transcription": transcription,
        "language": language_code
    }
```

**Supported Languages** (for international expansion):
- `en-US` - English (United States)
- `en-GB` - English (United Kingdom)  
- `es-ES` - Spanish (Spain)
- `hi-IN` - Hindi (India)
- Add more as needed

**Cost Optimization**:
- Use standard model for most cases (cheaper)
- Enable enhanced model only for critical transcriptions
- Cache transcriptions to avoid re-processing

---

### 3. PostgreSQL with Supabase

**Purpose**: Main application database with built-in authentication and real-time features

**Connection Setup (FastAPI)**:
```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
import os

# Supabase PostgreSQL connection
SUPABASE_DB_URL = os.getenv("SUPABASE_DATABASE_URL")
# Format: postgresql://postgres:[YOUR-PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres

# Create async engine
engine = create_async_engine(
    SUPABASE_DB_URL.replace("postgresql://", "postgresql+asyncpg://"),
    echo=False,
    pool_size=20,
    max_overflow=40,
    pool_pre_ping=True,
    pool_recycle=3600,
)

# Session factory
async_session = sessionmaker(
    engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)

Base = declarative_base()

# Dependency for FastAPI routes
async def get_db():
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
```

**Supabase-specific Features**:

1. **Row Level Security (RLS)** - Enable for user data isolation:
```sql
-- Enable RLS on users table
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

-- Policy: Users can only read their own data
CREATE POLICY "Users can view own data" ON users
    FOR SELECT
    USING (auth.uid() = user_id);

-- Policy: Users can update their own data
CREATE POLICY "Users can update own data" ON users
    FOR UPDATE
    USING (auth.uid() = user_id);
```

2. **Realtime Subscriptions** (for live updates):
```sql
-- Enable realtime for tables
ALTER PUBLICATION supabase_realtime ADD TABLE journal_entries;
ALTER PUBLICATION supabase_realtime ADD TABLE tasks;
```

3. **Database Migrations** (using Alembic):
```bash
# Install Alembic
pip install alembic

# Initialize
alembic init alembic

# Create migration
alembic revision --autogenerate -m "Initial schema"

# Apply migration
alembic upgrade head
```

**Supabase Client Setup** (for auth integration):
```python
from supabase import create_client, Client
import os

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# Client for backend operations (uses service role key)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
```

---

### 4. Redis Cache Configuration

**Purpose**: Cache frequently accessed data, session management, rate limiting

**Connection Setup (FastAPI)**:
```python
import redis.asyncio as redis
from redis.asyncio import Redis
import os
import json

# Redis connection
REDIS_URL = os.getenv("REDIS_URL")
# Format: redis://:[PASSWORD]@[HOST]:[PORT]/0
# Or for Azure: [CACHE-NAME].redis.cache.windows.net:6380,password=[KEY],ssl=True,abortConnect=False

redis_client: Redis = None

async def init_redis():
    """Initialize Redis connection pool"""
    global redis_client
    redis_client = await redis.from_url(
        REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
        max_connections=50,
        socket_keepalive=True,
        socket_connect_timeout=5,
        retry_on_timeout=True
    )
    return redis_client

async def close_redis():
    """Close Redis connection"""
    if redis_client:
        await redis_client.close()

# Cache utilities
class CacheManager:
    """Redis cache manager with common operations"""
    
    @staticmethod
    async def get(key: str):
        """Get value from cache"""
        try:
            value = await redis_client.get(key)
            return json.loads(value) if value else None
        except Exception as e:
            print(f"Cache get error: {e}")
            return None
    
    @staticmethod
    async def set(key: str, value: any, ttl: int = 300):
        """Set value in cache with TTL (default 5 minutes)"""
        try:
            await redis_client.setex(
                key, 
                ttl, 
                json.dumps(value, default=str)
            )
            return True
        except Exception as e:
            print(f"Cache set error: {e}")
            return False
    
    @staticmethod
    async def delete(key: str):
        """Delete key from cache"""
        try:
            await redis_client.delete(key)
            return True
        except Exception as e:
            print(f"Cache delete error: {e}")
            return False
    
    @staticmethod
    async def delete_pattern(pattern: str):
        """Delete all keys matching pattern"""
        try:
            keys = await redis_client.keys(pattern)
            if keys:
                await redis_client.delete(*keys)
            return True
        except Exception as e:
            print(f"Cache delete pattern error: {e}")
            return False
    
    @staticmethod
    async def exists(key: str) -> bool:
        """Check if key exists"""
        return await redis_client.exists(key) > 0

# FastAPI startup/shutdown events
from fastapi import FastAPI

app = FastAPI()

@app.on_event("startup")
async def startup_event():
    await init_redis()

@app.on_event("shutdown")
async def shutdown_event():
    await close_redis()
```

**Rate Limiting with Redis**:
```python
from datetime import datetime, timedelta

async def check_rate_limit(
    user_id: str, 
    action: str, 
    max_requests: int, 
    window_seconds: int
) -> bool:
    """
    Check if user has exceeded rate limit
    Returns: True if allowed, False if rate limited
    """
    key = f"ratelimit:{action}:{user_id}"
    current_count = await redis_client.get(key)
    
    if current_count is None:
        # First request in window
        await redis_client.setex(key, window_seconds, 1)
        return True
    
    if int(current_count) >= max_requests:
        return False
    
    await redis_client.incr(key)
    return True

# Usage in FastAPI route
from fastapi import HTTPException

@app.post("/api/v1/journal/entry")
async def create_journal_entry(user_id: str = Depends(get_current_user)):
    # Check rate limit: max 10 journals per minute
    if not await check_rate_limit(user_id, "journal_create", 10, 60):
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Please try again later."
        )
    
    # Process journal creation...
```

---

### 5. Google OAuth Authentication via Supabase

**Purpose**: Social authentication with Google accounts

**Supabase Auth Setup**:

1. **Enable Google Provider** in Supabase Dashboard:
   - Go to Authentication → Providers → Google
   - Add Google OAuth Client ID and Secret
   - Set redirect URL: `https://[PROJECT-REF].supabase.co/auth/v1/callback`

2. **FastAPI Integration**:
```python
from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from supabase import create_client, Client
import os

app = FastAPI()
security = HTTPBearer()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

# Verify JWT token
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Verify Supabase JWT token and return user
    """
    try:
        token = credentials.credentials
        
        # Verify token with Supabase
        user = supabase.auth.get_user(token)
        
        if not user:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        return user.user
        
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))

# OAuth callback endpoint (optional - Supabase handles this)
@app.get("/auth/google")
async def google_auth():
    """
    Redirect to Google OAuth
    """
    # Supabase SDK handles this on client side
    # Client calls: supabase.auth.signInWithOAuth({ provider: 'google' })
    pass

@app.post("/auth/callback")
async def auth_callback(session_data: dict):
    """
    Handle OAuth callback from Supabase
    """
    # Extract user data
    user_id = session_data["user"]["id"]
    email = session_data["user"]["email"]
    full_name = session_data["user"]["user_metadata"].get("full_name", "")
    
    # Check if user exists in our database
    existing_user = await db.get_user_by_email(email)
    
    if not existing_user:
        # Create new user record
        new_user = await db.create_user({
            "user_id": user_id,  # Use Supabase user ID
            "email": email,
            "full_name": full_name,
            "created_at": datetime.utcnow()
        })
        
        # Create free tier subscription
        await db.create_subscription({
            "user_id": user_id,
            "tier": "free",
            "status": "active",
            "started_at": datetime.utcnow()
        })
    
    return {
        "success": True,
        "user": existing_user or new_user,
        "access_token": session_data["access_token"],
        "refresh_token": session_data["refresh_token"]
    }
```

3. **Client-side Integration** (React Native example):
```javascript
// Initialize Supabase client
import { createClient } from '@supabase/supabase-js'

const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY)

// Google Sign-In
async function signInWithGoogle() {
  const { data, error } = await supabase.auth.signInWithOAuth({
    provider: 'google',
    options: {
      redirectTo: 'dopaminedetox://auth/callback',
      queryParams: {
        access_type: 'offline',
        prompt: 'consent',
      }
    }
  })
  
  if (error) console.error('Error:', error.message)
}

// Get session
const { data: { session } } = await supabase.auth.getSession()

// Use session token for API calls
const response = await fetch('https://api.dopaminedetox.app/api/v1/profile', {
  headers: {
    'Authorization': `Bearer ${session.access_token}`
  }
})
```

---

### 6. Google Gemini via LangChain

**Purpose**: LLM for task extraction, journal analysis, and insight generation

**Python SDK Setup (FastAPI)**:
```python
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.prompts import ChatPromptTemplate
from langchain.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field
from typing import List
import os

# Configuration
GOOGLE_API_KEY = os.getenv("GOOGLE_GEMINI_API_KEY")

# Initialize Gemini model
llm = ChatGoogleGenerativeAI(
    model="gemini-1.5-flash",  # or "gemini-1.5-pro" for better quality
    google_api_key=GOOGLE_API_KEY,
    temperature=0.7,
    max_tokens=2048,
    timeout=30,
    max_retries=2,
)

# Define output schemas
class ExtractedTask(BaseModel):
    """Schema for extracted task"""
    title: str = Field(description="Task title")
    category: str = Field(description="Task category: non_negotiable, important, or optional")
    confidence: float = Field(description="Confidence score 0-1")

class TaskExtractionOutput(BaseModel):
    """Schema for task extraction response"""
    tasks: List[ExtractedTask] = Field(description="List of extracted tasks")

class JournalAnalysis(BaseModel):
    """Schema for journal analysis"""
    primary_emotion: str = Field(description="Primary emotion detected")
    secondary_emotions: List[str] = Field(description="Secondary emotions")
    mood_rating: str = Field(description="Overall mood: great, good, calm, stressed, overwhelmed")
    sentiment_score: float = Field(description="Sentiment score from -1 to 1")
    behavioral_patterns: List[str] = Field(description="Detected behavioral patterns")
    insights: List[dict] = Field(description="Generated insights")
    summary: str = Field(description="2-3 sentence summary")

# Task Extraction Chain
async def extract_tasks_from_transcription(transcription: str) -> List[dict]:
    """
    Extract tasks from voice transcription using Gemini
    """
    parser = PydanticOutputParser(pydantic_object=TaskExtractionOutput)
    
    prompt = ChatPromptTemplate.from_template(
        """You are an AI assistant helping users plan their day by extracting tasks from voice transcriptions.

Transcription: {transcription}

Extract all tasks mentioned and categorize them:
- non_negotiable: Must-do tasks, high priority, deadlines
- important: Should-do tasks, significant but flexible
- optional: Nice-to-do tasks, low priority

Also assign a confidence score (0-1) based on how clearly the task was stated.

{format_instructions}

Output only valid JSON, no additional text."""
    )
    
    chain = prompt | llm | parser
    
    try:
        result = await chain.ainvoke({
            "transcription": transcription,
            "format_instructions": parser.get_format_instructions()
        })
        
        return [task.dict() for task in result.tasks]
        
    except Exception as e:
        print(f"Task extraction error: {e}")
        return []

# Journal Analysis Chain
async def analyze_journal_entry(transcription: str) -> dict:
    """
    Analyze journal entry using Gemini
    """
    parser = PydanticOutputParser(pydantic_object=JournalAnalysis)
    
    prompt = ChatPromptTemplate.from_template(
        """You are an empathetic AI coach analyzing a dopamine detox journal entry.

Journal Entry: {transcription}

Analyze the entry and provide:
1. Primary emotion (overwhelmed, stressed, calm, happy, anxious, etc.)
2. Secondary emotions (list up to 3)
3. Overall mood rating (great, good, calm, stressed, overwhelmed)
4. Sentiment score from -1 (very negative) to 1 (very positive)
5. Behavioral patterns (triggers mentioned, coping strategies, progress)
6. 2-3 supportive insights (max 30 words each) that:
   - Acknowledge their experience
   - Highlight positive behaviors
   - Encourage continued growth
7. A brief 2-3 sentence summary

Be supportive, non-judgmental, and focus on growth.

{format_instructions}

Output only valid JSON, no additional text."""
    )
    
    chain = prompt | llm | parser
    
    try:
        result = await chain.ainvoke({
            "transcription": transcription,
            "format_instructions": parser.get_format_instructions()
        })
        
        return result.dict()
        
    except Exception as e:
        print(f"Journal analysis error: {e}")
        return None

# Generate Personalized Affirmation
async def generate_affirmation(user_context: dict) -> str:
    """
    Generate personalized affirmation based on user's progress
    """
    prompt = ChatPromptTemplate.from_template(
        """Generate a supportive, personalized affirmation for a user on their dopamine detox journey.

User Context:
- Current streak: {current_streak} days
- Recent mood: {recent_mood}
- Recent challenge: {recent_challenge}

Create a short, encouraging affirmation (1-2 sentences) that:
- Acknowledges their progress
- Reinforces their capability
- Motivates continued effort

Make it personal and specific to their situation. Do not use generic phrases.
Output only the affirmation text, nothing else."""
    )
    
    chain = prompt | llm
    
    try:
        result = await chain.ainvoke(user_context)
        return result.content.strip()
    except Exception as e:
        print(f"Affirmation generation error: {e}")
        return "You're doing great. Keep going!"

# Streaming Response (for real-time analysis)
async def stream_journal_analysis(transcription: str):
    """
    Stream journal analysis for real-time feedback
    """
    prompt = f"""Analyze this journal entry and provide supportive insights:

{transcription}

Provide:
1. Primary emotion
2. Key insights
3. Supportive message"""
    
    async for chunk in llm.astream(prompt):
        yield chunk.content
```

**Cost Optimization**:
- Use `gemini-1.5-flash` for most operations (cheaper, faster)
- Use `gemini-1.5-pro` only for complex analysis
- Cache common prompts
- Implement retry logic with exponential backoff

**LangChain Features Used**:
- `ChatPromptTemplate` - Structured prompts
- `PydanticOutputParser` - Type-safe outputs
- `astream` - Streaming responses
- Chain composition for complex workflows

---

## Notes for AI Coding Tools

1. **Schema Generation**: This model is designed to be directly translatable to SQL DDL statements or ORM models (e.g., Prisma, SQLAlchemy, TypeORM)

2. **Naming Conventions**: 
   - Tables: snake_case plural (e.g., `journal_entries`)
   - Columns: snake_case (e.g., `user_id`)
   - Primary Keys: `{entity}_id`

3. **Timestamps**: All tables should have `created_at` (automatic) and `updated_at` (automatic) unless specified otherwise

4. **Foreign Key Constraints**: Use CASCADE on delete for dependent data (insights, metrics) and SET NULL or RESTRICT for optional relationships

5. **JSON Fields**: Use JSONB in PostgreSQL for better performance and indexing capabilities

6. **UUID vs Integer IDs**: UUIDs recommended for distributed systems and security (no sequential ID enumeration)

---

## Validation Rules

### User
- Email: Valid email format, unique
- Password: Min 8 characters, at least 1 uppercase, 1 lowercase, 1 number

### JournalEntry
- Date: Cannot be future date
- Entry text OR voice recording required (at least one)

### Task
- Title: Max 200 characters
- Category: Required, must be valid enum value

### DailyPlan
- Date: Cannot be more than 1 week in past or 1 week in future

---

This data model provides a comprehensive foundation for building the dopamine detox app with all features visible in the UI screens. It's structured to support scalability, performance, and future feature additions.