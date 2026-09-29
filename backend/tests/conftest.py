"""Keep original unittest bodies intact; report execution-environment gaps explicitly."""

import os

import pytest

LEGACY_HOST_TESTS = {
    "test_coding_tools_write.py::WriteToolsTests::test_real_failed_and_passed_counts_and_details",
    "test_coding_tools_write.py::WriteToolsTests::test_subtest_counts_do_not_become_negative",
    "test_coding_tools_write.py::WriteToolsTests::test_timeout_and_cancel_reap_test_process",
}


def pytest_collection_modifyitems(items):
    docker_enabled = os.environ.get("HERTA_DOCKER_TESTS") == "1"
    inside = os.environ.get("HERTA_SANDBOX") == "1"
    for item in items:
        node = item.nodeid.replace("\\", "/")
        suffix = node.split("/")[-1]
        if suffix in LEGACY_HOST_TESTS:
            item.add_marker(
                pytest.mark.skip(
                    reason=(
                        "legacy local PID/2s contract; replaced by "
                        "integration/test_docker_sandbox.py "
                        "(real Docker required, separately reported)"
                    )
                )
            )
        requires_docker = (
            "test_coding_evals.py::" in node
            or (
                "test_pytest_runner.py::PytestRunnerTests::" in node
                and not node.endswith("test_missing_path_is_an_explicit_error")
            )
            or "/integration/test_docker_sandbox.py::" in node
        )
        if requires_docker:
            item.add_marker(pytest.mark.docker)
            if inside or not docker_enabled:
                item.add_marker(
                    pytest.mark.skip(
                        reason=(
                            "host-driven Docker integration; set HERTA_DOCKER_TESTS=1 on host, "
                            "never expose Docker socket inside sandbox"
                        )
                    )
                )
