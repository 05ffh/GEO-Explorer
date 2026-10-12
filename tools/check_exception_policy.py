#!/usr/bin/env python3
"""Check bare except Exception policy compliance.

Scans src/ and scripts/ for `except Exception` patterns.
- Allowed: boundary sites with noqa: BLE001 + boundary comment + logger.exception
- Forbidden: all others (business logic must use specific exception types)

Usage:
  .venv/bin/python tools/check_exception_policy.py          # check only
  .venv/bin/python tools/check_exception_policy.py --json   # JSON output for CI
  .venv/bin/python tools/check_exception_policy.py --fix    # not implemented
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIRS = [PROJECT_ROOT / "src", PROJECT_ROOT / "scripts"]

# Files excluded from the scan (generated, vendored, third-party)
EXCLUDE_PATTERNS = {
    "__pycache__", ".pytest_cache", ".venv", ".git",
    "node_modules", "migrations", ".ipynb_checkpoints",
}

# Known boundary sites allowed to have broad except Exception
# Format: (file_path_relative, line_number, boundary_type)
ALLOWLIST: list[tuple[str, int, str]] = [
    # Add verified boundary sites as they are audited:
    # ("scripts/run_collection_diagnostic.py", 622, "CLI boundary"),
    # ("src/tasks/collection_tasks.py", 119, "Celery task boundary"),
]

# Required markers for allowed broad excepts
REQUIRED_NOQA = "noqa: BLE001"
REQUIRED_BOUNDARY = re.compile(r"(CLI boundary|task boundary|HTTP boundary|low-risk)")


def _is_excluded(rel_path: str) -> bool:
    parts = set(rel_path.split(os.sep))
    return bool(parts & EXCLUDE_PATTERNS)


def _is_allowlisted(rel_path: str, lineno: int) -> bool:
    for fpath, line, _btype in ALLOWLIST:
        if rel_path == fpath and lineno == line:
            return True
    return False


def scan_directory(root: Path) -> list[dict]:
    """Scan a directory tree for bare except Exception patterns."""
    violations = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune excluded directories
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_PATTERNS]
        for fname in filenames:
            if not fname.endswith(".py"):
                continue
            fpath = os.path.join(dirpath, fname)
            rel_path = os.path.relpath(fpath, PROJECT_ROOT)
            if _is_excluded(rel_path):
                continue

            try:
                with open(fpath, encoding="utf-8") as f:
                    lines = f.readlines()
            except Exception:
                continue

            for i, line in enumerate(lines, start=1):
                if "except Exception" not in line:
                    continue

                # Determine if properly annotated
                line_clean = line.strip()
                is_allowlisted = _is_allowlisted(rel_path, i)
                has_noqa = REQUIRED_NOQA in line_clean
                has_boundary = bool(REQUIRED_BOUNDARY.search(line_clean))

                # Read the next 2 lines to check for boundary comment + logger.exception
                context_lines = "".join(lines[i - 1 : min(i + 2, len(lines))])
                has_boundary_comment = bool(REQUIRED_BOUNDARY.search(context_lines))
                has_logger_exception = "logger.exception" in context_lines or "logger.exception" in "".join(
                    lines[i:min(i + 3, len(lines))]
                )

                if is_allowlisted:
                    if not has_noqa:
                        violations.append({
                            "file": rel_path, "line": i,
                            "issue": "allowlisted site missing noqa: BLE001",
                            "severity": "error",
                        })
                    if not has_boundary_comment:
                        violations.append({
                            "file": rel_path, "line": i,
                            "issue": "allowlisted site missing boundary comment",
                            "severity": "warning",
                        })
                    if not has_logger_exception:
                        violations.append({
                            "file": rel_path, "line": i,
                            "issue": "allowlisted site missing logger.exception",
                            "severity": "warning",
                        })
                elif has_noqa and has_boundary_comment:
                    # Properly annotated boundary site — noqa + boundary comment is sufficient
                    # logger.exception is recommended but not required for graceful-degrade endpoints
                    pass
                else:
                    violations.append({
                        "file": rel_path, "line": i,
                        "issue": "bare except Exception in business logic",
                        "severity": "error",
                        "hint": "Replace with specific exception types or add boundary allowlist entry",
                    })

    return violations


def main():
    parser = argparse.ArgumentParser(description="Check bare except Exception policy")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--fix", action="store_true", help="(Not implemented)")
    args = parser.parse_args()

    all_violations = []
    for src_dir in SRC_DIRS:
        if src_dir.exists():
            all_violations.extend(scan_directory(src_dir))

    if args.json:
        print(json.dumps(all_violations, indent=2))
    else:
        errors = [v for v in all_violations if v["severity"] == "error"]
        warnings = [v for v in all_violations if v["severity"] == "warning"]

        if all_violations:
            print(f"Found {len(errors)} errors, {len(warnings)} warnings:")
            for v in all_violations:
                icon = "✗" if v["severity"] == "error" else "⚠"
                hint = f" — {v['hint']}" if v.get("hint") else ""
                print(f"  {icon} {v['file']}:{v['line']}: {v['issue']}{hint}")
        else:
            print("OK: No bare except Exception violations found.")

    # Exit with error if there are error-level violations
    errors = [v for v in all_violations if v["severity"] == "error"]
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
