# Run Lifecycle Contract

Hephaestus invention is an intensive task. Running the 5-stage pipeline inline blocks Web workers, loses progress on crashes, and scales poorly. The execution architecture relies strictly on durable workers.

## The Durable Execution Plane

### 1. Run Generation (`RunRecord`)
Every invention dispatched generates a `RunRecord` mapped to a UUID.
* **Included Fields:** `run_id`, `status`, `created_at`, `request_snapshot`, `config_snapshot`, `current_stage`, `result_ref`.
* **Cost tracking:** `cost_usd` is actively mutated and persisted at each stage completion. Checkpoints assert budget boundaries.

### 2. Orchestration (`RunOrchestrator`)
The Orchestrator defines a formal loop:
1. **Queue Dispatch:** `POST /api/runs` inserts a `RunRecord` in `RunStatus.QUEUED`.
2. **Worker Pool:** `orchestrator.start_worker()` pulls records globally (or locally if purely SQLite dev setup). 
3. **Execution Execution:** The run status is shifted to `RunStatus.RUNNING`.
4. **Resumability:** A pipeline crash pauses the execution. Stage history maps checkpoints, preventing duplicating `DECOMPOSE` or `SEARCH` layers. 

### 3. Idempotency & Cancellations
* Duplicate creations sharing an `idempotency_key` return the existing `RunRecord`.
* Setting `cancel_requested=True` does NOT crash the execution thread abruptly. The active stage safely finalizes (or times out) and halts further transition.

### 4. Anti-Patterns Forbidden
* **No `await genesis.invent_stream(...)` within FastAPI route handlers** performing blocking AI loops on HTTP requests.
* **No in-memory `RunStore` dicts.** `SQLiteRunStore` must map to a real filesystem path by default (e.g., `hephaestus_dev.db`).
