# GramCare Backend

**GramCare** is an offline-first, low-bandwidth telehealth platform for rural villages in India, built as described in the research paper:
> *"GramCare: A Low-Cost, Offline-First, Low-Bandwidth Telehealth Platform for Rural Villages in India"*

## 🏗️ Architecture

```
Client (Android/Web)
  │── Local SQLite store (offline-first)
  │── Sync agent (outbox, delta sync, exponential backoff)
  │
  └── HTTPS/REST ──► API Gateway (FastAPI)
                         │
                         ├── Auth (OTP + JWT + RBAC)
                         ├── Appointments
                         ├── Patients / Encounters
                         ├── Sync Service (delta sync, conflict resolution)
                         ├── Teleconsultation (peer-to-peer WebRTC, no SFU)
                         ├── Chat + call signaling (Socket.IO)
                         ├── Store-and-Forward
                         ├── Media (MinIO S3)
                         └── Triage (rule-based, advice only)
                         │
                         ├── PostgreSQL (authoritative DB + audit log)
                         ├── Redis (sessions, rate limiting, queues)
                         └── MinIO (images, voice notes, PDFs)
```

## 📁 Project Structure

```
gramcare/
├── docker-compose.yml          # All services: PostgreSQL, Redis, MinIO, coturn (optional), API
├── scripts/
│   └── init.sql                # PostgreSQL initialization
└── backend/
    ├── Dockerfile
    ├── requirements.txt
    ├── alembic.ini
    ├── alembic/
    │   └── env.py              # Async Alembic migrations
    └── app/
        ├── main.py             # FastAPI app entry point
        ├── api/v1/
        │   ├── router.py       # Aggregates all routers
        │   └── endpoints/
        │       ├── auth.py         # OTP request/verify, JWT refresh, logout
        │       ├── patients.py     # Patient registration, records
        │       ├── appointments.py # Booking, slot availability, conflict detection
        │       ├── encounters.py   # Health records + prescriptions
        │       ├── sync.py         # Delta sync upload/pull
        │       ├── teleconsult.py  # Call room + ICE config, store-and-forward
        │       ├── messages.py     # Chat history (live delivery via Socket.IO)
        │       ├── media.py        # Presigned upload/download URLs
        │       ├── triage.py       # Rule-based red-flag checker
        │       └── users.py        # User management + audit logs
        ├── core/
        │   ├── config.py       # Pydantic settings
        │   ├── security.py     # JWT, OTP, hashing
        │   └── deps.py         # FastAPI DI: auth, RBAC, Redis
        ├── db/
        │   └── session.py      # Async SQLAlchemy engine
        ├── models/
        │   └── models.py       # All ORM models
        ├── schemas/
        │   └── schemas.py      # All Pydantic request/response schemas
        ├── realtime/
        │   └── socketio_app.py # WebRTC call signaling + chat (Socket.IO)
        ├── services/
        │   ├── otp_service.py      # Console OTP (no paid SMS gateway)
        │   └── storage_service.py  # MinIO presigned URLs
        └── utils/
            ├── audit.py        # Append-only audit log helper
            └── sync.py         # Version/sequence management
```

## 🚀 Quick Start

### Prerequisites
- Docker & Docker Compose
- Python 3.12+ (for local dev without Docker)

### 1. Start all services with Docker Compose

```bash
cd gramcare
docker compose up -d
```

This starts:
| Service | Port | Purpose |
|---------|------|---------|
| PostgreSQL | 5432 | Authoritative database + audit log |
| Redis | 6379 | Sessions, rate limiting, job queues |
| MinIO | 9000/9001 | Object storage (images, voice notes, PDFs) |
| FastAPI API + Socket.IO | 8000 | REST backend, WebRTC call signaling & chat |
| coturn *(optional)* | 3478 | TURN relay-of-last-resort for strict NATs |

No SFU/media-server and no paid SMS API are used — calls are peer-to-peer
WebRTC signaled over the same Socket.IO server that carries chat, and OTPs
are logged to the console in dev. This is the cost-cutting choice: the whole
stack runs free and self-hosted on one low-cost VM, matching the paper's
deployment target.

### 2. API Documentation

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- Health: http://localhost:8000/health
- Socket.IO endpoint: ws://localhost:8000/socket.io
- MinIO Console: http://localhost:9001 (minioadmin / minioadmin)

### 3. Local development (without Docker)

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env   # Edit as needed
uvicorn app.main:socket_app --reload --port 8000
```

`app.main:socket_app` serves the REST API and the Socket.IO signaling/chat
endpoint on the same port. (`app.main:app` still works and is what the test
suite imports, but it won't have `/socket.io` mounted.)

## 🔐 Authentication Flow

```
1. POST /api/v1/auth/otp/request  { phone, name }
   → OTP sent via SMS (or printed to console in dev)

