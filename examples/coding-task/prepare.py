"""Create a fresh, owned task copy; never reads credentials or calls a model."""

import json
import shutil
import tempfile
from pathlib import Path

EXAMPLE = Path(__file__).resolve().parent
DEMO_ROOT = EXAMPLE.parents[1] / ".local" / "coding-demo"
TASK = (
    "修复average在空列表上的异常：空列表应返回0，保留非空列表的行为。"
    "先搜索并读取相关代码和测试，修复后运行unittest，说明实际结果。"
    "不要删除或弱化现有测试。"
)


def prepare() -> Path:
    DEMO_ROOT.mkdir(parents=True, exist_ok=True)
    target = Path(tempfile.mkdtemp(prefix="average-", dir=DEMO_ROOT))
    (target / "tests").mkdir()
    for relative in ("metrics.py", "tests/test_metrics.py", "AGENTS.md"):
        shutil.copyfile(EXAMPLE / "project" / relative, target / relative)
    (target / ".herta-demo").write_text("average-v1\n", encoding="utf-8")
    return target


if __name__ == "__main__":
    print(json.dumps({"project": str(prepare()), "task": TASK}, ensure_ascii=False))
