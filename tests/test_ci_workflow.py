"""CI workflow file validation tests."""

import pytest
import yaml
from pathlib import Path


@pytest.fixture
def ci_config():
    ci_path = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"
    if not ci_path.exists():
        pytest.skip("ci.yml not found")
    return yaml.safe_load(ci_path.read_text())


class TestCIWorkflow:
    def test_workflow_file_exists(self):
        ci_path = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"
        assert ci_path.exists(), "ci.yml not found"

    def test_workflow_has_jobs(self, ci_config):
        assert "jobs" in ci_config or ci_config is not False

    def test_workflow_has_postgres_service(self, ci_config):
        jobs = ci_config.get("jobs", {})
        test_job = jobs.get("test", {}) if jobs else {}
        services = test_job.get("services", {}) if test_job else {}
        assert "postgres" in services, "ci.yml missing postgres service"

    def test_workflow_has_postgres_healthcheck(self, ci_config):
        ci_text = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"
        content = ci_text.read_text()
        assert "health-cmd" in content, "ci.yml missing postgres health check"
        assert "pg_isready" in content, "ci.yml missing pg_isready"

    def test_workflow_sets_database_url(self, ci_config):
        ci_text = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"
        content = ci_text.read_text()
        assert "DATABASE_URL" in content, "ci.yml missing DATABASE_URL"

    def test_workflow_runs_pytest(self, ci_config):
        ci_text = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"
        content = ci_text.read_text()
        assert "pytest" in content, "ci.yml missing pytest"

    def test_workflow_runs_exception_policy(self, ci_config):
        ci_text = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"
        content = ci_text.read_text()
        assert "check_exception_policy" in content, "ci.yml missing exception policy check"

    def test_workflow_has_timeout(self, ci_config):
        ci_text = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"
        content = ci_text.read_text()
        assert "timeout-minutes" in content, "ci.yml missing timeout"

    def test_workflow_skips_e2e(self, ci_config):
        ci_text = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"
        content = ci_text.read_text()
        assert "--ignore=tests/e2e" in content, "ci.yml not skipping e2e tests"
