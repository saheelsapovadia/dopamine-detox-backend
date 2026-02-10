# API Plan — Today's Tasks

> **Date:** 8 Feb 2026 (updated — added edit/batch-update APIs)
> **Screens:** `src/screens/home/HomeScreen.tsx`, `src/screens/planning/PlanMyDayScreen.tsx`
> **Base URL:** `https://api.savvyapp.com`
> **Auth:** Bearer token (via `apiClient.ts`)

---

## 1. HomeScreen Data Requirements

The HomeScreen has two visual states driven by whether the user has planned tasks for today:

| State | What it shows |
|---|---|
| **No tasks planned** (`hasPlannedTasks = false`) | "What's your one big goal for today?" prompt + "Plan My Day" CTA |
| **Tasks planned** (`hasPlannedTasks = true`) | Priority card (category, title, duration) + horizontal "Later" task list |

### Data needed from backend

| Field | Type | Example | Used for |
|---|---|---|---|
| `hasTasks` | `boolean` | `true` | Toggle between the two states |
| Priority task category | `string` | `"WORK"` | Category chip on card |
| Priority task title | `string` | `"Write Chapter 3"` | Large title text |
| Priority task duration | `number` | `45` | Session button duration |
| Priority task duration unit | `string` | `"MINS"` | Session button unit label |
| Later tasks | `array` | `[{id, title, subtitle, iconType}]` | Horizontal scroll cards |
| Day completion history | `array` | `[{date, isCompleted}]` | Day selector pills |

---

## 2. Data Models / Types

### Task

```typescript
interface Task {
  id: string;                          // UUID
  userId: string;                      // Owner user ID
  title: string;                       // e.g. "Write Chapter 3"
  subtitle?: string;                   // e.g. "Self Improvement"
  category: TaskCategory;              // e.g. "WORK"
  priority: 'high' | 'medium' | 'low'; // Determines priority card vs later list
  durationMins: number;                // e.g. 45
  iconType?: TaskIconType;             // Icon hint for the client
  status: TaskStatus;
  date: string;                        // ISO date "2026-02-07"
  createdAt: string;                   // ISO datetime
  updatedAt: string;                   // ISO datetime
}
```

### Enums

```typescript
type TaskCategory = 'WORK' | 'PERSONAL' | 'HEALTH' | 'LEARNING' | 'OTHER';

type TaskStatus = 'pending' | 'in_progress' | 'completed' | 'skipped';

type TaskIconType = 'pages' | 'plant' | 'journal' | 'exercise' | 'code' | 'default';
```

### Day Summary (for the day selector)

```typescript
interface DaySummary {
  date: string;        // ISO date "2026-02-07"
  label: string;       // "Today" | "Mon" | "Sun" etc.
  isToday: boolean;
  isCompleted: boolean; // All tasks for that day completed
  totalTasks: number;
  completedTasks: number;
}
```

---

## 3. API Endpoints

---

### 3.1 GET — Fetch Today's Tasks

Fetches all tasks the user has planned for a given date (defaults to today).

```
GET /api/v1/users/{userId}/tasks/daily?date=2026-02-07
```

#### Path Parameters

| Param | Type | Required | Description |
|---|---|---|---|
| `userId` | `string` | Yes | The authenticated user's ID |

#### Query Parameters

| Param | Type | Required | Default | Description |
|---|---|---|---|---|
| `date` | `string` (ISO date) | No | today's date | The date to fetch tasks for (`YYYY-MM-DD`) |

#### Request Headers

```
Authorization: Bearer <token>
Content-Type: application/json
```

#### Request Example

```
GET /api/v1/users/dev-user-001/tasks/daily?date=2026-02-07
Authorization: Bearer dev-mock-token-savvy-2026
```

#### Response — 200 OK (tasks exist)

