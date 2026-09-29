"""Manual evaluation helper using containerized pytest. NOT model scores."""

import argparse
import asyncio
import json
import shutil
import tempfile
from pathlib import Path

from herta_agent.runtime.messages import ToolCall
from herta_agent.tools.coding import coding_registry
from herta_agent.tools.coding.workspace import Workspace
from herta_agent.tools.executor import ToolExecutor


def prepare(case, output):
    destination = output / case.name
    if destination.exists():
        raise ValueError("Output already exists; choose a new directory.")
    shutil.copytree(case / "src", destination)
    return destination


async def invoke(workspace, name, **args):
    result = await ToolExecutor(coding_registry(workspace, writable=True)).execute(
        ToolCall(id="evaluation", name=name, arguments=json.dumps(args))
    )
    if not result.ok:
        raise RuntimeError(f"{result.error.code}: {result.error.message}")
    return result.data


async def verify_fixture(case, output):
    source = prepare(case, output)
    workspace = Workspace.open(source)
    before = await invoke(workspace, "run_tests")
    await invoke(workspace, "apply_patch", patch=(case / "fix.patch").read_text(encoding="utf-8"))
    after = await invoke(workspace, "run_tests")
    return {"case": case.name, "before": before, "after": after, "reference_only": True}


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--diagnosis", type=Path, help="Human-recorded model diagnosis JSON")
    parser.add_argument(
        "--patch", type=Path, help="Model repair unified diff, not the reference patch"
    )
    parser.add_argument("--verify-fixtures", action="store_true")
    args = parser.parse_args()
    if args.verify_fixtures:
        with tempfile.TemporaryDirectory() as folder:
            results = [
                await verify_fixture(case, Path(folder))
                for case in sorted((Path(__file__).parent / "bugs").iterdir())
                if case.is_dir()
            ]
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return
    if args.case is None or args.output is None:
        parser.error("--case and --output are required")
    source = prepare(args.case, args.output)
    workspace = Workspace.open(source)
    report = {
        "source_root": str(source),
        "workspace": str(workspace.root),
        "before": await invoke(workspace, "run_tests"),
        "diagnosis_match": None,
        "human_cause_verdict": "pending",
        "model_acceptance": "pending",
    }
    if args.diagnosis:
        actual = json.loads(args.diagnosis.read_text(encoding="utf-8"))
        expected = json.loads((args.case / "ground_truth.json").read_text(encoding="utf-8"))
        report["diagnosis_match"] = actual["path"] == expected["path"] and max(
            actual["start_line"], expected["start_line"]
        ) <= min(actual["end_line"], expected["end_line"])
        report["actual_diagnosis"], report["ground_truth"] = actual, expected
    if args.patch:
        report["patch"] = await invoke(
            workspace, "apply_patch", patch=args.patch.read_text(encoding="utf-8")
        )
        report["after"] = await invoke(workspace, "run_tests")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
