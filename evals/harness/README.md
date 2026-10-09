# Local Harness probes

Run without any model service or credentials:

```powershell
.\.venv\Scripts\python.exe evals/harness/run_offline.py
```

The versioned synthetic task runs the same Agent.run with C0 full history, C1 recent complete turns, and C2 bounded provenance-bearing excerpts. A literal-reading fixture reports whether its marker survived. This checks selection, protocol and budget contracts; it is not an LLM reasoning score or a cost-saving claim. Report: .local/harness-offline-report.json.

Failure/cancellation/permissions/MCP/storage are covered by backend/tests and frontend/tests. The separate evals/rag/questions.jsonl contains 28 existing knowledge tasks; local BGE retrieval uses those without sending data to a chat provider.

The user's current instruction permits local testing only. Real provider streaming, tool choice, grounded answers and C0/C1/C2 quality comparison remain pending. Do not run real chat evaluations during this stage.
