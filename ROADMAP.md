# Roadmap

## Done

- Email OTP login with rotating HttpOnly refresh cookie
- Signal-protocol E2EE (X3DH, double ratchet, AES-256-GCM)
- Real-time messaging, typing, presence, read/delivered receipts (WebSocket)
- Encrypted image + voice-note transfer
- Multi-device bundles and one-time prekey replenishment
- Rate limiting (Redis / in-memory), global JSON errors, request-id tracing
- Unread badges, live presence in the chat header
- Docker stack (postgres + redis + backend + nginx), async SMTP with retry

## Next

- Group chats (multi-participant conversations + per-recipient key wrapping)
- Message search (server-side over ciphertext metadata with client-side filtering)
- Message reply / edit UI (server + client)
- Voice & video calls (WebRTC with E2EE, SFU or P2P)
- WS presence merged across multiple conversations (user-scoped socket)
- Attachment encryption at rest (server-side envelope)

## Backlog

- Contact/block lists, message status history view
- Android / iOS / desktop clients sharing the same session store
- P2P backup of session keys with passphrase-derived encryption