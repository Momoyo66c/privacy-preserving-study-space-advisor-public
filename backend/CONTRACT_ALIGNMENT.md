# Contract Alignment Record

## Authenticated 1.0 additions

| Boundary | Schema | Endpoint/consumer |
|---|---|---|
| Module 4 client to authenticated API | `auth_credentials.schema.json`, `auth_session_response.schema.json`, `user_response.schema.json`, `delete_result.schema.json` | register/login/session/current-user/deletion |
| Module 4 client to personalized recommendation | `authenticated_recommendation_request.schema.json`, `me_preferences.schema.json`, `me_preference_update.schema.json` | `/api/v1/me/preferences` and `/api/v1/me/recommendations` |
| Module 4 client to selection learning | `room_selection_request.schema.json`, `room_selection_accepted.schema.json`, `room_selection_history.schema.json` | idempotent `/api/v1/me/room-selections` |

Authenticated clients never send a user ID or preference weights in recommendation requests. The backend derives both from the HttpOnly session. Selection requests use a UUID idempotency key and never accept client timestamps.

Module 3 implements shared contract version `1.0`.

| Boundary | Schema | Endpoint/consumer |
|---|---|---|
| Module 2 → 3 observation | `edge_observation.schema.json` | `POST /api/v1/edge/observations` |
| Module 2 → 3 preview | `thermal_preview.schema.json` | `PUT /api/v1/edge/rooms/{room_id}/thermal-preview` |
| Module 3 → 4 metadata/status | `room_metadata.schema.json`, `room_status.schema.json` | room list, status and detail routes |
| Module 3 → 4 history/forecast | `room_history.schema.json`, `forecast_result.schema.json` | history and forecast routes |
| Module 3 ↔ 4 preferences/recommendation | `preference_profile.schema.json`, `recommendation_*.schema.json` | preference and recommendation routes |
| All modules | `error.schema.json` | unified HTTP errors |

Known feature-summary fields are optional/nullable for degraded inputs, while unknown fields are rejected. All response and error envelopes include `schema_version=1.0`. Shared fixtures are validated by both JSON Schema and backend Pydantic tests.