```json
{
  "success": true,
  "data": {
    "date": "2026-02-07",
    "hasTasks": true,
    "priorityTask": {
      "id": "task-uuid-001",
      "userId": "dev-user-001",
      "title": "Write Chapter 3",
      "subtitle": null,
      "category": "WORK",
      "priority": "high",
      "durationMins": 45,
      "iconType": "pages",
      "status": "pending",
      "date": "2026-02-07",
      "createdAt": "2026-02-07T06:30:00.000Z",
      "updatedAt": "2026-02-07T06:30:00.000Z"
    },
    "laterTasks": [
      {
        "id": "task-uuid-002",
        "userId": "dev-user-001",
        "title": "Read 10 pages",
        "subtitle": "Self Improvement",
        "category": "LEARNING",
        "priority": "medium",
        "durationMins": 20,
        "iconType": "pages",
        "status": "pending",
        "date": "2026-02-07",
        "createdAt": "2026-02-07T06:30:00.000Z",
        "updatedAt": "2026-02-07T06:30:00.000Z"
      },
      {
        "id": "task-uuid-003",
        "userId": "dev-user-001",
        "title": "Water plants",
        "subtitle": "Living Room",
        "category": "PERSONAL",
        "priority": "low",
        "durationMins": 5,
        "iconType": "plant",
        "status": "pending",
        "date": "2026-02-07",
        "createdAt": "2026-02-07T06:30:00.000Z",
        "updatedAt": "2026-02-07T06:30:00.000Z"
      },
      {
        "id": "task-uuid-004",
        "userId": "dev-user-001",
        "title": "Journaling",
        "subtitle": "Reflection",
        "category": "PERSONAL",
        "priority": "low",
        "durationMins": 15,
        "iconType": "journal",
        "status": "pending",
        "date": "2026-02-07",
        "createdAt": "2026-02-07T06:30:00.000Z",
        "updatedAt": "2026-02-07T06:30:00.000Z"
      }
    ],
    "daySummaries": [
      { "date": "2026-02-07", "label": "Today", "isToday": true, "isCompleted": false, "totalTasks": 4, "completedTasks": 0 },
      { "date": "2026-02-06", "label": "Thu",   "isToday": false, "isCompleted": true, "totalTasks": 3, "completedTasks": 3 },
      { "date": "2026-02-05", "label": "Wed",   "isToday": false, "isCompleted": true, "totalTasks": 2, "completedTasks": 2 }
    ]
  }
}
```

#### Response — 200 OK (no tasks planned)

```json
{
  "success": true,
  "data": {
    "date": "2026-02-07",
    "hasTasks": false,
    "priorityTask": null,
    "laterTasks": [],
    "daySummaries": [
      { "date": "2026-02-07", "label": "Today", "isToday": true, "isCompleted": false, "totalTasks": 0, "completedTasks": 0 },
      { "date": "2026-02-06", "label": "Thu",   "isToday": false, "isCompleted": true, "totalTasks": 3, "completedTasks": 3 },
      { "date": "2026-02-05", "label": "Wed",   "isToday": false, "isCompleted": true, "totalTasks": 2, "completedTasks": 2 }
    ]
  }
}
```

#### Error Responses

| Status | Condition | Body |
|---|---|---|
| `401` | Missing or invalid token | `{ "success": false, "error": { "code": "UNAUTHORIZED", "message": "Invalid or expired token" } }` |
| `403` | User ID mismatch | `{ "success": false, "error": { "code": "FORBIDDEN", "message": "Cannot access another user's tasks" } }` |
| `404` | User not found | `{ "success": false, "error": { "code": "USER_NOT_FOUND", "message": "User not found" } }` |

---

### 3.2 POST — Create Today's Task

Creates a new task for the given date (defaults to today). Used when the user plans their day via the "Plan My Day" flow or adds a task manually.

```
POST /api/v1/users/{userId}/tasks
```

#### Path Parameters

| Param | Type | Required | Description |
|---|---|---|---|
| `userId` | `string` | Yes | The authenticated user's ID |

#### Request Headers

```
Authorization: Bearer <token>
Content-Type: application/json
```

#### Request Body

```json
{
  "title": "Write Chapter 3",
  "subtitle": null,
  "category": "WORK",
  "priority": "high",
  "durationMins": 45,
  "iconType": "pages",
  "date": "2026-02-07"
}
```

#### Request Body Schema

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `title` | `string` | Yes | — | Task title (max 200 chars) |
| `subtitle` | `string \| null` | No | `null` | Optional subtitle / context |
| `category` | `TaskCategory` | Yes | — | One of: `WORK`, `PERSONAL`, `HEALTH`, `LEARNING`, `OTHER` |
| `priority` | `string` | Yes | — | `"high"` = priority card, `"medium"` / `"low"` = later list |
| `durationMins` | `number` | Yes | — | Estimated session duration in minutes (min: 1, max: 480) |
| `iconType` | `TaskIconType` | No | `"default"` | Client icon hint |
| `date` | `string` | No | today | ISO date for the task (`YYYY-MM-DD`) |

