# Herta Companion V1 Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline; one final independent review. User has already approved the product direction and instructed implementation; proceed without a second approval round.

**Goal:** Deliver the first usable daily companion release: local music, voice, reminders, tray and editable preferences.

**Architecture:** Preserve Python Agent.run. Add a focused SQLite-backed companion service with trusted tools and deterministic HTTP APIs; Electron owns media transport, notifications, microphone permission and tray. Local speech runs in cancellable subprocesses.

**Tech Stack:** Existing Python/FastAPI/SQLite, Electron/React/TypeScript; optional faster-whisper and Piper for offline speech.

**Spec:** docs/companion-v1-design.md

## Global Constraints

- Engineering references: references/hermes-agent-main; Cyrene only product inspiration.
- No real chat/Embedding API acceptance; no secret output; no Live2D/code collaboration.
- One Agent.run; default deny non-companion side effects; unchanged read-only MCP gate.
- Asia/Shanghai time; closing hides, explicit quit cleans children; exact notification delivery cannot be promised.
- Runtime never downloads speech models. Public model preparation is separate and explicit.
- Preserve user files/current feature branch. No push/merge.

## Review Focus

- Sleep/restart across reminder deadlines: no lost unread occurrence and no repeat flood.
- Stale playback updates after next/pause: never overwrite newer revision.
- Path/symlink changes after import: fail clearly; never accept arbitrary paths from renderer/model.
- Cancellation/backend restart during speech: child cleanup and no late playback/transcript.
- Permission revocation during a Run: companion actions stop; MCP stays denied.

### Task 1: Persisted companion services and trusted tools

**Files:** companion/{models,store,tools,context,router}.py; service/app.py; tools/executor.py; runtime/agent.py; tests/test_companion.py

**Interfaces:** CompanionStore(path).snapshot(), create_reminder(title,due_at,repeat), tick(now), update_preferences(values), propose_memory(text), music_command(action,track_id,volume). trusted_tool_policy(spec)->bool. Agent(..., tool_policy=None).

- [ ] Test real SQLite restart, due occurrence dedup/two connections, daily/week skip, invalid time, unread ack, approved preference vs pending memory, media ID validation/stale revision, denied generic side effects and revoked companion action.
- [ ] Run `.venv/Scripts/python.exe -m unittest discover -s backend/tests -p test_companion.py` and observe missing behavior.
- [ ] Implement focused services/router; lifespan tick task, cancellation cleanup; register built-ins and per-Run context.
- [ ] Verify targeted tests and existing backend suite; record evidence.

### Task 2: Desktop transport, media, tray and notifications

**Files:** frontend/electron/{companion,main,preload}.ts; shared/contracts.ts; index.html; tests/unit/companion.test.ts; tests/e2e/companion.spec.ts

**Interfaces:** DesktopBridge companionSnapshot(), companionAction(action), importMusic(), mediaUrl(id), voiceStatus(), synthesize(text), transcribe(wav), cancelVoice(). Companion snapshot contains preferences, memories, reminders, deliveries, tracks and playback.

- [ ] Test input validation and actual HTTP action results; Electron import fixture WAV, playback state, reminder notification receipt, hidden window restoration, explicit quit cleanup.
- [ ] Watch tests fail before adding bridge/protocol/lifecycle.
- [ ] Add fixed-route validated bridge; approved file import; restricted media protocol; polling delivery loop + Notification; tray and shortcut, backgroundThrottling disabled for audio.
- [ ] Verify units/typecheck/build and targeted Electron tests, update existing close assertions for hide vs quit.

### Task 3: Local speech preparation and cancellation

**Files:** companion/{speech,speech_worker}.py; scripts/prepare_voice.py; backend/pyproject.toml/uv.lock; frontend/src/audio/{coordinator,recorder}.ts; tests/test_speech.py; tests/unit/audio.test.ts

**Interfaces:** SpeechService.status(), synthesize(text), transcribe(wav); bounded local subprocesses. AudioCoordinator controls actual Audio and cancels generations. Recorder produces 16k mono PCM WAV <=60 seconds.

- [ ] Test malformed/oversize WAV, silence, absent model, killed request child; stale TTS response never plays; stop restores music level; resampling output header/frame limits.
- [ ] Run failing tests, implement offline local providers without runtime downloads and abortable bridge requests.
- [ ] Prepare dependencies/public Chinese voice + multilingual ASR under .local/voice; run local synth/silence smoke only.
- [ ] Verify tests/lockfile/model manifest and cleanup behavior.

### Task 4: Daily panel, spoken replies and editable recording

**Files:** frontend/src/components/{CompanionPanel,VoiceInput,AssistantMessage}.tsx; App.tsx; styles; tests/e2e/companion.spec.ts

**Interfaces:** Uses Task 2 bridge and Task 3 coordinator; voice result updates existing draft, never creates another model loop.

- [ ] Add failing real Electron tests for creating/cancelling/snoozing reminder, preferences save/reopen, music import/play/pause, recording draft, memory approval, focus routine and message read/stop.
- [ ] Implement compact music/reminder/preference panel using existing tokens, same chat entry and readable errors.
- [ ] Verify keyboard, empty/error states, persistence, local audio and screenshots.

### Task 5: Integrated local verification and delivery

**Files:** README.md; docs/{IMPLEMENTATION_STATUS,HERMES_SOURCE_MAP,COMPANION_ACCEPTANCE}.md; planning notes.

- [ ] Run backend suite/Ruff, frontend suite/typecheck/lint/build and full Electron E2E; no remote model requests.
- [ ] One fresh independent whole-change review under executing-plans, fix material findings with reproducing tests.
- [ ] Record actual evidence and limits; ensure one-click launch works, usable built output, close-to-tray/exit instructions.
- [ ] Preserve local artifacts and original docs; commit only authorized implementation if appropriate, no push/merge.
