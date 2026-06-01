# API Reference (Frontend)

Base URL: your server origin (e.g. `http://localhost:8000`)

API prefix: **`/api/v1`**

Interactive docs (when `DEBUG=true`): `/docs` (Swagger), `/redoc` (ReDoc)

---

## Authentication

Protected routes require:

```http
Authorization: Bearer <access_token>
```

### Register (public)

```http
POST /api/v1/auth/register
Content-Type: application/json
```

**Request**

```json
{
"email": "user@example.com",
"name": "Display Name",
"password": "your-password"
}
```

**Response** `201` — same shape as login (auto sign-in)

```json
{
"access_token": "<jwt>",
"token_type": "bearer"
}
```

New users have `organization_id: null` (join an org later via `POST /users/me/organization`).

**Errors:** `409` duplicate email

### Login (public)

```http
POST /api/v1/auth/login
Content-Type: application/json
```

**Request**

```json
{
"email": "user@example.com",
"password": "your-password"
}
```

**Response** `200`

```json
{
"access_token": "<jwt>",
"token_type": "bearer"
}
```

**Errors:** `401` — `{ "detail": "...", "code": "authentication_error" }`

---

## Error format

Most application errors:

```json
{
"detail": "Human-readable message",
"code": "authentication_error"
}
```

| HTTP | `code` (examples) |
|------|-------------------|
| 401 | `authentication_error` |
| 403 | `authorization_error` |
| 409 | `conflict_error` |
| 404 | FastAPI default `{ "detail": "..." }` |
| 422 | Validation errors (field list) |

---

## Public endpoints

| Method | Path | Response |
|--------|------|----------|
| `GET` | `/health` | `{ "status": "ok" }` |
| `GET` | `/api/v1/health` | `{ "status": "ok" }` |
| `POST` | `/api/v1/auth/register` | Create account + JWT (`201`) |
| `POST` | `/api/v1/auth/login` | See above |

---

## Protected endpoints (JWT required)

### Users — `/api/v1/users`

| Method | Path | Access | Notes |
|--------|------|--------|-------|
| `GET` | `/users/me` | Any authenticated user | Current profile |
| `PATCH` | `/users/me` | Any authenticated user | Update own profile |
| `POST` | `/users/me/organization` | Tenant only (not super admin) | One-time join org |
| `GET` | `/users` | Super admin | List users |
| `POST` | `/users` | Super admin | Admin-create user (optional `organization_id`) |
| `GET` | `/users/{user_id}` | Self or super admin | Get user by id |
| `PATCH` | `/users/{user_id}` | Super admin | Update user (use `/me` for self) |
| `DELETE` | `/users/{user_id}` | Super admin | Delete user |

#### `GET /users/me` — `200`

**Response:** `UserResponse`

#### `PATCH /users/me` — `200`

**Request** (all fields optional)

```json
{
"name": "string",
"email": "user@example.com",
"password": "new-password"
}
```

**Response:** `UserResponse`

#### `POST /users/me/organization` — `200`

**Request**

```json
{
"organization_id": "uuid"
}
```

**Response:** `UserResponse`

**Errors:** `403` super admin; `409` already in an org

#### `GET /users` — `200` (super admin)

**Query**

| Param | Type | Description |
|-------|------|-------------|
| `organization_id` | uuid | Filter by org |
| `unassigned_only` | bool | Users with no org |

**Response**

```json
{
"items": [ /* UserResponse[] */ ]
}
```

#### `POST /users` — `201` (super admin only)

Use **`POST /auth/register`** for self-service signup (no JWT).

**Request**

```json
{
"email": "user@example.com",
"name": "Display Name",
"password": "optional",
"organization_id": "uuid or omit"
}
```

**Response:** `UserResponse`

#### `GET /users/{user_id}` — `200`

**Response:** `UserResponse`

**Errors:** `403` not self/super admin; `404` not found

#### `PATCH /users/{user_id}` — `200` (super admin)

**Request** (all fields optional)

```json
{
"name": "string",
"email": "user@example.com",
"password": "string",
"organization_id": "uuid or null to unassign"
}
```

**Response:** `UserResponse`

#### `DELETE /users/{user_id}` — `204` (super admin)

No body.

---

### Organizations — `/api/v1/organizations` (super admin only)

| Method | Path | Status |
|--------|------|--------|
| `GET` | `/organizations` | `200` |
| `POST` | `/organizations` | `201` |
| `GET` | `/organizations/{organization_id}` | `200` |
| `PATCH` | `/organizations/{organization_id}` | `200` |
| `DELETE` | `/organizations/{organization_id}` | `204` |

#### `GET /organizations` — `200`

```json
{
"items": [ /* OrganizationResponse[] */ ]
}
```

#### `POST /organizations` — `201`

