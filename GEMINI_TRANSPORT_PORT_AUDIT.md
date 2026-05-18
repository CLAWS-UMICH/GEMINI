# GEMINI Transport-Layer Port — Audit Report

**Date:** 2026-05-17
**Audited branch:** `stt-offload-port-plan`
**Baseline (plan starting point):** `ee599ff`
**Audited HEAD:** `a33e9b8`
**Auditor:** read-only inspection from sister repo `CORVUS_Integration` (branch `AI-integration-ar-merge`).

This document records (1) the audit plan I followed and (2) the findings. The plan is reusable for re-auditing later commits.

---

## Audit plan

A fresh auditor can reproduce this in ~10 minutes:

- [ ] **A1. Scope check.** Confirm only CORVUS-adjacent files changed since the plan baseline.
  ```bash
  git diff --stat ee599ff..HEAD | grep -v "^Assets/CLAWS/\|^Packages/\|^GEMINI_TRANSPORT_PORT" && echo "OUT-OF-SCOPE CHANGES FOUND" || echo "scope clean"
  ```
  Expected: `scope clean`. Anything in `Assets/Scripts/`, `Assets/Settings/`, `ProjectSettings/`, `Assets/CLAWS/Phase-1/Features/{Navigation,UIA,Vitals,Tasklist}` would be a red flag.

- [ ] **A2. Hard-constraint preservation.** Confirm the four "do not touch" files have zero diff:
  ```bash
  for f in Assets/CLAWS/Backend/Networking/CorvusARBridge.cs \
           Assets/CLAWS/Phase-1/Features/AIA/Scripts/CorvusHalo.cs \
           Assets/CLAWS/UI/IntentDisplayUI.cs \
           Assets/CLAWS/Backend/Networking/CorvusTTS.cs; do
    echo "$f: $(git diff ee599ff..HEAD -- $f | wc -l) lines"
  done
  ```
  Expected: every line says `0 lines`.

- [ ] **A3. Event preservation.** `CorvusController.cs` must declare all three events with the legacy signatures:
  ```bash
  grep -nE "event Action.*OnIntentReceived|event Action.*OnIntentResponseReceived|event Action +OnWakeDetected" Assets/CLAWS/Backend/Networking/CorvusController.cs
  ```
  Expected: 3 matches with shapes `Action<string, float, string, CorvusLatency>`, `Action<IntentResponse, CorvusLatency>`, `Action`.

- [ ] **A4. Main-thread firing.** Events must be enqueued on the main thread (so `Dispatch` can touch Unity APIs):
  ```bash
  grep -nB1 "OnIntentReceived?.Invoke\|OnIntentResponseReceived?.Invoke" Assets/CLAWS/Backend/Networking/CorvusController.cs | grep -i "MainThreadDispatcher"
  ```
  Expected: matches showing the invocations sit inside a `UnityMainThreadDispatcher.Instance().Enqueue(...)`.

- [ ] **A5. IntentResponse construction faithful to wire format.** Examine `HandleFinalFrame`:
  - `intent` coerced to `"unhandled"` if Python omits it.
  - `confidence` from `finalFrame.confidence`.
  - `response` defaulted to `""` if absent.
  - `parameters` always `null` (Python omits in Phase 1).

- [ ] **A6. No stale C# references to removed types.** Run:
  ```bash
  grep -rIn "SendCommandAsync\|OnRecordStop\|_microphoneRecord\|_whisper\b\|using Whisper\|CommandRequest" Assets/CLAWS --include="*.cs"
  ```
  Expected: zero matches. (Note: generic `StartRecording` / `StopRecording` matches in `Assets/Scripts/EyeTracking/` are unrelated to Whisper.)

- [ ] **A7. Prefab YAML sanity.**
  ```bash
  python3 -c "import yaml; list(yaml.safe_load_all(open('Assets/CLAWS/Phase-1/Features/AIA/Corvus.prefab')))" && echo "YAML OK"
  grep -n "WhisperManager\|MicrophoneRecord\|_whisper:\|_microphoneRecord:" Assets/CLAWS/Phase-1/Features/AIA/Corvus.prefab
  ```
  Expected: `YAML OK`, zero grep matches.

- [ ] **A8. AudioStreamer GUID parity.**
  ```bash
  meta=$(grep '^guid:' Assets/CLAWS/Backend/Networking/AudioStreamer.cs.meta | awk '{print $2}')
  prefab=$(grep "AudioStreamer" -A1 Assets/CLAWS/Phase-1/Features/AIA/Corvus.prefab | grep "guid:" | awk -F'guid: ' '{print $2}' | awk -F',' '{print $1}')
  [ "$meta" = "$prefab" ] && echo "GUID match: $meta" || echo "GUID MISMATCH"
  ```

