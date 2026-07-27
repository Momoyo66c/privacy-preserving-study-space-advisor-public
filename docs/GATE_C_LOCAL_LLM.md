# Gate C: Windows Local LLM Handoff

## Verified outcome

Gate C ranking is deterministic and remains available without an LLM. Ollama
is a local explanation-only dependency:

```text
room status + forecast + effective preferences
                    |
                    v
       deterministic rule adapter
                    |
          fixed rank/score/reasons
                    |
             template text
                    |
        optional Ollama rewrite
```

The LLM cannot participate in ranking, forecasting or preference learning. Any
provider failure retains the fixed result and returns template explanations.

Verified on 2026-07-27:

| Item | Result |
|---|---|
| Windows GPU | NVIDIA GeForce RTX 4060 Laptop GPU, 8 GB |
| Ollama | 0.32.4, loopback only |
| Model storage | `E:\Ollama\models` |
| C-drive model storage | 0 files / 0 bytes after both pulls |
| Selected model | `qwen3:1.7b`, Q4_K_M, manifest `sha256:8f68893c685c3ddff2aa3fffce2aa60a30bb2da65ca488b61fff134a4d1730e7` |
| Selected model blob | `sha256:3d0b790534fe4b79525fc3692950408dca41171676ed7e21db57af5c65ef6ab6` |
| Comparison model | `qwen3:4b`, Q4_K_M, manifest `sha256:359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7` |
| Comparison model blob | `sha256:3e4cb14174460404e7a233e531675303b2fbf7749c02f91864fe311ab6344e4f` |
| GPU offload | 100%, context 2048 |
| 1.7B warm provider benchmark | 10 runs, P50 1.38 s, P95 1.40 s |
| Full recommendation API | 10 stale/unknown runs, P50 1.98 s, P95 2.28 s |
| 1.7B validation | 10/10 accepted outputs, 10/10 unchanged rankings |

The 4B model produced valid, invariant explanations but failed the two-second
target in three consecutive groups: P95 2.63 s, 3.07 s and 2.65 s. The machine
therefore uses the planned 1.7B fallback.

## One-time Windows setup

Exit the Ollama tray application before changing variables:

```powershell
New-Item -ItemType Directory -Force E:\Ollama\models
[Environment]::SetEnvironmentVariable(
  "OLLAMA_MODELS", "E:\Ollama\models", "User"
)
[Environment]::SetEnvironmentVariable("OLLAMA_NO_CLOUD", "1", "User")
[Environment]::SetEnvironmentVariable(
  "OLLAMA_HOST", "127.0.0.1:11434", "User"
)
```

Start Ollama again, then:

```powershell
ollama pull qwen3:1.7b
ollama list
ollama show qwen3:1.7b
ollama ps
```

Do not copy model blobs into the repository. Keep
`C:\Users\<user>\.ollama\models` empty; an empty original directory does not
need to be deleted.

## Backend configuration

Copy `backend/.env.example` to `backend/.env` and set:

```text
RECOMMENDATION_ADAPTER_MODE=rule
RECOMMENDATION_ADAPTER_TIMEOUT_SECONDS=2.5
LLM_ENABLED=true
LLM_BASE_URL=http://127.0.0.1:11434
LLM_MODEL=qwen3:1.7b
LLM_TIMEOUT_SECONDS=2.0
LLM_CONTEXT_TOKENS=2048
LLM_MAX_OUTPUT_TOKENS=160
LLM_KEEP_ALIVE=30m
LLM_LANGUAGE=en
```

For a backend container, change only:

```text
LLM_BASE_URL=http://host.docker.internal:11434
```

Ollama must not bind to a LAN address. The browser never calls port 11434.

## Prewarm and benchmark

The first model load is not included in the warm latency target. Prewarm before
the demo:

```powershell
python -c "import httpx; httpx.post('http://127.0.0.1:11434/api/generate', json={'model':'qwen3:1.7b','prompt':'','stream':False,'think':False,'keep_alive':'30m','options':{'num_ctx':2048,'num_predict':1}}, timeout=180).raise_for_status()"
```

Then run:

```powershell
cd backend
python scripts\benchmark_llm.py --model qwen3:1.7b --runs 10 --timeout 2
```

The report must show all runs under `ranking_invariant_runs`. An output rejected
by the fact/privacy validator appears as `LLM_INVALID_OUTPUT` and uses templates.
The deterministic TestClient benchmark measured recommendation context P95 at
17.52 ms, below the 500 ms ranking target.

## Degradation demonstration

1. Request a three-room recommendation with Ollama running. The response should
   use `explanation_source=llm`.
2. Stop Ollama or set `LLM_ENABLED=false`, restart the backend and request the
   same recommendation.
3. Confirm rank, score, reasons and score breakdown are identical. Explanation
   source becomes `template`; warning is one of `LLM_DISABLED`,
   `LLM_UNAVAILABLE` or `LLM_TIMEOUT`.
4. Mark one configured sensor degraded/offline. The affected subscore is omitted
   or the health factor is reduced; the endpoint remains available.
5. Only a complete rule-adapter exception may return the marked `stub`.

`GET /health` reports adapter, provider, model and mode. An unavailable enabled
LLM makes health `degraded` but keeps HTTP 200 while the database is healthy.

## Privacy boundary

The provider receives only anonymous room ID/name, final rank and score,
approved structured reasons, current state/occupancy, 30-minute forecast,
confidence, stale and non-identifying effective preference context. It never
receives usernames, user IDs, cookies, tokens, selection history, prompts from
users, raw audio, full thermal arrays, radar tracks or precise personal
location. Recommendation audit rows store adapter/source/latency/fallback
summaries, not prompts or complete LLM responses.
