"""End-to-end run on the mock executor — preserves v1 contract that the
sample-signal flow stays CI-safe with no API key, no target_repo."""
from pathlib import Path
from workflows import run_factory, REQUIRED_ARTIFACTS


def test_end_to_end_creates_all_artifacts(tmp_path, monkeypatch):
    monkeypatch.setenv("FACTORY_DB_PATH", str(tmp_path / "mem.db"))
    runs_root = tmp_path / "runs"
    result = run_factory("examples/sample-signal.json", runs_root=str(runs_root))
    run_dir = Path(result["run_dir"])
    for name in REQUIRED_ARTIFACTS:
        assert (run_dir / name).exists(), f"missing artifact: {name}"
    assert result["verifier"]["decision"] in ("pass", "fail")
    assert result["verifier"]["executor"] == "mock"
    assert result["verifier"]["grading_mode"] == "artifact"


def test_verifier_ignores_coding_self_assessment(tmp_path, monkeypatch):
    monkeypatch.setenv("FACTORY_DB_PATH", str(tmp_path / "mem.db"))
    result = run_factory("examples/sample-signal.json",
                         runs_root=str(tmp_path / "runs"))
    import json
    vr = json.loads((Path(result["run_dir"]) / "verifier-report.json").read_text())
    assert "self-assessment is ignored" in vr["notes"]
