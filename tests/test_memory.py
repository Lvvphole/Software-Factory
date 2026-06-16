import tempfile, os
from memory import persist_run, fetch_run, count_runs


def test_persist_and_fetch(tmp_path):
    db = tmp_path / "f.db"
    record = {"run_id": "r1", "signal_id": "s1", "plan_id": "p1",
              "started_at": "2026-06-15T00:00:00Z", "completed_at": "2026-06-15T00:00:01Z",
              "verifier_decision": "pass"}
    persist_run(record, db_path=db)
    assert count_runs(db_path=db) == 1
    got = fetch_run("r1", db_path=db)
    assert got["run_id"] == "r1"
    assert got["verifier_decision"] == "pass"