2. POST /api/v1/auth/otp/verify   { phone, otp }
   → { access_token, refresh_token, user_id, role }

3. All protected endpoints require: Authorization: Bearer <access_token>

4. POST /api/v1/auth/refresh       { refresh_token }
   → New token pair (old refresh token revoked)

5. POST /api/v1/auth/logout        { refresh_token }
   → Revokes refresh token
```

## 📡 Key API Endpoints

| Method | Endpoint | Description | Roles |
|--------|----------|-------------|-------|
| POST | `/api/v1/auth/otp/request` | Request OTP | Public |
| POST | `/api/v1/auth/otp/verify` | Verify OTP → tokens | Public |
| GET | `/api/v1/users/me` | Current user profile | All |
| POST | `/api/v1/patients` | Register patient | CHW, Admin |
| GET | `/api/v1/patients` | List patients | CHW, Doctor, Admin |
| GET | `/api/v1/appointments/slots` | Available slots | All |
| POST | `/api/v1/appointments` | Book appointment | CHW, Admin |
| POST | `/api/v1/encounters` | Create health record | CHW, Admin |
| POST | `/api/v1/encounters/{id}/prescriptions` | Write prescription | Doctor, Admin |
| POST | `/api/v1/sync/upload` | Upload offline changes | All |
| GET | `/api/v1/sync/pull` | Pull server changes | All |
| POST | `/api/v1/teleconsult/room` | Get call room name + ICE servers | All |
| POST | `/api/v1/teleconsult/store-forward` | Submit S&F bundle | CHW |
| GET | `/api/v1/messages/{appointment_id}` | Chat history for an appointment | All |
| POST | `/api/v1/media/presign` | Get upload URL | CHW, Admin |
| POST | `/api/v1/triage/evaluate` | Evaluate red flags | CHW, Admin |
| GET | `/api/v1/audit-logs` | View audit trail | Admin |

## 📞 Real-time: calls + chat (Socket.IO)

Connect to `ws://localhost:8000/socket.io` with `auth: { token: <access_token> }`.

**Call signaling** (peer-to-peer WebRTC, audio-first — no SFU):
```
emit  call:join   { appointment_id }
on    call:peer-joined
emit  call:signal { appointment_id, data }   # SDP offer/answer/ICE, relayed as-is
on    call:signal { appointment_id, data }
emit  call:leave  { appointment_id }
on    call:peer-left
```

**Chat**:
```
emit  chat:join    { appointment_id }
emit  chat:message { appointment_id, body, idempotency_key? }
on    chat:message { id, appointment_id, sender_id, body, created_at }
```

The server authorizes every `join`/`message` against the appointment's
patient/CHW/doctor/admin, and persists chat messages so `GET
/api/v1/messages/{appointment_id}` can back-fill history for anyone who
reconnects or was offline.

## 🔄 Offline Sync Design

The sync service implements the conflict rules from §8.2 of the paper:

| Table | Conflict Rule |
|-------|--------------|
| `encounters`, `prescriptions`, `media_attachments` | **Union merge** (append-only, accepted both) |
| `patient_profiles` | **Last-writer-wins** with conflict logged in audit |
| `appointments` | **Server-authoritative** (rejected offline booking → CHW gets alternative slots) |

Every request uses a client-generated **idempotency key** to prevent duplicate records on retry.

## 🛡️ Security Controls

| Threat | Control |
|--------|---------|
| Unauthorized account access | Phone OTP + short-lived JWT + refresh token rotation |
| Excess access by staff | Role-based access control (patient/CHW/doctor/admin) |
| Interception in transit | TLS 1.2+ for API; DTLS-SRTP for WebRTC (mandatory in the browser/WebRTC stack itself) |
| Lost/stolen device | Offline PIN (device PIN hash stored in DB) |
| Data misuse | Consent recorded at registration; no third-party analytics |
| Tampering | Append-only audit log; idempotent sync with version checking |
| Triage misread as diagnosis | Output labelled "advice only" in every response |

## 🧪 Running Tests

```bash
cd backend
pytest tests/ -v
```

## 📊 Roles

| Role | Description |
|------|-------------|
| `patient` | Books appointments, joins consultations, views own records |
| `chw` | Registers patients, records vitals, books appointments, submits S&F |
| `doctor` | Reviews cases, writes prescriptions, responds to S&F bundles |
| `admin` | Full access, user management, facility management, audit logs |

## 🌐 Multilingual Support

The backend stores `language_code` per user (e.g., `en`, `hi`, `kn`).
The frontend uses this to serve the correct i18n resource file.
Prescription instructions are designed to be read aloud in the local language. 
