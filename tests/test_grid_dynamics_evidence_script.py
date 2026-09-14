from __future__ import annotations

import json
import sys

from scripts import run_grid_dynamics_evidence


def test_evidence_script_generates_report_plots_and_machine_readable_results(
    tmp_path, monkeypatch
):
    output = tmp_path / "dynamics-evidence"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_grid_dynamics_evidence.py",
            "--schedule-evidence",
            "evidence/gridtwin/results.json",
            "--output",
            str(output),
        ],
    )

    assert run_grid_dynamics_evidence.main() == 0
    result = json.loads((output / "results.json").read_text(encoding="utf-8"))
    report = (output / "technical-report.md").read_text(encoding="utf-8")

    assert result["minimum_evidence_gate"]["passed"] is True
    assert set(result["scenarios"]) == {
        "normal_load_change",
        "voltage_sag",
        "three_phase_fault",
        "inverter_trip",
    }
    assert result["schedule_feedback"]["workflow_action"] == "request_reschedule"
    assert "not switching-level EMT" in report
    assert "## Reproduce" in report
    assert (output / "dynamic-responses.svg").read_text(encoding="utf-8").startswith(
        "<?xml"
    )
    assert (output / "step-sensitivity.svg").is_file()