#### Response — 201 Created

```json
{
  "success": true,
  "data": {
    "id": "task-uuid-005",
    "userId": "dev-user-001",
    "title": "Write Chapter 3",
    "subtitle": null,
    "category": "WORK",
    "priority": "high",
    "durationMins": 45,
    "iconType": "pages",
    "status": "pending",
    "date": "2026-02-07",
    "createdAt": "2026-02-07T06:30:00.000Z",
    "updatedAt": "2026-02-07T06:30:00.000Z"
  }
}
```

#### Error Responses

| Status | Condition | Body |
|---|---|---|
| `400` | Validation error (missing title, invalid category, etc.) | `{ "success": false, "error": { "code": "VALIDATION_ERROR", "message": "title is required", "details": [...] } }` |
| `401` | Missing or invalid token | `{ "success": false, "error": { "code": "UNAUTHORIZED", "message": "Invalid or expired token" } }` |
| `403` | User ID mismatch | `{ "success": false, "error": { "code": "FORBIDDEN", "message": "Cannot create tasks for another user" } }` |
| `409` | Duplicate high-priority task for the same date | `{ "success": false, "error": { "code": "CONFLICT", "message": "A high-priority task already exists for this date" } }` |

---

### 3.3 POST — Batch Create Tasks (Plan My Day)

The "Plan My Day" flow lets users set multiple tasks at once. This endpoint creates them in a single request.

```
POST /api/v1/users/{userId}/tasks/batch
```

#### Path Parameters

| Param | Type | Required | Description |
|---|---|---|---|
| `userId` | `string` | Yes | The authenticated user's ID |

#### Request Headers

```
Authorization: Bearer <token>
Content-Type: application/json
```

#### Request Body

```json
{
  "date": "2026-02-07",
  "tasks": [
    {
      "title": "Write Chapter 3",
      "category": "WORK",
      "priority": "high",
      "durationMins": 45,
      "iconType": "pages"
    },
    {
      "title": "Read 10 pages",
      "subtitle": "Self Improvement",
      "category": "LEARNING",
      "priority": "medium",
      "durationMins": 20,
      "iconType": "pages"
    },
    {
      "title": "Water plants",
      "subtitle": "Living Room",
      "category": "PERSONAL",
      "priority": "low",
      "durationMins": 5,
      "iconType": "plant"
    }
  ]
}
```

#### Request Body Schema

| Field | Type | Required | Description |
|---|---|---|---|
| `date` | `string` | Yes | ISO date for all tasks (`YYYY-MM-DD`) |
| `tasks` | `CreateTaskRequest[]` | Yes | Array of tasks to create (min 1, max 20) |

Each item in `tasks` follows the same schema as section 3.2 Request Body, **except** `date` is omitted (inherited from the top-level `date` field).

#### Response — 201 Created

```json
{
  "success": true,
  "data": {
    "date": "2026-02-07",
    "created": 3,
    "tasks": [
      { "id": "task-uuid-010", "title": "Write Chapter 3", "priority": "high", "status": "pending" },
      { "id": "task-uuid-011", "title": "Read 10 pages", "priority": "medium", "status": "pending" },
      { "id": "task-uuid-012", "title": "Water plants", "priority": "low", "status": "pending" }
    ]
  }
}
```

#### Error Responses

| Status | Condition | Body |
|---|---|---|
| `400` | Empty tasks array or validation error | `{ "success": false, "error": { "code": "VALIDATION_ERROR", "message": "tasks array must contain at least one item" } }` |
| `401` | Missing or invalid token | `{ "success": false, "error": { "code": "UNAUTHORIZED", "message": "Invalid or expired token" } }` |
| `403` | User ID mismatch | `{ "success": false, "error": { "code": "FORBIDDEN", "message": "Cannot create tasks for another user" } }` |
| `409` | Multiple high-priority tasks in batch | `{ "success": false, "error": { "code": "CONFLICT", "message": "Only one task can have high priority per date" } }` |

---

### 3.4 PUT — Batch Update Tasks (Edit Tasks)

