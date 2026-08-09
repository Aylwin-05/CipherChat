# CipherChat

A privacy-first, end-to-end encrypted messaging platform.

**Frontend:** React 19 + Vite · **Backend:** FastAPI + SQLAlchemy + Alembic · **Storage:** PostgreSQL · **Cache/Rate-limit:** Redis · **Crypto:** X25519 / Ed25519 / AES-256-GCM, Double Ratchet (Signal-style).

## Features

- Email OTP authentication with HttpOnly refresh-token rotation
- End-to-end encryption: X3DH key agreement + double ratchet, AES-256-GCM keyed by the ratchet
- Client-side encrypted image transfer and voice notes
- Real-time messaging, typing indicators, presence, delivered/read receipts
- Multi-device key bundles with one-time prekey replenishment
- Rate-limited endpoints (Redis or in-memory), global JSON error handling, request-id tracing

## Architecture

Crypto happens **only in the browser**. The backend stores ciphertext, encrypted AES keys, and metadata — it never sees plaintext or private keys. Encryption flows:

```
Sender                                                      Recipient
  |  X3DH (X25519 + signed prekey + OPK) --------> session  |
  |  Double ratchet / AES-GCM ciphertext -------------------> decrypt
  |                                                        |
  |  Attachment AES key encrypted for each participant       |
```

## Development

Prerequisites: **PostgreSQL 14+** running locally on `:5432` (create the
`cipherchat` database and match the credentials in `backend/.env`). Redis is
optional — without `REDIS_URL` the app falls back to in-memory rate limiting
(fine for one local instance). Mail: the `.env` `SMTP_*` values for real OTP
delivery.

### Backend

```bash
cd backend
python -m venv .venv && .venv\Scripts\activate   # or source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                              # fill in values
alembic upgrade head
uvicorn app.main:app --reload                     # http://localhost:8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173, proxies /api + /ws to :8000
```

Open **http://localhost:5173** — sign up with a real inbox address; the OTP
arrives by email (Gmail app password recommended).

### Tests

```bash
cd backend && python -m pytest tests
cd frontend && npm test
```

## Production (Docker)

```bash
cp .env.example .env    # SECRET_KEY, MASTER_KEY, SMTP_*, CORS_ORIGINS
docker compose up --build
```

- nginx serves the SPA and proxies `/api`, `/uploads`, and `/ws` to the backend
- postgres and redis run as managed services with health checks
- `alembic upgrade head` runs automatically at backend startup

## Security Notes

- Access tokens live in memory; the refresh token is a rotating `HttpOnly` cookie
- WebSocket auth uses the `Sec-WebSocket-Protocol` subprotocol, never the URL
- Set `COOKIE_SECURE=true`, a locked-down `CORS_ORIGINS`/`ALLOWED_HOSTS`, and `DEBUG=false` in production

## Roadmap

See [ROADMAP.md](ROADMAP.md) for planned features (group chats, message search, voice/video calls).

## License

MIT