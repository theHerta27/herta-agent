# Windows夹具路径比较失败摘录

这是本轮工具输出的保留摘录，不是完整原始日志。第一次运行`focused-final.log`时20项中1项失败；随后以同名日志保存通过结果，导致原文件被覆盖。这里明确保留失败和覆盖事实。

```text
FAIL: test_nonregular_directory_entries_are_not_opened
test_cli_search.py line143
self.assertEqual([hit["path"] for hit in result.data["matches"]], ["ordinary.txt"])
AssertionError: Lists differ: ['ordinary.txt', 'pipe-fixture'] != ['ordinary.txt']
Ran 20 tests
FAILED (failures=1)
```

定位时实际打印`Temporary fixture path already canonical: False`。Repository.root经过resolve，Windows临时目录原路径可能包含ADMINI~1别名；测试替换Path.is_file时比较未规范化路径，漏掉目标。夹具改为`self.root = self.repo.root`，产品过滤条件未绕开。修正后20项通过，并用进程内移除保护的变异验证确认此测试确实能检出缺失条件。