When the user taps **Edit** on the HomeScreen priority card, the app opens the `PlanMyDay` screen in **edit mode** with all current tasks pre-populated. After changing titles, priorities, or durations, the client calls this endpoint to persist all changes in a single request.

```
PUT /api/v1/users/{userId}/tasks/batch
```

#### Path Parameters

| Param | Type | Required | Description |
|---|---|---|---|
| `userId` | `string` | Yes | The authenticated user's ID |

#### Request Headers

```
Authorization: Bearer <token>
Content-Type: application/json
```

#### Request Body

```json
{
  "date": "2026-02-07",
  "tasks": [
    {
      "id": "task-uuid-001",
      "title": "Write Chapter 3",
      "priority": "high",
      "durationMins": 60
    },
    {
      "id": "task-uuid-002",
      "title": "Read 10 pages",
      "priority": "low"
    },
    {
      "id": "task-uuid-003",
      "title": "Water plants",
      "priority": "low",
      "durationMins": 5
    }
  ]
}
```

#### Request Body Schema

| Field | Type | Required | Description |
|---|---|---|---|
| `date` | `string` | Yes | ISO date of the tasks being updated (`YYYY-MM-DD`) |
| `tasks` | `UpdateTaskRequest[]` | Yes | Array of task updates (min 1, max 20) |

#### UpdateTaskRequest

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | `string` | **Yes** | Existing task ID (UUID) to update |
| `title` | `string` | No | Updated task title (max 200 chars) |
| `subtitle` | `string \| null` | No | Updated subtitle |
| `category` | `TaskCategory` | No | Updated category |
| `priority` | `string` | No | `"high"`, `"medium"`, or `"low"` — changing this re-ranks the task |
| `durationMins` | `number` | No | Updated session duration in minutes (min: 1, max: 480) |
| `iconType` | `TaskIconType` | No | Updated client icon hint |

> **Merge semantics** — only fields present in each task object are updated; omitted fields keep their current values. Tasks not included in the array are left unchanged.

#### Response — 200 OK

```json
{
  "success": true,
  "data": {
    "date": "2026-02-07",
    "updated": 3,
    "tasks": [
      {
        "id": "task-uuid-001",
        "title": "Write Chapter 3",
        "priority": "high",
        "status": "pending",
        "updatedAt": "2026-02-07T10:15:00.000Z"
      },
      {
        "id": "task-uuid-002",
        "title": "Read 10 pages",
        "priority": "low",
        "status": "pending",
        "updatedAt": "2026-02-07T10:15:00.000Z"
      },
      {
        "id": "task-uuid-003",
        "title": "Water plants",
        "priority": "low",
        "status": "pending",
        "updatedAt": "2026-02-07T10:15:00.000Z"
      }
    ]
  }
}
```

#### Error Responses

| Status | Condition | Body |
|---|---|---|
| `400` | Empty tasks array | `{ "success": false, "error": { "code": "VALIDATION_ERROR", "message": "tasks array must contain at least one item" } }` |
| `400` | Task ID not found for the given date | `{ "success": false, "error": { "code": "VALIDATION_ERROR", "message": "Task task-uuid-999 not found for date 2026-02-07" } }` |
| `400` | Invalid field value (e.g. `durationMins: -1`) | `{ "success": false, "error": { "code": "VALIDATION_ERROR", "message": "durationMins must be between 1 and 480", "details": [...] } }` |
| `401` | Missing or invalid token | `{ "success": false, "error": { "code": "UNAUTHORIZED", "message": "Invalid or expired token" } }` |
| `403` | User ID mismatch | `{ "success": false, "error": { "code": "FORBIDDEN", "message": "Cannot update another user's tasks" } }` |
| `409` | Multiple tasks set to high priority | `{ "success": false, "error": { "code": "CONFLICT", "message": "Only one task can have high priority per date" } }` |

#### Behavior Notes

- **Idempotent** — calling with the same payload twice produces the same result.
- **Partial update** — only fields present in each task object are written; omitted fields retain their current values.
- **Priority re-ranking** — if `priority` is changed to `"high"` for a task, the server automatically demotes any existing high-priority task to `"medium"` for the same date.
- **Untouched tasks** — tasks for the same date that are not included in the `tasks` array are left unchanged.

---

### 3.5 PATCH — Update Single Task Status

