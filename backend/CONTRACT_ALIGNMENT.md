# Contract Alignment Record

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
