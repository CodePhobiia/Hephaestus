"""Generate capability manifest — compares advertised features vs actual implementation."""

from __future__ import annotations

import importlib
import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Add project root to path for web module imports
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger(__name__)


@dataclass
class Capability:
    """A single advertised capability."""
    name: str
    module: str
    class_or_function: str = ""
    description: str = ""
    implemented: bool = False
    importable: bool = False
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "module": self.module,
            "class_or_function": self.class_or_function,
            "description": self.description,
            "implemented": self.implemented,
            "importable": self.importable,
            "notes": self.notes,
        }


# Canonical capability registry — every advertised feature is listed here
CAPABILITIES: list[Capability] = [
    Capability(
        name="Genesis Invention Pipeline",
        module="hephaestus.core.genesis",
        class_or_function="Genesis",
        description="End-to-end invention pipeline: decompose → search → translate → recompose",
    ),
    Capability(
        name="DeepForge Anti-Training Pressure",
        module="hephaestus.deepforge.pressure",
        class_or_function="AntiTrainingPressure",
        description="Multi-round adversarial pressure to force novel generation",
    ),
    Capability(
        name="Pantheon Council Adjudication",
        module="hephaestus.pantheon.coordinator",
        class_or_function="PantheonCoordinator",
        description="Three-agent council (Athena, Hermes, Apollo) for quality adjudication",
    ),
    Capability(
        name="Depth Policy Table",
        module="hephaestus.core.depth_policy",
        class_or_function="DepthPolicyTable",
        description="Codified depth→budget mapping for exploration control",
    ),
    Capability(
        name="Adaptive Exploration Controller",
        module="hephaestus.core.adaptive_controller",
        class_or_function="AdaptiveExplorationController",
        description="Mid-run parameter adjustment based on health signals",
    ),
    Capability(
        name="Perplexity Research Integration",
        module="hephaestus.research.perplexity",
        class_or_function="PerplexityClient",
        description="Research grounding via Perplexity API",
    ),
    Capability(
        name="Source Trust Model",
        module="hephaestus.research.source_trust",
        class_or_function="SourceTrustModel",
        description="Domain-based citation quality scoring",
    ),
    Capability(
        name="Research Artifact Store",
        module="hephaestus.research.artifact_store",
        class_or_function="ResearchArtifactStore",
        description="Persistent storage for research artifacts linked to runs",
    ),
    Capability(
        name="MCP Tool Integration",
        module="hephaestus.tools.mcp.client",
        class_or_function="MCPClient",
        description="JSON-RPC 2.0 MCP server communication",
    ),
    Capability(
        name="MCP Trust Policy",
        module="hephaestus.tools.mcp.trust",
        class_or_function="MCPTrustPolicy",
        description="Per-server tool permission enforcement",
    ),
    Capability(
        name="MCP Health Tracking",
        module="hephaestus.tools.mcp.health",
        class_or_function="MCPHealthTracker",
        description="Circuit breaker and health monitoring for MCP servers",
    ),
    Capability(
        name="Durable Run Store (Postgres)",
        module="hephaestus.execution.run_store",
        class_or_function="PostgresRunStore",
        description="Persistent run lifecycle storage backed by PostgreSQL",
    ),
    Capability(
        name="Run Orchestrator",
        module="hephaestus.execution.orchestrator",
        class_or_function="RunOrchestrator",
        description="Admission control, concurrency pools, lifecycle management",
    ),
    Capability(
        name="Provider Registry",
        module="hephaestus.providers",
        class_or_function="ProviderRegistry",
        description="Lazy-loaded provider discovery and capability routing",
    ),
    Capability(
        name="Structured JSON Logging",
        module="hephaestus.telemetry.logging",
        class_or_function="configure_logging",
        description="stdlib logging with JSON output and correlation IDs",
    ),
    Capability(
        name="Prometheus Metrics",
        module="hephaestus.telemetry.metrics",
        class_or_function="MetricsCollector",
        description="In-process metrics with Prometheus text exposition",
    ),
    Capability(
        name="OTLP Tracing",
        module="hephaestus.telemetry.tracing",
        class_or_function="configure_tracing",
        description="OpenTelemetry distributed tracing with no-op fallback",
    ),
    Capability(
        name="Cost Governance",
        module="hephaestus.telemetry.cost",
        class_or_function="CostGovernor",
        description="Pre-flight and mid-flight spend controls",
    ),
    Capability(
        name="Pantheon State Machine",
        module="hephaestus.pantheon.state_machine",
        class_or_function="ObjectionLifecycleMachine",
        description="Authoritative state transitions with audit trail",
    ),
    Capability(
        name="Council Artifact Store",
        module="hephaestus.pantheon.artifact_store",
        class_or_function="CouncilArtifactStore",
        description="Deliberation persistence and decision explainability",
    ),
    Capability(
        name="Web UI",
        module="web.app",
        class_or_function="app",
        description="FastAPI web interface with run lifecycle management",
    ),
    Capability(
        name="CLI Interface",
        module="hephaestus.cli.main",
        class_or_function="main",
        description="Click-based CLI for local invocations",
    ),
]


def verify_capabilities() -> list[Capability]:
    """Verify all capabilities by attempting to import them."""
    results = []
    for cap in CAPABILITIES:
        cap_copy = Capability(**cap.to_dict())
        try:
            mod = importlib.import_module(cap.module)
            cap_copy.importable = True
            if cap.class_or_function:
                if hasattr(mod, cap.class_or_function):
                    cap_copy.implemented = True
                else:
                    cap_copy.notes = f"{cap.class_or_function} not found in {cap.module}"
            else:
                cap_copy.implemented = True
        except ImportError as exc:
            cap_copy.importable = False
            cap_copy.notes = str(exc)
        except Exception as exc:
            cap_copy.notes = f"Import error: {exc}"
        results.append(cap_copy)
    return results


def generate_manifest() -> dict[str, Any]:
    """Generate the full capability manifest."""
    results = verify_capabilities()
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "total_capabilities": len(results),
        "implemented": sum(1 for r in results if r.implemented),
        "importable": sum(1 for r in results if r.importable),
        "missing": [r.to_dict() for r in results if not r.implemented],
        "all": [r.to_dict() for r in results],
    }


def main() -> None:
    """CLI entry point."""
    manifest = generate_manifest()
    print(json.dumps(manifest, indent=2, ensure_ascii=False))

    missing = manifest["missing"]
    if missing:
        print(f"\n⚠ {len(missing)} capabilities not verified:", file=sys.stderr)
        for m in missing:
            print(f"  ✗ {m['name']}: {m['notes']}", file=sys.stderr)
        sys.exit(1)
    else:
        print(f"\n✓ All {manifest['total_capabilities']} capabilities verified", file=sys.stderr)


if __name__ == "__main__":
    main()