Updates a single task field (primarily `status`). Used for "Begin Session" (→ `in_progress`), completion, and skipping.

```
PATCH /api/v1/users/{userId}/tasks/{taskId}
```

#### Path Parameters

| Param | Type | Required | Description |
|---|---|---|---|
| `userId` | `string` | Yes | The authenticated user's ID |
| `taskId` | `string` | Yes | The task to update |

#### Request Headers

```
Authorization: Bearer <token>
Content-Type: application/json
```

#### Request Body

```json
{
  "status": "in_progress"
}
```

#### Request Body Schema

| Field | Type | Required | Description |
|---|---|---|---|
| `status` | `TaskStatus` | Yes | New status: `"pending"`, `"in_progress"`, `"completed"`, `"skipped"` |

#### Response — 200 OK

Returns the full updated `Task` object (same shape as section 2 Task model).

#### Error Responses

| Status | Condition | Body |
|---|---|---|
| `400` | Invalid status value | `{ "success": false, "error": { "code": "VALIDATION_ERROR", "message": "Invalid status value" } }` |
| `401` | Missing or invalid token | `{ "success": false, "error": { "code": "UNAUTHORIZED", "message": "Invalid or expired token" } }` |
| `403` | User ID mismatch | `{ "success": false, "error": { "code": "FORBIDDEN", "message": "Cannot update another user's tasks" } }` |
| `404` | Task not found | `{ "success": false, "error": { "code": "NOT_FOUND", "message": "Task not found" } }` |

---

### 3.6 DELETE — Delete a Task

Permanently deletes a task.

```
DELETE /api/v1/users/{userId}/tasks/{taskId}
```

#### Path Parameters

| Param | Type | Required | Description |
|---|---|---|---|
| `userId` | `string` | Yes | The authenticated user's ID |
| `taskId` | `string` | Yes | The task to delete |

#### Request Headers

```
Authorization: Bearer <token>
```

#### Response — 204 No Content

Empty body on success.

#### Error Responses

| Status | Condition | Body |
|---|---|---|
| `401` | Missing or invalid token | `{ "success": false, "error": { "code": "UNAUTHORIZED", "message": "Invalid or expired token" } }` |
| `403` | User ID mismatch | `{ "success": false, "error": { "code": "FORBIDDEN", "message": "Cannot delete another user's tasks" } }` |
| `404` | Task not found | `{ "success": false, "error": { "code": "NOT_FOUND", "message": "Task not found" } }` |

---

## 4. Data Models / Request Types (TypeScript)

All types live in `src/types/task.ts`.

```typescript
// Task categories
export type TaskCategory = 'WORK' | 'PERSONAL' | 'HEALTH' | 'LEARNING' | 'OTHER';

// Task status
export type TaskStatus = 'pending' | 'in_progress' | 'completed' | 'skipped';

// Icon types available on the client
export type TaskIconType = 'pages' | 'plant' | 'journal' | 'exercise' | 'code' | 'default';

// Core task model
export interface Task {
  id: string;
  userId: string;
  title: string;
  subtitle?: string | null;
  category: TaskCategory;
  priority: 'high' | 'medium' | 'low';
  durationMins: number;
  iconType: TaskIconType;
  status: TaskStatus;
  date: string;       // "YYYY-MM-DD"
  createdAt: string;  // ISO 8601
  updatedAt: string;  // ISO 8601
}

// Day summary for day selector
export interface DaySummary {
  date: string;
  label: string;
  isToday: boolean;
  isCompleted: boolean;
  totalTasks: number;
  completedTasks: number;
}

// GET daily tasks response
export interface DailyTasksResponse {
  date: string;
  hasTasks: boolean;
  priorityTask: Task | null;
  laterTasks: Task[];
  daySummaries: DaySummary[];
}

// POST create task request body
export interface CreateTaskRequest {
  title: string;
  subtitle?: string | null;
  category: TaskCategory;
  priority: 'high' | 'medium' | 'low';
  durationMins: number;
  iconType?: TaskIconType;
  date?: string;
}

// PUT update task request body (edit mode — partial, id required)
export interface UpdateTaskRequest {
  id: string;
  title?: string;
  subtitle?: string | null;
  category?: TaskCategory;
  priority?: 'high' | 'medium' | 'low';
  durationMins?: number;
  iconType?: TaskIconType;
}

// POST /tasks/batch response
export interface BatchCreateTasksResponse {
  date: string;
  created: number;
  tasks: Pick<Task, 'id' | 'title' | 'priority' | 'status'>[];
}

// PUT /tasks/batch response
export interface BatchUpdateTasksResponse {
  date: string;
  updated: number;
  tasks: (Pick<Task, 'id' | 'title' | 'priority' | 'status'> & { updatedAt: string })[];
}
```

