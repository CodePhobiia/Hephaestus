# Hephaestus Operations Runbook

## Overview

This runbook covers deployment, monitoring, and incident response for Hephaestus in production.

---

## 1. Deployment

### Prerequisites

- Docker or Podman runtime
- PostgreSQL >= 14
- Python >= 3.11 (for local dev)

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `HEPHAESTUS_DATABASE_URL` | Yes (prod) | — | PostgreSQL connection string |
| `ANTHROPIC_API_KEY` | Yes | — | Anthropic API key |
| `OPENAI_API_KEY` | No | — | OpenAI API key (optional provider) |
| `PERPLEXITY_API_KEY` | No | — | Perplexity research API key |
| `HEPH_API_KEY` | Yes (web) | — | API authentication key |
| `HEPH_RATE_LIMIT_RPM` | No | 10 | Requests per minute limit |
| `HEPH_MAX_CONCURRENT` | No | 2 | Max concurrent pipeline runs |
| `HEPH_SPEND_LIMIT_USD` | No | 20.0 | Global spend ceiling per session |
| `OTLP_ENDPOINT` | No | — | OpenTelemetry collector endpoint |
| `HEPHAESTUS_LOG_FORMAT` | No | json | Logging format (json or text) |
| `HEPHAESTUS_LOG_LEVEL` | No | INFO | Log level |

### Initial Deployment

```bash
# 1. Run schema migrations
python scripts/migrate.py up --dsn="$HEPHAESTUS_DATABASE_URL"

# 2. Build container
docker build -t hephaestus:latest .

# 3. Run
docker run -d \
  --name hephaestus \
  -p 8000:8000 \
  -e HEPHAESTUS_DATABASE_URL="..." \
  -e ANTHROPIC_API_KEY="..." \
  -e HEPH_API_KEY="..." \
  hephaestus:latest
```

### Rolling Updates

```bash
# 1. Run any new migrations
python scripts/migrate.py up --dsn="$HEPHAESTUS_DATABASE_URL"

# 2. Rebuild and restart
docker build -t hephaestus:next .
docker stop hephaestus
docker rm hephaestus
docker run -d --name hephaestus -p 8000:8000 ... hephaestus:next
```

---

## 2. Health Checks

### Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/health` | GET | Liveness check |
| `/api/metrics` | GET | Prometheus-format metrics |
| `/api/providers` | GET | Provider availability |

### Alerts

- **High error rate:** If `heph_runs_total{status="failed"}` exceeds 20% of total in 15min
- **Provider degraded:** If any provider health check returns `DEGRADED`
- **Cost ceiling:** If `heph_spend_usd_current_hour` approaches `HEPH_SPEND_LIMIT_USD`
- **Stale runs:** If `heph_active_runs` stays elevated for > 30min

---

## 3. Incident Response

### Pipeline Failures

1. Check `/api/metrics` for error rate trends
2. Review structured logs for the `run_id` and `correlation_id`
3. Check provider health: `GET /api/providers`
4. If MCP server issues: check circuit breaker state in health tracker

### Database Issues

```bash
# Check migration status
python scripts/migrate.py status --dsn="$HEPHAESTUS_DATABASE_URL"

# Clean up stale runs (automatic, but can be triggered manually)
# The orchestrator's cleanup task runs every 10 minutes
```

### Cost Overruns

1. Check `heph_cost_usd_total` metric
2. Review per-user/tenant aggregates via RunStore
3. Adjust `HEPH_SPEND_LIMIT_USD` if needed
4. Budget violations are logged at WARNING level

---

## 4. Migration Management

```bash
# View status
python scripts/migrate.py status --dsn="..."

# Apply all pending
python scripts/migrate.py up --dsn="..."

# Roll back to version N
python scripts/migrate.py down --target=N --dsn="..."
```

---

## 5. Observability Stack

### Structured Logging

All logs are JSON-formatted with correlation IDs:

```json
{
  "timestamp": "2024-01-01T00:00:00Z",
  "level": "INFO",
  "logger": "hephaestus.execution.orchestrator",
  "message": "Run abc123 queued (interactive)",
  "correlation_id": "corr_xyz",
  "run_id": "abc123"
}
```

### Prometheus Metrics

Available at `/api/metrics`:

- `heph_runs_total` — Total runs by status, mode, depth
- `heph_cost_usd_total` — Cumulative cost by provider
- `heph_stage_duration_seconds` — Pipeline stage latencies
- `heph_provider_latency_seconds` — Provider API latencies
- `heph_active_runs` — Current active run count
- `heph_queued_runs` — Current queue depth
- `heph_tool_denials_total` — Tool permission denials
- `heph_pantheon_reforge_total` — Reforge operations

### OTLP Tracing

Set `OTLP_ENDPOINT` to export traces to your collector (Jaeger, Tempo, etc.).
Traces cover: run lifecycle, stage transitions, provider calls, MCP interactions.
