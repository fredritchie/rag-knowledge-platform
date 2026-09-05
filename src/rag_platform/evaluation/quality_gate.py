from __future__ import annotations

import math
from typing import Any


def evaluate_quality_gate(
    retrieval_report: dict[str, Any],
    rag_report: dict[str, Any],
    baseline: dict[str, Any],
) -> dict[str, Any]:
    """Compare evaluation reports with versioned baselines and absolute tolerances."""
    reports = {"retrieval": retrieval_report, "rag": rag_report}
    results: dict[str, dict[str, Any]] = {}
    failures: list[str] = []

    minimum_cases = int(baseline.get("minimum_cases", 1))
    for report_name, report in reports.items():
        cases = int(report.get("cases", 0))
        if cases < minimum_cases:
            failures.append(
                f"{report_name}.cases={cases} is below required minimum {minimum_cases}"
            )

    for metric, policy in baseline["metrics"].items():
        report_name = str(policy["report"])
        baseline_value = float(policy["baseline"])
        tolerance = float(policy.get("tolerance", 0.0))
        if report_name not in reports:
            raise ValueError(f"Unknown quality-gate report: {report_name}")
        observed = float(reports[report_name].get(metric, float("nan")))
        minimum = baseline_value - tolerance
        passed = math.isfinite(observed) and observed >= minimum
        results[metric] = {
            "report": report_name,
            "observed": observed,
            "baseline": baseline_value,
            "tolerance": tolerance,
            "minimum": minimum,
            "passed": passed,
        }
        if not passed:
            failures.append(f"{metric}={observed:.4f} is below required minimum {minimum:.4f}")

    return {"passed": not failures, "metrics": results, "failures": failures}
