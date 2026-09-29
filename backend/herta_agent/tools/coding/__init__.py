from herta_agent.tools.coding.apply_patch import apply_patch
from herta_agent.tools.coding.grep_code import grep_code
from herta_agent.tools.coding.list_directory import list_directory
from herta_agent.tools.coding.plan import propose_plan
from herta_agent.tools.coding.read_file import read_file
from herta_agent.tools.coding.run_tests import run_tests
from herta_agent.tools.registry import ToolRegistry


def coding_registry(repo, *, writable=False):
    registry = ToolRegistry()
    for spec in (read_file(repo), list_directory(repo), grep_code(repo), propose_plan()):
        registry.register(spec)
    if writable:
        registry.register(apply_patch(repo))
        registry.register(run_tests(repo))
    return registry
