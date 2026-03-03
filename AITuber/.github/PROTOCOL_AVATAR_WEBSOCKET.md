# Avatar WebSocket Protocol (SRS summary)

This document mirrors the SRS A-7 contract at a high level.
The source of truth is the SRS; keep this doc in sync.

## Endpoint
- Default: `ws://127.0.0.1:31900`

## Commands
- `avatar_update`: emotion/gesture/look_target/mouth_open
- `avatar_event`: one-shot effects
- `avatar_config`: initial settings
- `avatar_reset`: neutral reset
- `avatar_viseme`: viseme event timeline (optional)

## Live2D requirements
Live2D must be able to implement viseme switching:
- Recommended: multiple viseme parameters (V_A..V_O etc.) with crossfade.
- Fallback: single axis ParamMouthForm with intervals.

## Backward compatibility
- Ignore unknown fields.
- Unknown commands must not crash the client.
