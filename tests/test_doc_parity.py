"""Documentation parity tests — verify advertised capabilities match implementation."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

# Add project root to path for web module imports
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# -- Core modules importable --


def test_genesis_engine_importable():
    mod = importlib.import_module("hephaestus.core.genesis")
    assert hasattr(mod, "Genesis")


def test_depth_policy_importable():
    mod = importlib.import_module("hephaestus.core.depth_policy")
    assert hasattr(mod, "DepthPolicyTable")
    assert hasattr(mod, "get_depth_policy")


def test_adaptive_controller_importable():
    mod = importlib.import_module("hephaestus.core.adaptive_controller")
    assert hasattr(mod, "AdaptiveExplorationController")


def test_quality_gate_importable():
    mod = importlib.import_module("hephaestus.core.quality_gate")
    assert hasattr(mod, "QualityAssessment") or hasattr(mod, "assess_invention_quality")


# -- DeepForge modules --


def test_pressure_engine_importable():
    mod = importlib.import_module("hephaestus.deepforge.pressure")
    assert hasattr(mod, "AntiTrainingPressure")


# -- Pantheon modules --


def test_pantheon_coordinator_importable():
    mod = importlib.import_module("hephaestus.pantheon.coordinator")
    assert hasattr(mod, "PantheonCoordinator")


def test_pantheon_state_machine_importable():
    mod = importlib.import_module("hephaestus.pantheon.state_machine")
    assert hasattr(mod, "ObjectionLifecycleMachine")
    assert hasattr(mod, "CouncilPhaseMachine")


def test_pantheon_artifact_store_importable():
    mod = importlib.import_module("hephaestus.pantheon.artifact_store")
    assert hasattr(mod, "CouncilArtifactStore")


# -- Execution plane --


def test_run_store_importable():
    mod = importlib.import_module("hephaestus.execution.run_store")
    assert hasattr(mod, "RunStore")
    assert hasattr(mod, "PostgresRunStore")
    assert hasattr(mod, "SQLiteRunStore")


def test_orchestrator_importable():
    mod = importlib.import_module("hephaestus.execution.orchestrator")
    assert hasattr(mod, "RunOrchestrator")


def test_execution_models_importable():
    mod = importlib.import_module("hephaestus.execution.models")
    assert hasattr(mod, "RunRecord")
    assert hasattr(mod, "RunStatus")
    assert hasattr(mod, "ExecutionClass")


# -- Provider registry --


def test_provider_registry_importable():
    mod = importlib.import_module("hephaestus.providers")
    assert hasattr(mod, "ProviderRegistry")
    assert hasattr(mod, "build_default_registry")


def test_anthropic_provider_importable():
    mod = importlib.import_module("hephaestus.providers.anthropic")
    assert hasattr(mod, "AnthropicProvider")


def test_openai_provider_importable():
    mod = importlib.import_module("hephaestus.providers.openai_provider")
    assert hasattr(mod, "OpenAIProvider")


def test_embeddings_provider_importable():
    mod = importlib.import_module("hephaestus.providers.embeddings")
    assert hasattr(mod, "EmbeddingsProvider")


# -- Telemetry --


def test_telemetry_logging_importable():
    mod = importlib.import_module("hephaestus.telemetry.logging")
    assert hasattr(mod, "configure_logging")
    assert hasattr(mod, "set_correlation_id")


def test_telemetry_metrics_importable():
    mod = importlib.import_module("hephaestus.telemetry.metrics")
    assert hasattr(mod, "MetricsCollector")
    assert hasattr(mod, "get_metrics")


def test_telemetry_tracing_importable():
    mod = importlib.import_module("hephaestus.telemetry.tracing")
    assert hasattr(mod, "configure_tracing")
    assert hasattr(mod, "get_tracer")


def test_telemetry_cost_importable():
    mod = importlib.import_module("hephaestus.telemetry.cost")
    assert hasattr(mod, "CostGovernor")
    assert hasattr(mod, "BudgetPolicy")


def test_telemetry_events_importable():
    mod = importlib.import_module("hephaestus.telemetry.events")
    assert hasattr(mod, "EventBus")
    assert hasattr(mod, "get_event_bus")


# -- MCP --


def test_mcp_client_importable():
    mod = importlib.import_module("hephaestus.tools.mcp.client")
    assert hasattr(mod, "MCPClient")


def test_mcp_protocol_importable():
    mod = importlib.import_module("hephaestus.tools.mcp.protocol")
    assert hasattr(mod, "ProtocolEngine")


def test_mcp_trust_importable():
    mod = importlib.import_module("hephaestus.tools.mcp.trust")
    assert hasattr(mod, "MCPTrustPolicy")


def test_mcp_health_importable():
    mod = importlib.import_module("hephaestus.tools.mcp.health")
    assert hasattr(mod, "MCPHealthTracker")


# -- Research --


def test_research_source_trust_importable():
    mod = importlib.import_module("hephaestus.research.source_trust")
    assert hasattr(mod, "SourceTrustModel")


def test_research_ingestion_importable():
    mod = importlib.import_module("hephaestus.research.ingestion")
    assert hasattr(mod, "ingest_content")


def test_research_artifact_store_importable():
    mod = importlib.import_module("hephaestus.research.artifact_store")
    assert hasattr(mod, "ResearchArtifactStore")


# -- Depth policy table correctness --


def test_depth_policy_covers_all_depths():
    from hephaestus.core.depth_policy import get_depth_policy

    table = get_depth_policy()
    for depth in range(1, 11):
        budget = table.policy_for(depth, "standard")
        assert budget.search_candidates > 0
        assert budget.recomposition_ceiling >= 1

        forge_budget = table.policy_for(depth, "forge")
        assert forge_budget.translate_pressure_rounds >= 1  # Forge always has pressure


def test_depth_policy_clamping():
    from hephaestus.core.depth_policy import get_depth_policy

    table = get_depth_policy()
    # Should clamp without error
    b0 = table.policy_for(0, "standard")
    b1 = table.policy_for(1, "standard")
    b100 = table.policy_for(100, "standard")
    b10 = table.policy_for(10, "standard")
    assert b0 == b1  # 0 clamps to 1
    assert b100 == b10  # 100 clamps to 10


# -- State machine correctness --


def test_objection_valid_transitions():
    from hephaestus.pantheon.state_machine import ObjectionLifecycleMachine, PantheonStateError

    machine = ObjectionLifecycleMachine()
    # Valid
    machine.transition(
        objection_id="test-1",
        from_status="OPEN",
        to_status="RESOLVED",
        round_index=1,
        agent="test",
        reason="fixed",
    )
    # Invalid
    with pytest.raises(PantheonStateError):
        machine.transition(
            objection_id="test-2",
            from_status="RESOLVED",
            to_status="ESCALATED",
            round_index=2,
            agent="test",
        )


def test_council_phase_machine():
    from hephaestus.pantheon.state_machine import CouncilPhaseMachine

    machine = CouncilPhaseMachine()
    assert machine.current_phase == "PREPARE"
    machine.transition("SCREEN", round_index=0)
    machine.transition("INDEPENDENT_BALLOT", round_index=0)
    machine.transition("COUNCIL", round_index=1)
    # Skip to FINALIZE is valid
    machine.transition("FINALIZE", round_index=1)
    assert machine.is_final()


# -- Telemetry unit tests --


def test_metrics_prometheus_export():
    from hephaestus.telemetry.metrics import MetricsCollector

    m = MetricsCollector()
    m.inc("heph_runs_total", labels={"status": "completed"})
    m.inc("heph_runs_total", labels={"status": "completed"})
    m.inc("heph_runs_total", labels={"status": "failed"})
    output = m.export_prometheus()
    assert "heph_runs_total" in output
    assert 'status="completed"' in output


def test_structured_json_logging():
    import io
    import json
    import logging

    from hephaestus.telemetry.logging import configure_logging, set_correlation_id

    stream = io.StringIO()
    configure_logging(level="DEBUG", json_output=True, stream=stream)
    set_correlation_id("test-corr-123")
    test_logger = logging.getLogger("test.doc_parity")
    test_logger.info("test message")

    output = stream.getvalue()
    assert output.strip()
    record = json.loads(output.strip().split("\n")[-1])
    assert record["message"] == "test message"
    assert record["correlation_id"] == "test-corr-123"


def test_event_bus_dispatch():
    from hephaestus.telemetry.events import EventBus, EventType

    received = []
    bus = EventBus()
    bus.subscribe(lambda evt: received.append(evt))
    bus.emit_simple(EventType.RUN_STARTED, stage="test")
    assert len(received) == 1
    assert received[0].event_type == EventType.RUN_STARTED
