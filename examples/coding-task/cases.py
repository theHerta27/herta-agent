"""Small owned task fixtures, not an evaluation framework or an agent runtime."""

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

EXAMPLE = Path(__file__).resolve().parent
DEMO_ROOT = EXAMPLE.parents[1] / ".local" / "coding-demo"
TASKS = {
    "checkout": (
        "修复这个结算项目的两个问题：商品小计应计算数量；5000分免运费门槛应按折后商品金额判断，"
        "不足门槛运费500分。保留返回字段与其他行为。先运行现有测试观察真实失败，再搜索读代码，"
        "定位并修改，最后复测并解释结果。不要修改或删除现有测试。"
    ),
    "wordcount": (
        "为这个字频统计命令行程序增加 --format json：输出一个JSON对象，字段为total、unique、counts，"
        "counts是每个单词的计数；支持Unicode与空输入。默认text输出逐字保持兼容。"
        "把JSON序列化放入新模块wordcount/json_output.py，在tests/test_json_output.py补至少2个测试。"
        "先运行现有测试再阅读、实现和复测；不要修改或删除现有测试。不安装依赖。"
    ),
    "approval": (
        "把settings.py里的DEFAULT_RETRIES从2改为4，其他内容不变。先读取再提出修改。"
        "如果用户拒绝，或发生edit_conflict，立即停止修改并如实说明，不重试、不新建文件绕过。"
    ),
}


def prepare_case(name: str, *, demo_root: Path = DEMO_ROOT) -> Path:
    if name not in TASKS:
        raise ValueError("未知演示任务。")
    demo_root.mkdir(parents=True, exist_ok=True)
    target = Path(tempfile.mkdtemp(prefix=name + "-", dir=demo_root))
    shutil.copytree(
        EXAMPLE / "cases" / name,
        target,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    (target / ".herta-demo").write_text(name + "-v1\n", encoding="utf-8")
    return target


def check_case(root: Path, *, demo_root: Path = DEMO_ROOT) -> dict:
    root = root.resolve()
    if not root.is_relative_to(demo_root.resolve()) or root == demo_root.resolve():
        raise ValueError("只检查本工具新建的演示目录。")
    marker = root / ".herta-demo"
    if not marker.is_file() or marker.is_symlink():
        raise ValueError("演示标记不存在。")
    name = marker.read_text(encoding="utf-8").removesuffix("-v1\n")
    if name not in TASKS:
        raise ValueError("演示标记不匹配。")
    original = EXAMPLE / "cases" / name
    hashes = {
        path.relative_to(original).as_posix(): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in (original / "tests").glob("*.py")
    }
    unchanged = all(
        (root / path).is_file()
        and not (root / path).is_symlink()
        and hashlib.sha256((root / path).read_bytes()).hexdigest() == digest
        for path, digest in hashes.items()
    )
    worker = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            "-X",
            "utf8",
            str(EXAMPLE / "case_checks.py"),
            str(root),
            name,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        check=False,
    )
    try:
        observed = json.loads(worker.stdout)
        if worker.returncode != 0 or type(observed.get("tests_run")) is not int:
            raise ValueError
    except (ValueError, AttributeError):
        return {
            "passed": False,
            "checker_error": True,
            "original_tests_unchanged": unchanged,
        }
    passed = (
        unchanged
        and observed["tests_passed"]
        and observed["independent_behavior_passed"]
    )
    return {
        **observed,
        "passed": bool(passed),
        "case": name,
        "original_tests_unchanged": unchanged,
        "original_test_sha256": hashes,
        "model_called_by_checker": False,
    }