---

## 5. Client Integration Plan

### Service Functions (`src/services/taskService.ts`)

```typescript
import { apiClient } from './apiClient';
import type {
  Task, TaskStatus, DailyTasksResponse,
  CreateTaskRequest, BatchCreateTasksResponse,
  UpdateTaskRequest, BatchUpdateTasksResponse,
} from '../types/task';

export const taskService = {
  /** GET  /tasks/daily */
  fetchDaily: (userId: string, date?: string) => {
    const query = date ? `?date=${date}` : '';
    return apiClient.get<DailyTasksResponse>(`/api/v1/users/${userId}/tasks/daily${query}`);
  },

  /** POST /tasks */
  create: (userId: string, task: CreateTaskRequest) =>
    apiClient.post<Task>(`/api/v1/users/${userId}/tasks`, task as Record<string, unknown>),

  /** POST /tasks/batch */
  batchCreate: (userId: string, date: string, tasks: CreateTaskRequest[]) =>
    apiClient.post<BatchCreateTasksResponse>(
      `/api/v1/users/${userId}/tasks/batch`,
      { date, tasks } as Record<string, unknown>,
    ),

  /** PUT  /tasks/batch (edit mode) */
  batchUpdate: (userId: string, date: string, tasks: UpdateTaskRequest[]) =>
    apiClient.put<BatchUpdateTasksResponse>(
      `/api/v1/users/${userId}/tasks/batch`,
      { date, tasks } as Record<string, unknown>,
    ),

  /** PATCH /tasks/{taskId} */
  updateStatus: (userId: string, taskId: string, status: TaskStatus) =>
    apiClient.patch<Task>(`/api/v1/users/${userId}/tasks/${taskId}`, { status }),

  /** DELETE /tasks/{taskId} */
  remove: (userId: string, taskId: string) =>
    apiClient.delete<void>(`/api/v1/users/${userId}/tasks/${taskId}`),
};
```

### Screen Integration

| Screen | Action | Endpoint |
|---|---|---|
| **HomeScreen** — no tasks planned | Tap "Plan My Day" → PlanMyDay screen | — (navigation only) |
| **PlanMyDay** — create mode | Lock & Start Day | `POST /tasks/batch` (3.3) |
| **HomeScreen** — tasks exist | Tap "Edit" on priority card → PlanMyDay in edit mode | — (navigation only) |
| **PlanMyDay** — edit mode | Save Changes | `PUT /tasks/batch` (3.4) |
| **HomeScreen** — priority card | Tap "Begin Session" | `PATCH /tasks/{taskId}` (3.5) |

### Navigation Params

```typescript
// PlanMyDay accepts optional edit-mode params
PlanMyDay: { editMode?: boolean; date?: string } | undefined;
```

When `editMode` is `true`, the PlanMyDay screen reads existing tasks from `TaskContext.dailyTasks` and pre-populates the non-negotiable input (high-priority task) and the low-priority task list. On submit it calls `batchUpdateTasks()` instead of `batchCreateTasks()`.

---

## 6. Summary

| # | Endpoint | Method | Purpose |
|---|---|---|---|
| 1 | `/api/v1/users/{userId}/tasks/daily?date=` | `GET` | Fetch today's tasks (priority + later) + day summaries |
| 2 | `/api/v1/users/{userId}/tasks` | `POST` | Create a single task |
| 3 | `/api/v1/users/{userId}/tasks/batch` | `POST` | Bulk create tasks from "Plan My Day" flow |
| 4 | `/api/v1/users/{userId}/tasks/batch` | `PUT` | Bulk update tasks from "Edit Tasks" flow |
| 5 | `/api/v1/users/{userId}/tasks/{taskId}` | `PATCH` | Update a single task's status |
| 6 | `/api/v1/users/{userId}/tasks/{taskId}` | `DELETE` | Delete a task |
