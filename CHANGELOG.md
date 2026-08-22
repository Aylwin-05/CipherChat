# Changelog

All notable changes to CipherChat are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- Signal-protocol end-to-end encryption: X3DH key agreement, double ratchet,
  AES-256-GCM message encryption (client-side only; server stores ciphertext).
- Email OTP authentication with JWT access tokens in memory and a rotating
  `HttpOnly` refresh-token cookie; optional two-step verification.
- Multi-device support: per-device prekey bundles, per-device message
  envelopes, one-time prekey replenishment.
- Cross-device history sync via an account sync envelope wrapped by a
  recovery-code-derived key; client-side recovery codes.
- Group chats: admin roles, invite links, member management, group-key
  rotation on membership change, per-participant key wrapping.
- Real-time layer over WebSocket: messaging, typing indicators, presence,
  delivered/read receipts, unread badges.
- Voice and video calls (WebRTC) with frame-level media encryption via
  insertable streams (`RTCRtpScriptTransform`); graceful fallback flagged in
  UI on unsupported browsers.
- Media sharing: client-side encrypted images, files, voice notes, avatars;
  view-once media with post-open download denial.
- Disappearing messages with server-enforced expiry.
- Message features: replies, edits, delete-for-me / delete-for-everyone,
  forwarding with repeat counter, reactions, starred messages, message info
  panel.
- Stories with view tracking, expiry, and privacy levels.
- Contacts: friend requests, directional blocking, privacy toggles for last
  seen / profile photo / stories.
- App lock (peppered HMAC PIN with lockout) and Web Push notifications with
  redacted payloads.
- Docker deployment stack: postgres, redis, backend, nginx; async SMTP with
  retry.
- Rate limiting (Redis or in-memory fallback), global JSON error handling,
  request-id tracing, CSP/HSTS headers.
- Backend test suite (200+ tests) and frontend Signal-protocol test suite.

### Security

- Removed server-side private-key escrow: devices upload public halves only.
- One-time prekeys consumed atomically server-side.
- Identity-key pinning with safety-number verification UI.
- Associated-data binding added to legacy AES-GCM paths.
- Magic-byte sniffing and strict MIME handling on uploads; SVG rejected;
  attachments served as downloads.
- SSRF guards on push endpoints; XFF spoofing hardened; production config
  fail-fast validation.

## [0.4.0]

### Added

- Initial public release of the CipherChat platform: React frontend,
  FastAPI backend, PostgreSQL storage, WebSocket real-time layer, email OTP
  login, and RSA-based encrypted messaging (since superseded by the Signal
  protocol stack).
