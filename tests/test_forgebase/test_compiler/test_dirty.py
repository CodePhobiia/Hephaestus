"""Tests for DirtyTracker — higher-level dirty marker upsert/consume logic."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hephaestus.forgebase.compiler.dirty import DirtyTracker
from hephaestus.forgebase.domain.enums import DirtyTargetKind
from hephaestus.forgebase.service.id_generator import DeterministicIdGenerator
from hephaestus.forgebase.store.sqlite.dirty_marker_repo import SqliteDirtyMarkerRepository

T0 = datetime(2026, 4, 3, 12, 0, 0, tzinfo=UTC)
T1 = datetime(2026, 4, 3, 13, 0, 0, tzinfo=UTC)
T2 = datetime(2026, 4, 3, 14, 0, 0, tzinfo=UTC)


def _make_tracker(
    sqlite_db,
    id_gen: DeterministicIdGenerator,
    start_time: datetime = T0,
) -> tuple[DirtyTracker, SqliteDirtyMarkerRepository]:
    """Create a DirtyTracker with a controllable clock."""
    repo = SqliteDirtyMarkerRepository(sqlite_db)
    current_time = [start_time]

    def clock_fn() -> datetime:
        return current_time[0]

    tracker = DirtyTracker(repo=repo, id_generator=id_gen, clock_fn=clock_fn)
    # Expose the mutable time for tests to advance
    tracker._test_time = current_time  # type: ignore[attr-defined]
    return tracker, repo


@pytest.mark.asyncio
class TestDirtyTracker:
    async def test_mark_dirty_creates_new_marker(self, sqlite_db, id_gen):
        tracker, repo = _make_tracker(sqlite_db, id_gen)
        vault_id = id_gen.vault_id()
        source_id = id_gen.source_id()
        job_id = id_gen.job_id()

        marker = await tracker.mark_dirty(
            vault_id=vault_id,
            target_kind=DirtyTargetKind.CONCEPT,
            target_key="solid electrolyte interphase",
            dirtied_by_source=source_id,
            dirtied_by_job=job_id,
        )
        await sqlite_db.commit()

        assert marker.vault_id == vault_id
        assert marker.target_kind == DirtyTargetKind.CONCEPT
        assert marker.target_key == "solid electrolyte interphase"
        assert marker.times_dirtied == 1
        assert marker.first_dirtied_at == T0
        assert marker.last_dirtied_at == T0
        assert marker.last_dirtied_by_source == source_id
        assert marker.last_dirtied_by_job == job_id
        assert marker.consumed_by_job is None
        assert marker.consumed_at is None

        # Verify it's persisted
        got = await repo.get(marker.marker_id)
        assert got is not None
        assert got.target_key == "solid electrolyte interphase"

    async def test_mark_dirty_upsert_preserves_first_dirtied_at(self, sqlite_db, id_gen):
        tracker, repo = _make_tracker(sqlite_db, id_gen)
        vault_id = id_gen.vault_id()

        m1 = await tracker.mark_dirty(
            vault_id=vault_id,
            target_kind=DirtyTargetKind.CONCEPT,
            target_key="sei",
            dirtied_by_source=id_gen.source_id(),
            dirtied_by_job=id_gen.job_id(),
        )
        await sqlite_db.commit()

        # Advance the clock
        tracker._test_time[0] = T1  # type: ignore[attr-defined]

        m2 = await tracker.mark_dirty(
            vault_id=vault_id,
            target_kind=DirtyTargetKind.CONCEPT,
            target_key="sei",
            dirtied_by_source=id_gen.source_id(),
            dirtied_by_job=id_gen.job_id(),
        )
        await sqlite_db.commit()

        # first_dirtied_at must be preserved from original marker
        assert m2.first_dirtied_at == T0
        assert m2.last_dirtied_at == T1

        # Verify in the database
        got = await repo.find_by_target(vault_id, DirtyTargetKind.CONCEPT, "sei")
        assert got is not None
        assert got.first_dirtied_at == T0
        assert got.last_dirtied_at == T1

    async def test_mark_dirty_upsert_increments_times_dirtied(self, sqlite_db, id_gen):
        tracker, repo = _make_tracker(sqlite_db, id_gen)
        vault_id = id_gen.vault_id()

        m1 = await tracker.mark_dirty(
            vault_id=vault_id,
            target_kind=DirtyTargetKind.MECHANISM,
            target_key="photosynthesis",
            dirtied_by_source=id_gen.source_id(),
            dirtied_by_job=id_gen.job_id(),
        )
        await sqlite_db.commit()
        assert m1.times_dirtied == 1

        # Dirty again
        tracker._test_time[0] = T1  # type: ignore[attr-defined]
        m2 = await tracker.mark_dirty(
            vault_id=vault_id,
            target_kind=DirtyTargetKind.MECHANISM,
            target_key="photosynthesis",
            dirtied_by_source=id_gen.source_id(),
            dirtied_by_job=id_gen.job_id(),
        )
        await sqlite_db.commit()
        assert m2.times_dirtied == 2

        # Dirty a third time
        tracker._test_time[0] = T2  # type: ignore[attr-defined]
        m3 = await tracker.mark_dirty(
            vault_id=vault_id,
            target_kind=DirtyTargetKind.MECHANISM,
            target_key="photosynthesis",
            dirtied_by_source=id_gen.source_id(),
            dirtied_by_job=id_gen.job_id(),
        )
        await sqlite_db.commit()
        assert m3.times_dirtied == 3

        # Verify in the database
        got = await repo.find_by_target(vault_id, DirtyTargetKind.MECHANISM, "photosynthesis")
        assert got is not None
        assert got.times_dirtied == 3

    async def test_get_dirty_targets_filters_by_kind(self, sqlite_db, id_gen):
        tracker, repo = _make_tracker(sqlite_db, id_gen)
        vault_id = id_gen.vault_id()

        # Create markers of different kinds
        await tracker.mark_dirty(
            vault_id=vault_id,
            target_kind=DirtyTargetKind.CONCEPT,
            target_key="alpha",
            dirtied_by_source=id_gen.source_id(),
            dirtied_by_job=id_gen.job_id(),
        )
        await tracker.mark_dirty(
            vault_id=vault_id,
            target_kind=DirtyTargetKind.MECHANISM,
            target_key="beta",
            dirtied_by_source=id_gen.source_id(),
            dirtied_by_job=id_gen.job_id(),
        )
        await tracker.mark_dirty(
            vault_id=vault_id,
            target_kind=DirtyTargetKind.CONCEPT,
            target_key="gamma",
            dirtied_by_source=id_gen.source_id(),
            dirtied_by_job=id_gen.job_id(),
        )
        await sqlite_db.commit()

        # Filter by CONCEPT
        concepts = await tracker.get_dirty_targets(
            vault_id,
            target_kind=DirtyTargetKind.CONCEPT,
        )
        assert len(concepts) == 2
        keys = {m.target_key for m in concepts}
        assert keys == {"alpha", "gamma"}

        # Filter by MECHANISM
        mechanisms = await tracker.get_dirty_targets(
            vault_id,
            target_kind=DirtyTargetKind.MECHANISM,
        )
        assert len(mechanisms) == 1
        assert mechanisms[0].target_key == "beta"

        # No filter — all three
        all_markers = await tracker.get_dirty_targets(vault_id)
        assert len(all_markers) == 3

    async def test_get_dirty_targets_excludes_consumed(self, sqlite_db, id_gen):
        tracker, repo = _make_tracker(sqlite_db, id_gen)
        vault_id = id_gen.vault_id()

        m1 = await tracker.mark_dirty(
            vault_id=vault_id,
            target_kind=DirtyTargetKind.CONCEPT,
            target_key="a",
            dirtied_by_source=id_gen.source_id(),
            dirtied_by_job=id_gen.job_id(),
        )
        m2 = await tracker.mark_dirty(
            vault_id=vault_id,
            target_kind=DirtyTargetKind.CONCEPT,
            target_key="b",
            dirtied_by_source=id_gen.source_id(),
            dirtied_by_job=id_gen.job_id(),
        )
        await sqlite_db.commit()

        # Consume m1
        consume_job = id_gen.job_id()
        await tracker.consume(m1.marker_id, consume_job)
        await sqlite_db.commit()

        targets = await tracker.get_dirty_targets(vault_id)
        assert len(targets) == 1
        assert targets[0].marker_id == m2.marker_id

    async def test_consume_marks_consumed(self, sqlite_db, id_gen):
        tracker, repo = _make_tracker(sqlite_db, id_gen)
        vault_id = id_gen.vault_id()

        m = await tracker.mark_dirty(
            vault_id=vault_id,
            target_kind=DirtyTargetKind.CONCEPT,
            target_key="test-concept",
            dirtied_by_source=id_gen.source_id(),
            dirtied_by_job=id_gen.job_id(),
        )
        await sqlite_db.commit()

        consume_job = id_gen.job_id()
        await tracker.consume(m.marker_id, consume_job)
        await sqlite_db.commit()

        got = await repo.get(m.marker_id)
        assert got is not None
        assert got.consumed_by_job == consume_job
        assert got.consumed_at is not None

    async def test_count_dirty(self, sqlite_db, id_gen):
        tracker, repo = _make_tracker(sqlite_db, id_gen)
        vault_id = id_gen.vault_id()

        assert await tracker.count_dirty(vault_id) == 0

        await tracker.mark_dirty(
            vault_id=vault_id,
            target_kind=DirtyTargetKind.CONCEPT,
            target_key="a",
            dirtied_by_source=id_gen.source_id(),
            dirtied_by_job=id_gen.job_id(),
        )
        await tracker.mark_dirty(
            vault_id=vault_id,
            target_kind=DirtyTargetKind.MECHANISM,
            target_key="b",
            dirtied_by_source=id_gen.source_id(),
            dirtied_by_job=id_gen.job_id(),
        )
        m3 = await tracker.mark_dirty(
            vault_id=vault_id,
            target_kind=DirtyTargetKind.CONCEPT,
            target_key="c",
            dirtied_by_source=id_gen.source_id(),
            dirtied_by_job=id_gen.job_id(),
        )
        await sqlite_db.commit()

        assert await tracker.count_dirty(vault_id) == 3

        # Consume one
        await tracker.consume(m3.marker_id, id_gen.job_id())
        await sqlite_db.commit()

        assert await tracker.count_dirty(vault_id) == 2

    async def test_should_trigger_synthesis_below_threshold(self, sqlite_db, id_gen):
        tracker, repo = _make_tracker(sqlite_db, id_gen)
        vault_id = id_gen.vault_id()

        # No markers — below threshold
        assert await tracker.should_trigger_synthesis(vault_id, threshold=3) is False

        # Add 2 markers — still below threshold of 3
        await tracker.mark_dirty(
            vault_id=vault_id,
            target_kind=DirtyTargetKind.CONCEPT,
            target_key="a",
            dirtied_by_source=id_gen.source_id(),
            dirtied_by_job=id_gen.job_id(),
        )
        await tracker.mark_dirty(
            vault_id=vault_id,
            target_kind=DirtyTargetKind.CONCEPT,
            target_key="b",
            dirtied_by_source=id_gen.source_id(),
            dirtied_by_job=id_gen.job_id(),
        )
        await sqlite_db.commit()

        assert await tracker.should_trigger_synthesis(vault_id, threshold=3) is False

    async def test_should_trigger_synthesis_at_threshold(self, sqlite_db, id_gen):
        tracker, repo = _make_tracker(sqlite_db, id_gen)
        vault_id = id_gen.vault_id()

        # Add exactly threshold markers
        for i in range(3):
            await tracker.mark_dirty(
                vault_id=vault_id,
                target_kind=DirtyTargetKind.CONCEPT,
                target_key=f"concept-{i}",
                dirtied_by_source=id_gen.source_id(),
                dirtied_by_job=id_gen.job_id(),
            )
        await sqlite_db.commit()

        assert await tracker.should_trigger_synthesis(vault_id, threshold=3) is True

        # Also test above threshold
        await tracker.mark_dirty(
            vault_id=vault_id,
            target_kind=DirtyTargetKind.MECHANISM,
            target_key="extra",
            dirtied_by_source=id_gen.source_id(),
            dirtied_by_job=id_gen.job_id(),
        )
        await sqlite_db.commit()

        assert await tracker.should_trigger_synthesis(vault_id, threshold=3) is True
