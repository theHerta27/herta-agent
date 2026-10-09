# Herta V1 Implementation Plan

> Execute incrementally using the existing approved design. Separate desktop and tool domains use superpowers:dispatching-parallel-agents; root integrates and verifies.

**Goal:** A usable Windows desktop with budgeted context, reliable tools, visible sources/diagnostics, public settings and one-click startup.
**Architecture:** Keep Agent.run as the only runtime. Add a pure ContextEngine and provenance-bearing extractive summaries without modifying stored history. Credentials stay in the main/backend process environment.
**Tech Stack:** Python 3.12, FastAPI, SQLite, Electron, React, TypeScript.
**Spec:** docs/Herta_Agent_Harness_v1.md

## Constraints and review focus
- Local single-user Windows; preserve existing UI, knowledge and untracked user documents.
- Complete persona/current turn retained; whole tool exchanges selected together.
- Oversized required context fails before provider request.
- Summaries are untrusted derived data with source range/hash, never fabricated facts.
- Configuration changes during runs are refused; restart preserves history.
- Optional MCP is explicitly allowlisted and read-only; unavailable extensions must not block ordinary chat.
- Keys never enter renderer, public settings, logs or reports.
- Actual provider/RAG scores are reported only after actual API execution.

## Tasks
- [x] P0 backend/frontend baseline: 179 backend + 22 frontend tests, Python 3.12.13, Node 22.16.0, base 81a1d740.
- [x] Context: RED tests, settings/estimator/package, complete-turn selection, bounded extractive summaries, per-step persisted diagnostics, regression.
- [x] Tools/MCP: RED tests, permission/deadline metadata, official SDK readonly adapter/sample server, disconnect/cancellation coverage.
- [x] Desktop: RED tests, public settings and guarded backend restart, Context/evidence diagnostics, startup/chat/cancel/reload e2e.
- [x] Delivery/local evaluation: one-click launcher with local masked keys, frozen harness cases and C0/C1/C2 report, README/status.
- [x] Final full regression and independent review; address important findings and launch product.

## Verification
Backend unittest + Ruff; frontend unit + typecheck + lint + build + Electron e2e; local BGE retrieval + offline C0/C1/C2 probe; real provider evaluation deferred by latest user instruction; git diff --check.

## Decisions
The user requested execution of the supplied design and a usable first version, so do not repeat design approval. Work in the specified checkout to preserve its installed runtime/index; no external publish or branch merge. Optional Memory/Skills remain outside V1.

## Final local verification (2026-10-09)
223 backend unittest, Ruff check/format; 35 frontend unit, typecheck/lint/build, 11 Electron e2e all passed. Native offline launcher reached readiness and closed owned backend without sending a message. Independent review findings fixed. No remote real acceptance after user revoked permission. See docs/IMPLEMENTATION_STATUS.md and docs/HARNESS_EVAL_REPORT.md.

2026-10-09 后续授权：用户明确要求把当前版本上传 GitHub。提交首版实现/测试/文档/启动器并普通推送 origin/phase-6-ui；不合并、不创建PR、不上传本机密钥/数据库/权重，保留原有未追踪用户方案文档。
