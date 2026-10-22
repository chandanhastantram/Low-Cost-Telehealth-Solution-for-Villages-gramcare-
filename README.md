<div align="center">

# 🏡 GramCare

**A village health register that brings a doctor one phone call away.**

Low-cost, offline-first, low-bandwidth telehealth for rural villages in India — community health workers register patients and record vitals, doctors consult over peer-to-peer audio/video, and nothing breaks when the signal does.

Based on the research paper *“GramCare: A Low-Cost, Offline-First, Low-Bandwidth Telehealth Platform for Rural Villages in India.”*

`FastAPI` · `Socket.IO` · `WebRTC` · `PostgreSQL` · `React` · `Vite`

</div>

---

## Contents

- [What it does](#what-it-does)
- [Who uses it](#who-uses-it)
- [Built for bad networks](#built-for-bad-networks)
- [Architecture](#architecture)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [Calls & chat](#calls--chat)
- [Offline sync](#offline-sync)
- [Security](#security)
- [API overview](#api-overview)
- [Testing](#testing)
- [Deployment](#deployment)
- [Project structure](#project-structure)
- [Roadmap](#roadmap)

---

## What it does

| | |
|---|---|
| 📋 **Register villagers** | Phone, name, basic history, and recorded consent — in two steps. |
| 🩺 **Record visits** | Vitals with live out-of-range warnings, tap-to-select symptoms, chief complaint. |
| 🚦 **Red-flag triage** | Rule-based, traffic-light triage on every visit. Always labelled *advice only*. |
| 📅 **Book doctors** | Live free slots in the clinic's time zone; if a slot is taken, alternatives are offered instantly. |
| 📞 **Consult** | Peer-to-peer audio (video optional) + chat in the same room. No media server, no per-minute cost. |
| 📨 **Store & forward** | When a live call isn't possible, the CHW sends the case; a doctor replies later, optionally with a prescription. |
| ℞ **Prescribe** | Multi-medicine prescriptions with advice and follow-up date, added to the patient's file. |
| 🔒 **Offline PIN** | App locks after 5 idle minutes and unlocks on-device with no network. |
| 🧾 **Audit trail** | Append-only log of who read or changed what. |

The UI is styled as a paper register — ruled cards, rubber-stamp confirmations, a marigold *toran* over each page — with a **Daylight / Lantern** theme toggle on every screen.

## Who uses it

| Role | Can do |
|---|---|
| **Health worker (CHW)** | Register patients in their facility, record visits, book consults, send store-and-forward cases, read doctors' replies |
| **Doctor** | Run consultations, write prescriptions, answer the store-and-forward queue |
| **Patient** | See their appointments, visit history and prescriptions; cancel their own appointment |
| **Admin** | Onboard doctors and CHWs, create facilities, assign people to facilities, (de)activate accounts, read the audit trail |

## Built for bad networks

Rural links drop, crawl, and come back. The consultation room is designed (and tested) for that:

- **Calls resume by themselves.** WebRTC uses the *perfect negotiation* pattern, restarts ICE when the path fails, and renegotiates automatically when either side reconnects or reloads.
- **Messages are never lost.** Sends are optimistic and kept in an outbox (persisted in the browser) until the server acknowledges them; idempotency keys mean retries never duplicate. Missed messages are back-filled after every reconnect.
- **Audio first.** Video is optional, capped at ~250 kbps and 320×240.
- **Works where WebSockets don't.** Socket.IO falls back to HTTP long-polling.
- **You can see the network.** A signal meter (*Good signal / 2G mood / Offline*) and an in-call quality meter.

An end-to-end stress test (two real browsers) covers: chat both ways, audio flowing both ways, simultaneous camera changes, one side going offline mid-call and mid-chat, a tab reload mid-call, and an unsent message surviving a reload.

## Architecture

```
 Phone / browser (React)
   ├─ REST (axios, auto token refresh) ──────────────┐
   ├─ Socket.IO ── chat + WebRTC signalling ─────────┤
   └─ WebRTC media ── peer to peer (TURN if needed) ─┼──► other participant
                                                     │
                                       FastAPI + Socket.IO  (one process)
                                         ├─ Auth: OTP + JWT + refresh rotation
                                         ├─ Patients · Encounters · Prescriptions
                                         ├─ Appointments + slot scheduling
                                         ├─ Delta sync (change log + conflict rules)
                                         ├─ Store-and-forward · Triage · Media
                                         └─ Record-level access control
                                                     │
                       PostgreSQL ── Redis (optional) ── MinIO (optional)
```

No SFU, no paid SMS, no paid SaaS: the whole stack runs on one small VM.

## Quick start

### Prerequisites

- Python 3.12+
- Node.js 20+
- PostgreSQL 16 (local, Docker, or a free hosted one such as Neon)

### Option A — Docker Compose (everything)

```bash
docker compose up -d        # Postgres, Redis, MinIO, API (+ optional coturn)
cd frontend && npm install && npm run dev
```

### Option B — run it yourself

**Backend**

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env         # set DATABASE_URL and SECRET_KEY
alembic upgrade head
uvicorn app.main:socket_app --reload --port 8000
```

> Use `app.main:socket_app`, not `app.main:app` — only `socket_app` serves Socket.IO (calls and chat).

**Frontend**

```bash
cd frontend
npm install
npm run dev                  # http://localhost:5173
```

Set `VITE_API_URL` / `VITE_SOCKET_URL` in `frontend/.env` if the API isn't on `http://127.0.0.1:8000`.

**Log in:** with `DEBUG=true` (or `DEMO_LOGIN_ENABLED=true`) the login page offers one-click demo accounts for every role. Otherwise use phone + OTP — in development the OTP is printed in the API console.

| Service | URL |
|---|---|
| Web app | http://localhost:5173 |
| API docs (debug only) | http://localhost:8000/docs |
| Health check | http://localhost:8000/health |

## Configuration

All backend settings are environment variables (see `backend/.env.example`).

| Variable | Purpose | Default |
|---|---|---|
| `DATABASE_URL` | Async Postgres URL (`postgresql+asyncpg://…`) | local Postgres |
| `SECRET_KEY` | JWT signing key — **change in production** | — |
| `DEBUG` | Debug logging, `/docs`, demo logins | `true` |
| `DEMO_LOGIN_ENABLED` | Demo logins without the rest of debug mode | `false` |
| `ALLOWED_ORIGINS` | Comma-separated CORS origins (your frontend URL) | localhost |
| `CONSOLE_OTP` | Print OTPs to the server log (no SMS gateway) | `true` |
| `CLINIC_UTC_OFFSET_MINUTES` | Doctors' hours are clinic-local time | `330` (IST) |
| `STUN_URLS` | STUN servers | Google STUN |
| `TURN_ENABLED`, `TURN_URL`, `TURN_USERNAME`, `TURN_CREDENTIAL` | Self-hosted TURN (`TURN_URL` may list several) | off |
| `TURN_CREDENTIALS_URL` | Hosted TURN credentials endpoint (e.g. Metered) | — |
| `REDIS_URL` | Rate limiting & PIN lockout (optional — degrades gracefully) | local Redis |
| `MINIO_*` | Object storage for photos / voice notes | local MinIO |

## Calls & chat

Everything happens in the appointment's consultation room. Connect to Socket.IO with `auth: { token }`.

| Event | Direction | Notes |
|---|---|---|
| `chat:join` | → server | Re-sent after every reconnect |
| `chat:message` | → server | `{appointment_id, body, idempotency_key}` · ack `{ok, message}` |
| `chat:message` | ← server | Broadcast to the other participants |
| `chat:typing` | ↔ | Typing indicator |
| `call:join` | → server | Ack `{ok, peers}` — peers already in the call |
| `call:signal` | ↔ | SDP description / ICE candidate, relayed with the sender's id |
| `call:peer-joined` / `call:peer-left` / `call:peer-offline` | ← server | Presence |
| `call:leave` | → server | Also sent on tab close |

Only participants of an appointment (its patient, the assigned doctor, the CHW or a CHW of the patient's facility, admins) can join its rooms; signals are relayed only for sockets that joined.

**TURN:** direct peer-to-peer connections fail on some networks (often between two mobile carriers). For real-world use configure a TURN relay — either self-host [coturn](https://github.com/coturn/coturn) (included in `docker-compose.yml`, needs a VM with public UDP) or set `TURN_CREDENTIALS_URL` to a hosted provider.

## Offline sync

Devices keep working offline and sync through `/api/v1/sync/upload` and `/api/v1/sync/pull`. Every write — through REST or sync — is recorded in a change log with a monotonically increasing version, so a device that pulls `since=N` sees everything after `N`.

| Data | Conflict rule (paper §8.2) |
|---|---|
| Encounters, prescriptions | **Union merge** — inserts always accepted; edits refused (corrections are new entries) |
| Patient profiles | **Last-writer-wins** — the overwritten server copy is returned and logged |
| Appointments | **Server-authoritative** — a stale change or a taken slot is rejected with alternative slots |

Uploads are validated with the same schemas and access rules as the REST API, each entry in its own savepoint, with a per-entry result. Pulls are scoped: patients get only their own records, CHWs their facility.

## Security

| Threat | Control |
|---|---|
| Account takeover | Phone OTP (cryptographically random) · short-lived JWT · rotating refresh tokens |
| Staff seeing too much | Role checks **and** record-level checks (facility for CHWs, self for patients) |
| Interception | TLS for the API; DTLS-SRTP for WebRTC media |
| Lost phone | Offline PIN with auto-lock; 5 wrong tries end the session |
| Call hijacking | Signals only relayed between authorised members of the room |
| Tampering | Append-only audit log; idempotent, versioned sync |
| Triage mistaken for diagnosis | Every result labelled *advice only — a doctor decides* |

## API overview

Full interactive docs at `/docs` when `DEBUG=true`.

| Area | Endpoints |
|---|---|
| Auth | `POST /auth/otp/request` · `POST /auth/otp/verify` · `POST /auth/refresh` · `POST /auth/logout` · `POST /auth/dev-login` |
| Me | `GET/PATCH /users/me` · `PUT/DELETE /users/me/pin` · `POST /users/me/pin/verify` |
| Admin | `GET /users` · `PATCH /users/{id}` · `POST /doctors` · `POST /chws` · `GET/POST /facilities` · `GET /audit-logs` |
| Patients | `POST/GET /patients` · `GET /patients/me` · `GET/PATCH /patients/{id}` · `GET /patients/{id}/records` · `POST /patients/{id}/consent` |
| Appointments | `GET /appointments/slots` · `POST/GET /appointments` · `GET/PATCH /appointments/{id}` |
| Encounters | `POST /encounters` · `GET /encounters/{id}` · `POST/GET /encounters/{id}/prescriptions` |
| Teleconsult | `POST /teleconsult/room` · `GET /teleconsult/ice-servers` · `POST/GET /teleconsult/store-forward` · `POST /teleconsult/store-forward/{id}/respond` |
| Chat | `GET /messages/{appointment_id}` |
| Sync | `POST /sync/upload` · `GET /sync/pull` · `GET /sync/status` |
| Triage | `POST /triage/evaluate` · `GET /triage/rules` |
| Media | `POST /media/presign` · `POST /media/{id}/complete` · `GET /media/{id}/download` |

All paths are under `/api/v1`.

## Testing

```bash
cd backend
pytest -v
```

25 self-contained tests (SQLite, in-memory Redis stub, captured OTPs — no services needed) covering auth, triage, record-level access, booking conflicts, encounters and prescriptions, sync conflict rules and pull scoping, store-and-forward, and the offline PIN.

```bash
cd frontend
npm run build
npm run lint
```

## Deployment

The repo is ready for a **Railway (API) + Vercel (web) + Neon (Postgres)** setup:

- `backend/Dockerfile` honours `$PORT` and runs `alembic upgrade head` before starting.
- `backend/railway.json` sets the build and the `/health` check.
- `frontend/vercel.json` rewrites all routes to the SPA.

Production checklist:

1. Set `DATABASE_URL`, a fresh `SECRET_KEY`, `DEBUG=false`, `APP_ENV=production`.
2. Set `ALLOWED_ORIGINS` to the frontend URL; set `VITE_API_URL` and `VITE_SOCKET_URL` on the frontend to the API URL.
3. Configure TURN (see [Calls & chat](#calls--chat)).
4. Decide on `DEMO_LOGIN_ENABLED` — with it on, anyone with the link can log in as any role.
5. Serve over HTTPS — browsers only allow microphone/camera on secure origins.

## Project structure

```
gramcare/
├── docker-compose.yml          Postgres, Redis, MinIO, API, coturn
├── scripts/init.sql
├── backend/
│   ├── Dockerfile · railway.json · requirements.txt · alembic/
│   ├── app/
│   │   ├── main.py             FastAPI app + Socket.IO mount (socket_app)
│   │   ├── api/v1/endpoints/   auth, users, patients, appointments, encounters,
│   │   │                       teleconsult, messages, media, triage, sync
│   │   ├── core/               config, security, deps (roles), access (records)
│   │   ├── models/ · schemas/
│   │   ├── realtime/           Socket.IO: chat + WebRTC signalling
│   │   ├── services/           scheduling, OTP, storage
│   │   └── utils/              audit log, sync change log
│   └── tests/
└── frontend/
    ├── vercel.json
    └── src/
        ├── pages/              Login, Dashboard, Book, Register, Room, Records,
        │                       Store & forward, Profile, Admin, Audit
        ├── components/         Layout, Shell (lock + palette), theme, signal meter
        ├── lib/                useCall, useChat, useRoomSocket, sync helpers, copy
        └── ui/                 component kit, toasts, hand-drawn doodles
```

## Roadmap

- Full offline client (IndexedDB store + sync outbox for visits and registrations)
- Interface translations (Hindi, Kannada, Tamil, …) — language preference is already stored per user
- Free SMS / WhatsApp OTP gateway
- Read-aloud prescriptions in the patient's language
- IVR / USSD access for feature phones

---

<div align="center">
Made for the last mile. 🌾
</div>
