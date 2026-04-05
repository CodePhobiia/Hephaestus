# Deployment Model

Hephaestus scales according to the provided infrastructure layer. 

## Storage Provider Authority

1. **PostgreSQL** is the sole production authority for Run Store, Analytics, and Telemetry (where applicable).
   * Schema transitions are enforced exclusively via `scripts/migrate.py`.
   * Concurrent node operations demand Postgres locks.
2. **SQLite** remains strictly as a local test/development fallback.
   * Its files must rest durably on disk (e.g. `./data/hephaestus.db`). Using `:memory:` to run ephemeral operations on live APIs is invalid product behavior. 

## The Multi-Layer Packaging Rule

Heavyweight components delay imports. A standard Python container install (e.g. `pip install -e .`) yields a Fast-booting web API and orchestrator plane.

Providers (Anthropic, OpenAI) and advanced ML assets (`sentence-transformers`, `numpy`) load lazily exclusively at the functional boundary, avoiding crash-on-import behavior on minimal infrastructure. 

Metrics exist on a `/api/metrics` Prometheus text-exposition scrape endpoint, while OpenTelemetry (OTLP) instrumentation operates transparently and exports asynchronously based on `OTLP_ENDPOINT` environment toggles.
