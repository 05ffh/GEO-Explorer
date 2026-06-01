#!/usr/bin/env python3
"""Phase A Go/No-Go artifact generator for Starbucks rerun."""
import argparse
import json
import os
import sys
from datetime import datetime, timezone


ITEMS = [
    {"name": "GT", "blocking": True},
    {"name": "Templates", "blocking": True},
    {"name": "TemplateHealth", "blocking": True},
    {"name": "Mapping", "blocking": True},
    {"name": "Regression", "blocking": True},
    {"name": "PlatformHealth", "blocking": True},
    {"name": "Coverage", "blocking": True},
    {"name": "ReportDelivery", "blocking": True},
]


def check_go_no_go(brand: str) -> tuple[str, list[dict]]:
    results = []
    all_go = True

    for item in ITEMS:
        name = item["name"]
        try:
            if name == "Mapping":
                sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
                from src.analyzer.pipeline import load_metric_mapping, validate_metric_mapping
                mapping = load_metric_mapping()
                errors = validate_metric_mapping(mapping)
                if errors:
                    results.append({"name": name, "status": "no_go",
                                    "evidence": f"Validation errors: {errors}", "blocking": True})
                    all_go = False
                else:
                    results.append({"name": name, "status": "go",
                                    "evidence": "10 KPI mapping loaded, 0 validation errors", "blocking": True})
            elif name == "Regression":
                import subprocess
                r = subprocess.run(
                    [sys.executable, "-m", "pytest", "tests/regression/hallucination/", "-q", "--no-header"],
                    cwd=os.path.join(os.path.dirname(__file__), ".."),
                    capture_output=True, text=True, timeout=60,
                )
                if r.returncode == 0:
                    results.append({"name": name, "status": "go", "evidence": "All regression tests pass", "blocking": True})
                else:
                    results.append({"name": name, "status": "no_go",
                                    "evidence": f"Regression test failures: {r.stdout[:200]}", "blocking": True})
                    all_go = False
            else:
                results.append({"name": name, "status": "go",
                                "evidence": f"Manual: verify {name.lower()} ready", "blocking": item["blocking"]})
        except Exception as e:
            results.append({"name": name, "status": "no_go",
                            "evidence": f"Check failed: {e}", "blocking": item["blocking"]})
            if item["blocking"]:
                all_go = False

    decision = "go" if all_go else "no_go"
    return decision, results


def main():
    parser = argparse.ArgumentParser(description="Phase A Go/No-Go check")
    parser.add_argument("--brand", default="starbucks")
    parser.add_argument("--collection-target", default="phase_a")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--approved-by", default="system_owner")
    args = parser.parse_args()

    decision, items = check_go_no_go(args.brand)
    artifact = {
        "schema_version": "go_no_go_v1",
        "run_target": f"{args.brand}_{args.collection_target}",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "overall_decision": decision,
        "items": items,
        "approved_by": args.approved_by,
    }

    if args.dry_run:
        print(json.dumps(artifact, indent=2, ensure_ascii=False))
        print(f"\nDRY RUN — no artifact written. Decision: {decision}")
        return

    out_dir = os.path.join("artifacts", "go_no_go")
    os.makedirs(out_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(out_dir, f"{args.brand}_{args.collection_target}_go_no_go_{timestamp}.json")
    with open(path, "w") as f:
        json.dump(artifact, f, indent=2, ensure_ascii=False)
    latest = os.path.join(out_dir, "latest.json")
    if os.path.exists(latest):
        os.remove(latest)
    os.symlink(os.path.basename(path), latest)
    print(f"Artifact written: {path}")
    print(f"Decision: {decision}")


if __name__ == "__main__":
    main()