**Request**

```json
{
"name": "Acme Inc",
"meta": {}
}
```

**Response:** `OrganizationResponse`

#### `GET /organizations/{organization_id}` — `200`

**Response:** `OrganizationResponse`

#### `PATCH /organizations/{organization_id}` — `200`

**Request** (optional fields)

```json
{
"name": "New Name",
"meta": { "tier": "pro" }
}
```

**Response:** `OrganizationResponse`

#### `DELETE /organizations/{organization_id}` — `204`

**Errors:** `409` if users or import jobs still reference the org

---

### Imports — `/api/v1/imports`

| Method | Path | Status |
|--------|------|--------|
| `POST` | `/imports` | `202` |
| `GET` | `/imports/{import_job_id}` | `200` |

#### `POST /imports` — `202`

**Content-Type:** `multipart/form-data`

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `file` | file | yes | — |
| `account_id` | string | no | `"default"` |
| `user_id` | uuid | no | default env user |

Target user must have joined an organization (`organization_id` set), or `403`.

**Response:** `ImportJobResponse`

#### `GET /imports/{import_job_id}` — `200`

**Response:** `ImportJobResponse`

---

### Query (RAG) — `/api/v1/query`

| Method | Path | Status |
|--------|------|--------|
| `POST` | `/query` | `200` |

#### `POST /query` — `200`

**Query:** `isDevelopment` (bool, default `false`)

**Request**

```json
{
"query": "What did we discuss about X?",
"user_id": "uuid"
}
```

`user_id` is the **target user** for search scope (may differ from JWT user).

**Response**

```json
{
"answer": "string",
"sources": [
  {
    "content": "string | null",
    "distance": 0.12,
    "message_id": "string | null",
    "conversation_id": "string | null",
    "sender": "string | null",
    "import_job_id": "string | null"
  }
]
}
```

`sources` may be `null`.

---

### Tasks (Celery demo) — `/api/v1/tasks`

| Method | Path | Status |
|--------|------|--------|
| `POST` | `/tasks` | `202` |
| `GET` | `/tasks/{task_id}` | `200` |

#### `POST /tasks` — `202`

**Request**

```json
{
"message": "string (1-500 chars)"
}
```

**Response**

```json
{
"task_id": "string",
"status": "queued"
}
```

#### `GET /tasks/{task_id}` — `200`

**Response**

```json
{
"task_id": "string",
"status": "PENDING | STARTED | SUCCESS | FAILURE | RETRY | REVOKED",
"result": "string | null",
"error": "string | null"
}
```

---

## Shared types

### UserResponse

```json
{
"id": "uuid",
"organization_id": "uuid | null",
"email": "user@example.com",
"name": "string",
"super_admin": false,
"created_at": "ISO-8601 datetime",
"updated_at": "ISO-8601 datetime"
}
```

### OrganizationResponse

```json
{
"id": "uuid",
"name": "string",
"meta": {},
"created_at": "ISO-8601 datetime",
"updated_at": "ISO-8601 datetime"
}
```

### ImportJobResponse

```json
{
"id": "uuid",
"user_id": "uuid",
"organization_id": "uuid",
"source": "claude",
"status": "pending | processing | completed | failed",
"file_name": "string",
"file_hash": "string",
"stats": {
  "conversations_count": 0,
  "messages_created": 0,
  "messages_updated": 0,
  "conversations_skipped": 0,
  "embeddings_created": 0,
  "embeddings_skipped": 0
},
"error_message": "string | null",
"started_at": "ISO-8601 | null",
"completed_at": "ISO-8601 | null",
"created_at": "ISO-8601",
"celery_task_id": "string | null",
"duplicate": false
}
```

---

## Roles (UI routing)

| Role | `super_admin` | `organization_id` | Can use |
|------|---------------|-------------------|---------|
| Platform super admin | `true` | `null` | Organizations CRUD, users admin, `/users/me` |
| Tenant (no org) | `false` | `null` | `/users/me`, join org |
| Tenant (joined) | `false` | uuid | Profile, imports, query |

Super admin is set in the database only, not via API.

---

## Typical flows

### Super admin

1. `POST /api/v1/auth/login`
2. `POST /api/v1/organizations` — create orgs
3. `POST /api/v1/users` — create users (optional `organization_id`)
4. `PATCH /api/v1/users/{id}` — assign or move users between orgs

### Tenant

1. `POST /api/v1/auth/register` or `POST /api/v1/auth/login`
2. `GET /api/v1/users/me` — if `organization_id` is null, show join UI
3. `PATCH /api/v1/users/me` — update own profile
4. `POST /api/v1/users/me/organization` — join org
5. `POST /api/v1/imports` — upload export (`user_id` = self)
6. `POST /api/v1/query` — ask questions (`user_id` = self)