- [ ] **A9. Ported files match sister repo.** Diff `PcmConverter.cs`, `PcmConverterTests.cs`, `AudioStreamer.cs`, the new asmdefs against the sister repo at `/mnt/c/Users/sunaa/Documents/CLAWS/CORVUS_Integration`. Cosmetic comment differences are OK; functional differences are not.

- [ ] **A10. Whisper-removal gating.** Confirm Task 10's deletions have NOT happened (smoke test must run first):
  ```bash
  grep -c "com.whisper.unity" Packages/manifest.json
  ls -la Assets/StreamingAssets/Whisper/ 2>/dev/null && echo "Whisper assets still present (expected)"
  ```
  Expected: manifest count `1`, `ggml-tiny.en.bin` still present.

---

## Findings (audit performed 2026-05-17)

### ✅ Pass
- **A1 Scope.** Only CORVUS-related files changed. 21 files, 2582 insertions, 293 deletions. No Navigation / Vitals / UIA / Tasklist / Settings / ProjectSettings collateral.
- **A2 Hard constraints.** `CorvusARBridge.cs`, `CorvusHalo.cs`, `IntentDisplayUI.cs`, `CorvusTTS.cs` — all 0-line diff against baseline.
- **A3 Events.** All three events declared with correct signatures at `CorvusController.cs:117-130`.
- **A4 Main-thread firing.** Both `OnIntentReceived` and `OnIntentResponseReceived` invoked inside the same `UnityMainThreadDispatcher.Instance().Enqueue(() => {...})` block at `CorvusController.cs:308-314`.
- **A5 IntentResponse construction.** `CorvusController.cs:287-296` — intent coerced to `"unhandled"` when empty, response defaulted to `""`, parameters set to `null`. Faithful to spec §8.
- **A6 No stale C# refs.** Zero matches in `Assets/CLAWS/**/*.cs` for any removed symbol. (Unrelated `StartRecording`/`StopRecording` methods exist in `Assets/Scripts/EyeTracking/`, but they belong to a different feature.)
- **A7 Prefab YAML.** Parses cleanly. Zero matches for `WhisperManager` / `MicrophoneRecord` / `_whisper:` / `_microphoneRecord:`.
- **A8 AudioStreamer GUID.** Meta `bba46168865945e783a71159c09084c2` matches prefab `m_Script.guid`.
- **A9 Ported files.** `AudioStreamer.cs` byte-identical to sister repo. `WebSocketClient.SendBinaryAsync` byte-identical. `PcmConverter.cs` identical except for one missing XML doc comment line. `PcmConverterTests.cs` identical except for two cosmetic inline comments. Math/logic unchanged.
- **A10 Whisper-removal gated correctly.** `com.whisper.unity` still in `Packages/manifest.json`; `ggml-tiny.en.bin` still on disk. Task 10 has not been run — consistent with the plan's "only after Task 9 smoke passes" gate.

### ⚠️ Minor cosmetic issues (non-blocking)

1. **Stale class docstring on `Assets/CLAWS/Testing/CorvusTest.cs:6-10`.** Says "Sends natural-language phrases to the Python NLU server via CorvusController". After the port, the harness only triggers `_corvusARBridge.SimulateIntent(...)` locally — no wire, no classifier. Suggested replacement: "Play-mode keyboard harness (keys 1–9). Triggers `CorvusARBridge.SimulateIntent` locally to exercise the Dispatch path without going through Python. Production voice testing happens via the wake word."

2. **`PcmConverter.cs` XML doc missing one line.** The sister repo includes `/// Scaling factor is 32768 with intermediate int clamp so -1.0 maps to short.MinValue.` This explains the 32768-vs-32767 nuance that caught us out during the original port. Functionally correct in GEMINI but a reader hitting this code cold won't know why 32768 was chosen.

3. **`PcmConverterTests.cs` missing two inline comments.** The `0.5 * 32767` rounding comment and the `// both should clamp to 32767` comment in the `AboveOne_ClampsToShortMax` test. Tests still assert correctly; just less self-documenting.

### ❌ No critical or important issues found.

---

## What's still pending (per the plan)

- **Task 9** — manual end-to-end smoke test against the Python EVA server (`corvus-eva`). User-driven; needs Python server running and a microphone-enabled Unity Play session.
- **Task 10** — remove `com.whisper.unity` from `Packages/manifest.json` and delete `Assets/StreamingAssets/Whisper/`. Gated on Task 9 passing.

---

## Overall verdict

**Implementation matches plan intent.** The transport layer was swapped exactly as specified; the `Dispatch` switch and the three preserved events stayed inviolate. The three cosmetic nits above can be cleaned up in a tiny follow-up commit — none of them affect runtime behavior or block the smoke test.
