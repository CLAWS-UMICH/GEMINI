# GEMINI Transport-Layer Port — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Swap GEMINI's CORVUS transport layer from "Whisper-on-Unity + text-command-in / IntentResponse-out" to "raw-PCM-stream-in / `{type:"final"}`-out" so GEMINI works with the new Python EVA server, while leaving the 611-line `CorvusARBridge.Dispatch` switch and the `IntentResponse` / `IntentParameters` data classes completely untouched.

**Architecture:** Unity owns wake-word + mic capture + Piper TTS + intent-to-Unity-API routing. Python (separate repo, `corvus-eva` server) owns Silero VAD + faster-whisper + classifier. WebSocket carries binary PCM up and JSON `final` frames down. `CorvusController` reads the new `final` frame, builds an `IntentResponse` from it, and fires the existing `OnIntentReceived` / `OnIntentResponseReceived` events so `CorvusARBridge.Dispatch` keeps working unchanged.

**Tech Stack:** Unity 6, C# 9, Unity Test Framework, `System.Net.WebSockets.ClientWebSocket`, Unity `Microphone` API, Piper TTS (already in scene), `whisper.unity` (to be removed).

**Spec:** `docs/superpowers/specs/2026-05-17-gemini-transport-port-design.md`. Read the spec first if any task feels under-specified.

**Working directory:** `/mnt/c/Users/sunaa/Documents/CLAWS/GEMINI` (branch `main`, baseline commit `ee599ff`).

**Sister repo with the working reference implementation:** `/mnt/c/Users/sunaa/Documents/CLAWS/CORVUS_Integration` branch `AI-integration-ar-merge`. Paths like `[sister]/Assets/...` in this plan refer to that repo. Read-only — never write into it.

**Reset escape hatch:** if anything goes wrong, `git reset --hard ee599ff` returns to the baseline.

---

## Hard constraints — must hold across every task

These come from the spec. Violating any of them invalidates the migration.

1. **Do NOT modify** `Assets/CLAWS/Backend/Networking/CorvusARBridge.cs` (611 lines).
2. **Do NOT modify** `Assets/CLAWS/Phase-1/Features/AIA/Scripts/CorvusHalo.cs`.
3. **Do NOT modify** `Assets/CLAWS/UI/IntentDisplayUI.cs`.
4. **Do NOT modify** `Assets/CLAWS/Backend/Networking/CorvusTTS.cs`.
5. **Preserve** events `OnWakeDetected()`, `OnIntentReceived(string,float,string,CorvusLatency)`, `OnIntentResponseReceived(IntentResponse,CorvusLatency)`. All three must fire on the Unity main thread for every successful `final` frame.
6. **Preserve** classes `IntentResponse`, `IntentParameters`, `CorvusLatency` in their current shape and namespace (`CLAWS.Networking`).
7. Don't push. Don't `git add .` / `-A` (Unity scenes / packages-lock churn would sweep in spurious files).
8. After the prefab edit task, `Corvus.prefab` is the source of truth — both `Assets/CLAWS/GEMINI.unity` and `Assets/CLAWS/Phase-1/Features/Navigation.unity` reference it.

---

## File structure summary

### Created
| Path | Purpose |
|---|---|
| `Assets/CLAWS/Backend/Networking/Audio/CLAWS.Audio.asmdef` (+ meta) | Isolated assembly for pure-C# audio helpers |
| `Assets/CLAWS/Backend/Networking/Audio/PcmConverter.cs` (+ meta) | float→int16 LE conversion + chunk splitter |
| `Assets/CLAWS/Backend/Networking/AudioStreamer.cs` (+ meta) | MonoBehaviour: Unity `Microphone` → `WebSocketClient.SendBinaryAsync` |
| `Assets/CLAWS/Tests/Editor/CLAWS.Audio.Tests.Editor.asmdef` (+ meta) | Edit-mode test assembly |
| `Assets/CLAWS/Tests/Editor/SmokeTest.cs` (+ meta) | Proves test runner is alive |
| `Assets/CLAWS/Tests/Editor/PcmConverterTests.cs` (+ meta) | 11 NUnit tests for `PcmConverter` |

### Modified
| Path | Change |
|---|---|
| `Assets/CLAWS/Backend/Networking/WebSocketClient.cs` | Add `SendBinaryAsync(byte[])` |
| `Assets/CLAWS/Backend/Networking/CorvusController.cs` | New DTOs + state-machine rewrite, preserve events |
| `Assets/CLAWS/Testing/CorvusTest.cs` | Drop `SendCommandAsync` call; always use `SimulateIntent` |
| `Assets/CLAWS/Phase-1/Features/AIA/Corvus.prefab` | Remove `WhisperManager` + `MicrophoneRecord` components; add `AudioStreamer`; wire `_audioStreamer` |
| `Packages/manifest.json` | Remove `com.whisper.unity` line |

### Deleted (final task only)
| Path | Reason |
|---|---|
| `Assets/StreamingAssets/Whisper/ggml-tiny.en.bin` (+ meta) | ~77 MB model no longer loaded |
| `Assets/StreamingAssets/Whisper/` folder + meta | Empty after model removal |

### Unity will auto-regenerate after manifest edit
- `Packages/packages-lock.json` — commit after Unity reimports.

---

## Pre-flight: how to run tests

### GUI
1. Open Unity Editor with the GEMINI project.
2. `Window > General > Test Runner`.
3. Select "EditMode" tab → `Run All`.

### CLI (from WSL or PowerShell)
Replace `<UNITY_PATH>` with your Unity install (the project uses Unity 6 per `ProjectSettings/ProjectVersion.txt`):

```bash
"<UNITY_PATH>" -batchmode -nographics \
  -projectPath /mnt/c/Users/sunaa/Documents/CLAWS/GEMINI \
  -runTests -testPlatform EditMode \
  -testResults TestResults.xml \
  -logFile -
```

Expected for a green run: exit code 0, `TestResults.xml` shows `result="Passed"` for every test case.

If you cannot reach Unity (running from a WSL shell with no Unity install in PATH), perform TDD by inspection — write tests first, confirm by reading that the type-under-test does not exist yet, then implement, then walk every test against the implementation mentally. The human will run the actual test runner.

---

## Task 0: Set up minimal test infrastructure

**Why:** GEMINI has no asmdef-based test assemblies. We carve out one tiny production asmdef (`CLAWS.Audio`) for the pure audio code and one test asmdef that references it. Smallest possible blast radius.

**Files:**
- Create: `Assets/CLAWS/Backend/Networking/Audio/CLAWS.Audio.asmdef` (+ `.meta`)
- Create: `Assets/CLAWS/Tests/Editor/CLAWS.Audio.Tests.Editor.asmdef` (+ `.meta`)
- Create: `Assets/CLAWS/Tests/Editor/SmokeTest.cs` (+ `.meta`)

Unity also auto-generates `.meta` files for any new directories under `Assets/`. Generate them ourselves so the working tree stays clean after the next Unity import — the project tracks every `.meta` in git.

- [ ] **Step 1: Create the production asmdef**

`Assets/CLAWS/Backend/Networking/Audio/CLAWS.Audio.asmdef`:
```json
{
    "name": "CLAWS.Audio",
    "rootNamespace": "CLAWS.Audio",
    "references": [],
    "includePlatforms": [],
    "excludePlatforms": [],
    "allowUnsafeCode": false,
    "overrideReferences": false,
    "precompiledReferences": [],
    "autoReferenced": true,
    "defineConstraints": [],
    "versionDefines": [],
    "noEngineReferences": false
}
```

`autoReferenced: true` means the default `Assembly-CSharp` (where `AudioStreamer.cs` and `CorvusController.cs` live) automatically sees `CLAWS.Audio` types without manual reference.

- [ ] **Step 2: Create the test asmdef**

`Assets/CLAWS/Tests/Editor/CLAWS.Audio.Tests.Editor.asmdef`:
```json
{
    "name": "CLAWS.Audio.Tests.Editor",
    "rootNamespace": "",
    "references": [
        "UnityEngine.TestRunner",
        "UnityEditor.TestRunner",
        "CLAWS.Audio"
    ],
    "includePlatforms": [
        "Editor"
    ],
    "excludePlatforms": [],
    "allowUnsafeCode": false,
    "overrideReferences": true,
    "precompiledReferences": [
        "nunit.framework.dll"
    ],
    "autoReferenced": false,
    "defineConstraints": [
        "UNITY_INCLUDE_TESTS"
    ],
    "versionDefines": [],
    "noEngineReferences": false
}
```

- [ ] **Step 3: Write the smoke test**

`Assets/CLAWS/Tests/Editor/SmokeTest.cs`:
```csharp
using NUnit.Framework;

public class SmokeTest
{
    [Test]
    public void SmokeTest_TestRunnerExecutes_Passes()
    {
        Assert.That(1 + 1, Is.EqualTo(2));
    }
}
```

- [ ] **Step 4: Generate `.meta` files**

Unity normally generates `.meta` files on import. Since this plan may be executed from a WSL shell with no Unity available, generate them yourself with stable random GUIDs. Use `python3 -c "import uuid; print(uuid.uuid4().hex)"` for each GUID. Each meta gets a unique 32-hex-char GUID. Reference an existing `.cs.meta` in `Assets/CLAWS/Backend/Networking/` (e.g., `WebSocketClient.cs.meta`) for the project's canonical minimal format.

Asmdef `.meta` template (one per asmdef, fresh GUID each):
```
fileFormatVersion: 2
guid: <32-hex-char-guid>
AssemblyDefinitionImporter:
  externalObjects: {}
  userData: 
  assetBundleHash: 
```

Script `.meta` template (one per `.cs`, fresh GUID each):
```
fileFormatVersion: 2
guid: <32-hex-char-guid>
MonoImporter:
  externalObjects: {}
  serializedVersion: 2
  defaultReferences: []
  executionOrder: 0
  icon: {instanceID: 0}
  userData: 
  assetBundleHash: 
```

Also generate folder metas for the new directories (`Audio/`, `Tests/`, `Tests/Editor/`):
```
fileFormatVersion: 2
guid: <32-hex-char-guid>
folderAsset: yes
DefaultImporter:
  externalObjects: {}
  userData: 
  assetBundleHash: 
```

Required folder metas:
- `Assets/CLAWS/Backend/Networking/Audio.meta`
- `Assets/CLAWS/Tests.meta`
- `Assets/CLAWS/Tests/Editor.meta`

- [ ] **Step 5: Run the smoke test (if Unity is reachable)**

GUI: open Test Runner, hit Run All in EditMode.
CLI: see pre-flight section.

Expected: 1 test, 1 passed.

If Unity is not reachable from your shell, skip this step and note "Unity test run deferred to human; smoke test added but not executed" in your report.

- [ ] **Step 6: Commit**

```bash
git add Assets/CLAWS/Backend/Networking/Audio/CLAWS.Audio.asmdef \
        Assets/CLAWS/Backend/Networking/Audio/CLAWS.Audio.asmdef.meta \
        Assets/CLAWS/Backend/Networking/Audio.meta \
        Assets/CLAWS/Tests.meta \
        Assets/CLAWS/Tests/Editor.meta \
        Assets/CLAWS/Tests/Editor/CLAWS.Audio.Tests.Editor.asmdef \
        Assets/CLAWS/Tests/Editor/CLAWS.Audio.Tests.Editor.asmdef.meta \
        Assets/CLAWS/Tests/Editor/SmokeTest.cs \
        Assets/CLAWS/Tests/Editor/SmokeTest.cs.meta
git commit -m "test: set up CLAWS.Audio + tests asmdefs with smoke test"
```

---

## Task 1: PcmConverter — float → int16 little-endian conversion (TDD)

**Why:** Unity's `Microphone.GetData` returns `float[]` in `[-1.0, 1.0]`. Python expects little-endian int16 PCM bytes (per `UNITY_PYTHON_CONTRACT.md` §3). Pure function, fully testable.

**Important scaling note:** the implementation multiplies by **32768** (not `short.MaxValue = 32767`) with an intermediate `int` clamp, so `-1.0f` maps to `short.MinValue = -32768`. This was a real bug we found in the sister repo's first attempt — the test for `-1.0 → {0x00, 0x80}` failed when scaling by 32767 (which produces `-32767 = {0x01, 0x80}`). The code below uses the correct 32768 scaling.

**Files:**
- Create: `Assets/CLAWS/Backend/Networking/Audio/PcmConverter.cs` (+ meta)
- Create: `Assets/CLAWS/Tests/Editor/PcmConverterTests.cs` (+ meta)

- [ ] **Step 1: Write the failing test file**

`Assets/CLAWS/Tests/Editor/PcmConverterTests.cs`:
```csharp
using NUnit.Framework;
using CLAWS.Audio;

public class PcmConverterTests
{
    [Test]
    public void FloatsToInt16_Zero_ProducesZeroBytes()
    {
        var floats = new float[] { 0.0f };
        var bytes = PcmConverter.FloatsToInt16(floats);
        Assert.That(bytes.Length, Is.EqualTo(2));
        Assert.That(bytes[0], Is.EqualTo(0));
        Assert.That(bytes[1], Is.EqualTo(0));
    }

    [Test]
    public void FloatsToInt16_MaxPositive_ProducesShortMax()
    {
        var floats = new float[] { 1.0f };
        var bytes = PcmConverter.FloatsToInt16(floats);
        // short.MaxValue = 32767 = 0x7FFF, little-endian → 0xFF 0x7F
        Assert.That(bytes[0], Is.EqualTo(0xFF));
        Assert.That(bytes[1], Is.EqualTo(0x7F));
    }

    [Test]
    public void FloatsToInt16_MaxNegative_ProducesShortMin()
    {
        var floats = new float[] { -1.0f };
        var bytes = PcmConverter.FloatsToInt16(floats);
        // short.MinValue = -32768 = 0x8000, little-endian → 0x00 0x80
        Assert.That(bytes[0], Is.EqualTo(0x00));
        Assert.That(bytes[1], Is.EqualTo(0x80));
    }

    [Test]
    public void FloatsToInt16_AboveOne_ClampsToShortMax()
    {
        var floats = new float[] { 1.5f, 2.0f };
        var bytes = PcmConverter.FloatsToInt16(floats);
        Assert.That(bytes[0], Is.EqualTo(0xFF));
        Assert.That(bytes[1], Is.EqualTo(0x7F));
        Assert.That(bytes[2], Is.EqualTo(0xFF));
        Assert.That(bytes[3], Is.EqualTo(0x7F));
    }

    [Test]
    public void FloatsToInt16_BelowNegativeOne_ClampsToShortMin()
    {
        var floats = new float[] { -1.5f };
        var bytes = PcmConverter.FloatsToInt16(floats);
        Assert.That(bytes[0], Is.EqualTo(0x00));
        Assert.That(bytes[1], Is.EqualTo(0x80));
    }

    [Test]
    public void FloatsToInt16_EmptyInput_ProducesEmptyOutput()
    {
        var bytes = PcmConverter.FloatsToInt16(new float[0]);
        Assert.That(bytes.Length, Is.EqualTo(0));
    }

    [Test]
    public void FloatsToInt16_KnownMidValue_RoundsToExpectedInt16()
    {
        var bytes = PcmConverter.FloatsToInt16(new float[] { 0.5f });
        short value = (short)(bytes[0] | (bytes[1] << 8));
        Assert.That(value, Is.InRange((short)16380, (short)16386));
    }
}
```

- [ ] **Step 2: Confirm the tests would fail**

Either run Unity Test Runner (expect 7 fails with "type or namespace `PcmConverter` could not be found"), or verify by inspection that `Assets/CLAWS/Backend/Networking/Audio/PcmConverter.cs` does not yet exist:

```bash
ls Assets/CLAWS/Backend/Networking/Audio/PcmConverter.cs 2>&1
```

Expected: `No such file or directory`. Note this confirmation in your report — that's the TDD evidence.

- [ ] **Step 3: Implement `PcmConverter.FloatsToInt16`**

`Assets/CLAWS/Backend/Networking/Audio/PcmConverter.cs`:
```csharp
using System;

namespace CLAWS.Audio
{
    public static class PcmConverter
    {
        /// <summary>
        /// Convert float samples in [-1.0, 1.0] to little-endian int16 PCM bytes.
        /// Values outside [-1.0, 1.0] are clamped. Output length is 2 * samples.Length.
        /// Scaling factor is 32768 with intermediate int clamp so -1.0 maps to short.MinValue.
        /// </summary>
        public static byte[] FloatsToInt16(float[] samples)
        {
            if (samples == null || samples.Length == 0)
                return Array.Empty<byte>();

            var bytes = new byte[samples.Length * 2];
            for (int i = 0; i < samples.Length; i++)
            {
                float clamped = samples[i];
                if (clamped > 1.0f) clamped = 1.0f;
                else if (clamped < -1.0f) clamped = -1.0f;

                int scaled = (int)(clamped * 32768f);
                if (scaled > short.MaxValue) scaled = short.MaxValue;
                else if (scaled < short.MinValue) scaled = short.MinValue;

                short value = (short)scaled;
                bytes[i * 2] = (byte)(value & 0xFF);
                bytes[i * 2 + 1] = (byte)((value >> 8) & 0xFF);
            }
            return bytes;
        }
    }
}
```

- [ ] **Step 4: Walk each test against the implementation**

Confirm by inspection that every test passes:
1. `0.0f` → `(int)(0 * 32768) = 0` → bytes `{0x00, 0x00}`. ✓
2. `1.0f` → `(int)(1.0 * 32768) = 32768` → clamped to 32767 → bytes `{0xFF, 0x7F}`. ✓
3. `-1.0f` → `(int)(-1.0 * 32768) = -32768` → no clamp → bytes `{0x00, 0x80}`. ✓
4. `1.5f`/`2.0f` → clamped to `1.0f` first → same as test 2 ×2. ✓
5. `-1.5f` → clamped to `-1.0f` first → same as test 3. ✓
6. empty → `Array.Empty<byte>()`. ✓
7. `0.5f` → `(int)(0.5 * 32768) = 16384` → in range `[16380, 16386]`. ✓

If Unity is reachable, run the test runner and confirm 7 passes. If not, the walk-through above is the evidence.

- [ ] **Step 5: Generate `.meta` files**

Generate `PcmConverter.cs.meta` and `PcmConverterTests.cs.meta` using the `MonoImporter` template from Task 0 Step 4 — fresh 32-hex-char GUID each.

- [ ] **Step 6: Commit**

```bash
git add Assets/CLAWS/Backend/Networking/Audio/PcmConverter.cs \
        Assets/CLAWS/Backend/Networking/Audio/PcmConverter.cs.meta \
        Assets/CLAWS/Tests/Editor/PcmConverterTests.cs \
        Assets/CLAWS/Tests/Editor/PcmConverterTests.cs.meta
git commit -m "feat(audio): PcmConverter float-to-int16 little-endian"
```

---

## Task 2: PcmConverter — chunking helper (TDD)

**Why:** A future helper for callers that want to accumulate samples and emit fixed-size chunks. `AudioStreamer` doesn't actually call this (it chunks naturally via Microphone position polling), but the helper is documented in the contract and kept symmetrical with the sister repo.

**Files:**
- Modify: `Assets/CLAWS/Backend/Networking/Audio/PcmConverter.cs`
- Modify: `Assets/CLAWS/Tests/Editor/PcmConverterTests.cs`

- [ ] **Step 1: Append failing tests to `PcmConverterTests.cs`**

Add these methods inside the existing `PcmConverterTests` class (after the existing 7 tests):

```csharp
    [Test]
    public void ChunkSamples_ExactMultiple_ProducesEqualChunks()
    {
        var samples = new float[3200]; // 2 chunks of 1600
        var chunks = PcmConverter.ChunkSamples(samples, chunkSize: 1600);
        Assert.That(chunks.Count, Is.EqualTo(2));
        Assert.That(chunks[0].Length, Is.EqualTo(1600));
        Assert.That(chunks[1].Length, Is.EqualTo(1600));
    }

    [Test]
    public void ChunkSamples_PartialTail_DropsTail()
    {
        // 1700 samples → 1 full chunk of 1600; remainder 100 dropped
        // (Tail handling is the caller's responsibility — keep this function strict.)
        var samples = new float[1700];
        var chunks = PcmConverter.ChunkSamples(samples, chunkSize: 1600);
        Assert.That(chunks.Count, Is.EqualTo(1));
        Assert.That(chunks[0].Length, Is.EqualTo(1600));
    }

    [Test]
    public void ChunkSamples_SmallerThanChunk_ReturnsEmpty()
    {
        var samples = new float[800];
        var chunks = PcmConverter.ChunkSamples(samples, chunkSize: 1600);
        Assert.That(chunks.Count, Is.EqualTo(0));
    }

    [Test]
    public void ChunkSamples_PreservesData()
    {
        var samples = new float[1600];
        for (int i = 0; i < samples.Length; i++) samples[i] = i / 1600f;
        var chunks = PcmConverter.ChunkSamples(samples, chunkSize: 1600);
        Assert.That(chunks.Count, Is.EqualTo(1));
        Assert.That(chunks[0][0], Is.EqualTo(0f));
        Assert.That(chunks[0][1599], Is.EqualTo(1599f / 1600f));
    }
```

- [ ] **Step 2: Confirm failures**

Either run tests (expect 4 new fails with "ChunkSamples not found") or verify by inspection that `PcmConverter` currently has only the `FloatsToInt16` method.

- [ ] **Step 3: Implement `ChunkSamples`**

Add `using System.Collections.Generic;` at the top of `PcmConverter.cs` (alongside `using System;`).

Then add this method inside the `PcmConverter` static class:

```csharp
        /// <summary>
        /// Split a sample buffer into fixed-size chunks. Drops any partial tail
        /// shorter than chunkSize; the caller should accumulate the remainder
        /// across calls if it needs lossless behavior.
        /// </summary>
        public static List<float[]> ChunkSamples(float[] samples, int chunkSize)
        {
            var chunks = new List<float[]>();
            if (samples == null || chunkSize <= 0) return chunks;

            int fullChunks = samples.Length / chunkSize;
            for (int c = 0; c < fullChunks; c++)
            {
                var chunk = new float[chunkSize];
                Array.Copy(samples, c * chunkSize, chunk, 0, chunkSize);
                chunks.Add(chunk);
            }
            return chunks;
        }
```

- [ ] **Step 4: Walk each new test against the implementation**

1. `ExactMultiple`: 3200/1600 = 2 full chunks of 1600. ✓
2. `PartialTail`: 1700/1600 = 1 full chunk; 100-sample tail dropped. ✓
3. `SmallerThanChunk`: 800/1600 = 0 chunks; empty list. ✓
4. `PreservesData`: `Array.Copy` preserves; `chunk[0]=0f`, `chunk[1599]=1599/1600f`. ✓

If Unity is reachable, run tests and confirm 11 passes (7 from Task 1 + 4 from Task 2). Otherwise note the walk-through as evidence.

- [ ] **Step 5: Commit**

```bash
git add Assets/CLAWS/Backend/Networking/Audio/PcmConverter.cs \
        Assets/CLAWS/Tests/Editor/PcmConverterTests.cs
git commit -m "feat(audio): PcmConverter chunking helper"
```

No new `.meta` changes — both files already have metas from Task 1.

---

## Task 3: WebSocketClient.SendBinaryAsync

**Why:** Current `WebSocketClient.SendAsync(string)` only emits text frames. Audio chunks need `WebSocketMessageType.Binary`. The underlying `ClientWebSocket` supports both natively.

**Files:**
- Modify: `Assets/CLAWS/Backend/Networking/WebSocketClient.cs`

No unit test — testing `SendBinaryAsync` against a real server requires either a hand-rolled mock WebSocket server or integration testing with Python. We verify manually in Task 9 (end-to-end). The change is mechanical and small.

- [ ] **Step 1: Locate the existing `SendAsync(string)` method**

Open `Assets/CLAWS/Backend/Networking/WebSocketClient.cs`. The `SendAsync(string)` method runs from approximately line 57 to its closing brace at approximately line 89 (just before `public async Task<string> ReceiveAsync()`).

- [ ] **Step 2: Insert `SendBinaryAsync` immediately after `SendAsync(string)`'s closing brace**

Insert this method (8-space indent on the signature, 12-space body) between the `SendAsync(string)` closing brace and the `ReceiveAsync()` declaration:

```csharp
        public async Task SendBinaryAsync(byte[] data)
        {
            if (!IsConnected)
            {
                Debug.LogError("Cannot send binary: WebSocket is not connected");
                return;
            }

            if (data == null || data.Length == 0) return;

            try
            {
                var buffer = new ArraySegment<byte>(data);
                await _webSocket.SendAsync(
                    buffer,
                    WebSocketMessageType.Binary,
                    true,
                    _cancellationTokenSource.Token
                );
            }
            catch (Exception ex)
            {
                Debug.LogError($"Failed to send binary frame: {ex.Message}");
                throw;
            }
        }
```

**Critical:** no success-path `Debug.Log` — audio streams at 10 Hz; logging every send would spam the Console.

- [ ] **Step 3: Confirm it compiles (if Unity is reachable)**

Open Unity, wait for the script reload. The Console should show no compile errors.

If Unity is not reachable, verify by inspection:
- `using` statements at the top already include `System`, `System.Net.WebSockets`, `System.Threading.Tasks`, `UnityEngine` — yes, `SendBinaryAsync` compiles.
- `_cancellationTokenSource` is a private field — yes, the same one used by `SendAsync(string)`.

- [ ] **Step 4: Commit**

```bash
git add Assets/CLAWS/Backend/Networking/WebSocketClient.cs
git commit -m "feat(net): add SendBinaryAsync for PCM streaming"
```

---

## Task 4: AudioStreamer MonoBehaviour

**Why:** Bridges Unity's `Microphone` API to `WebSocketClient.SendBinaryAsync`. Owns the recording AudioClip and the chunk-emit loop. Uses `PcmConverter` for sample conversion.

**Files:**
- Create: `Assets/CLAWS/Backend/Networking/AudioStreamer.cs` (+ meta)

Because `Microphone` is a static Unity API, this class is integration-tested manually in Task 9 (end-to-end smoke). The pure conversion paths (`PcmConverter`) are already covered by tests; this class is just the glue.

- [ ] **Step 1: Create the file**

`Assets/CLAWS/Backend/Networking/AudioStreamer.cs`:
```csharp
using System.Collections;
using UnityEngine;
using CLAWS.Audio;

namespace CLAWS.Networking
{
    /// <summary>
    /// Captures HoloLens microphone at 16kHz mono, converts to int16 PCM,
    /// and streams ~100ms chunks over WebSocketClient.SendBinaryAsync.
    /// </summary>
    public class AudioStreamer : MonoBehaviour
    {
        private const int SAMPLE_RATE = 16000;
        private const int CHUNK_SAMPLES = 1600;  // 100ms at 16kHz
        private const int CLIP_LENGTH_SEC = 10;  // ring buffer length

        [SerializeField] private string _microphoneDevice; // null/empty = default device

        private WebSocketClient _webSocket;
        private AudioClip _recordingClip;
        private int _lastReadPosition;
        private bool _isStreaming;
        private Coroutine _pumpCoroutine;

        public bool IsStreaming => _isStreaming;

        public void Initialize(WebSocketClient webSocket)
        {
            _webSocket = webSocket;
        }

        public void StartStreaming()
        {
            if (_isStreaming) return;
            if (_webSocket == null)
            {
                Debug.LogError("[AudioStreamer] WebSocket not initialized");
                return;
            }
            if (Microphone.devices.Length == 0)
            {
                Debug.LogError("[AudioStreamer] No microphone devices available");
                return;
            }

            string device = string.IsNullOrEmpty(_microphoneDevice) ? null : _microphoneDevice;
            _recordingClip = Microphone.Start(device, true, CLIP_LENGTH_SEC, SAMPLE_RATE);
            _lastReadPosition = 0;
            _isStreaming = true;
            _pumpCoroutine = StartCoroutine(PumpAudio(device));
            Debug.Log("[AudioStreamer] Streaming started");
        }

        public void StopStreaming()
        {
            if (!_isStreaming) return;
            _isStreaming = false;

            if (_pumpCoroutine != null) StopCoroutine(_pumpCoroutine);
            _pumpCoroutine = null;

            string device = string.IsNullOrEmpty(_microphoneDevice) ? null : _microphoneDevice;
            if (Microphone.IsRecording(device))
                Microphone.End(device);

            if (_recordingClip != null)
            {
                Destroy(_recordingClip);
                _recordingClip = null;
            }
            Debug.Log("[AudioStreamer] Streaming stopped");
        }

        private IEnumerator PumpAudio(string device)
        {
            // ~100ms cadence
            var wait = new WaitForSeconds(0.05f);
            while (_isStreaming && _recordingClip != null)
            {
                yield return wait;

                int currentPos = Microphone.GetPosition(device);
                int available = currentPos - _lastReadPosition;
                if (available < 0) available += _recordingClip.samples; // ring wraparound

                if (available < CHUNK_SAMPLES) continue;

                int fullChunks = available / CHUNK_SAMPLES;
                int samplesToRead = fullChunks * CHUNK_SAMPLES;

                var buffer = new float[samplesToRead];
                _recordingClip.GetData(buffer, _lastReadPosition);
                _lastReadPosition = (_lastReadPosition + samplesToRead) % _recordingClip.samples;

                var pcm = PcmConverter.FloatsToInt16(buffer);
                // Fire-and-forget; SendBinaryAsync catches its own errors
                _ = _webSocket.SendBinaryAsync(pcm);
            }
        }

        private void OnDestroy()
        {
            if (_isStreaming) StopStreaming();
        }
    }
}
```

- [ ] **Step 2: Generate the `.meta` file**

`Assets/CLAWS/Backend/Networking/AudioStreamer.cs.meta` using the `MonoImporter` template from Task 0 Step 4 with a fresh GUID.

- [ ] **Step 3: Confirm it compiles (if Unity is reachable)**

Open Unity, wait for script reload. `AudioStreamer` should appear in the AddComponent menu under `Scripts > CLAWS.Networking`.

- [ ] **Step 4: Commit**

```bash
git add Assets/CLAWS/Backend/Networking/AudioStreamer.cs \
        Assets/CLAWS/Backend/Networking/AudioStreamer.cs.meta
git commit -m "feat(audio): AudioStreamer MonoBehaviour for mic-to-WebSocket streaming"
```

---

## Task 5: CorvusController — add new control-message DTOs (no commit yet)

**Why:** New protocol uses `{type, ...}` shape per `UNITY_PYTHON_CONTRACT.md`. Add the four new DTOs alongside the existing `CommandRequest` / `IntentResponse` / `IntentParameters` / `CorvusLatency`. Don't remove the old ones yet — Tasks 6+7 will retire `CommandRequest`. The existing `IntentResponse` and `IntentParameters` stay forever (they're the `Dispatch` API).

**Files:**
- Modify: `Assets/CLAWS/Backend/Networking/CorvusController.cs`

- [ ] **Step 1: Add new DTOs after the existing `IntentResponse` class**

In `CorvusController.cs`, after the closing brace of the `IntentResponse` class (which ends at approximately line 39) and before the `CorvusLatency` class declaration (approximately line 40), insert:

```csharp
    [System.Serializable]
    public class StartMessage
    {
        public string type = "start";
        public int sample_rate = 16000;
        public int channels = 1;
    }

    [System.Serializable]
    public class StopMessage
    {
        public string type = "stop";
    }

    /// <summary>
    /// Generic incoming-frame envelope. Used to peek at `type` before
    /// deserializing the full body.
    /// </summary>
    [System.Serializable]
    public class FrameEnvelope
    {
        public string type;
    }

    /// <summary>
    /// Incoming "final" frame from Python EVA server. Fields beyond `type` and `response`
    /// are optional per the contract — missing optional fields deserialize to default
    /// values (null for string, 0 for float) via JsonUtility.
    /// </summary>
    [System.Serializable]
    public class FinalFrame
    {
        public string type;
        public string response;
        public string transcript;
        public string intent;
        public float  confidence;
        public float  latency_ms;
    }
```

- [ ] **Step 2: Verify expected state**

The file now has both the old DTOs (`CommandRequest`, `IntentResponse`, `IntentParameters`) AND the new DTOs (`StartMessage`, `StopMessage`, `FrameEnvelope`, `FinalFrame`). `CorvusLatency` and the `CorvusController` class body are unchanged. No compile errors yet — just additions.

- [ ] **Step 3: DO NOT commit**

Leave the working tree dirty. Tasks 5-7 commit together at the end of Task 7 because Task 6 + 7 cross a state where `CorvusTest.cs` won't compile.

---

## Task 6: CorvusController — class body rewrite (no commit yet)

**Why:** Core of the migration. Strip Whisper plumbing; introduce state machine; route incoming frames by `type`; drive `AudioStreamer`; preserve all three existing events.

**Files:**
- Modify: `Assets/CLAWS/Backend/Networking/CorvusController.cs` (heavy edit)

- [ ] **Step 1: Update the `using` block at the top of the file**

Replace the existing `using` block (lines 1-9) with:

```csharp
using System;
using System.Collections;
using System.Collections.Generic;
using System.Threading.Tasks;
using UnityEngine;
using UnityEngine.Windows.Speech;
using CLAWS.Networking;
using PimDeWitte.UnityMainThreadDispatcher;
```

Removed: `using Whisper;`, `using Whisper.Utils;`. Added: `using System.Collections;` (for the `IEnumerator` timeout coroutine).

- [ ] **Step 2: Replace the `CommandRequest` class with nothing**

Find at line 13-17:
```csharp
    [System.Serializable]
    public class CommandRequest
    {
        public string command;
    }
```

Delete those 5 lines. The new DTOs from Task 5 stay; `IntentResponse`, `IntentParameters`, the new `StartMessage`/`StopMessage`/`FrameEnvelope`/`FinalFrame`, and `CorvusLatency` are all preserved.

- [ ] **Step 3: Replace the entire `CorvusController` class body**

Find the line `public class CorvusController : MonoBehaviour` (around line 50 in the original file) and replace EVERYTHING from that line through the closing brace of the class (around line 311 in the original, marked by `     }` followed by the namespace's closing brace) with:

```csharp
    public class CorvusController : MonoBehaviour
    {
        public enum State { IDLE, WAKE, STREAMING, SPEAKING }

        // Latency
        private System.Diagnostics.Stopwatch _stopWatch = new System.Diagnostics.Stopwatch();
        private long _ttsLatency;
        private long _serverProcessingLatency;
        private long _roundTripLatency;
        private long _networkOnlyLatency;

        // WebSocket connection to Python server
        private WebSocketClient _webSocketClient;

        // Wake word
        private KeywordRecognizer _wakeRecognizer;
        private string[] _wakeWords = new string[] { "hey corvus", "corvus" };

        [SerializeField] private string _serverUrl = "ws://localhost:8765";
        [SerializeField] private CorvusTTS _corvusTTS;
        [SerializeField] private LMCCWebSocketClient _lmcc;
        [SerializeField] private AudioStreamer _audioStreamer;

        [Tooltip("Seconds to wait for a final response before giving up.")]
        [SerializeField] private float _streamingTimeoutSec = 5.0f;

        private State _state = State.IDLE;
        private Coroutine _timeoutCoroutine;

        public bool IsConnected => _webSocketClient?.IsConnected ?? false;
        public State CurrentState => _state;

        /// <summary>
        /// Legacy 4-arg event preserved for back-compat with CorvusHalo and IntentDisplayUI.
        /// Fires once per final frame, on the Unity main thread.
        /// </summary>
        public event Action<string, float, string, CorvusLatency> OnIntentReceived;

        /// <summary>
        /// Structured event preserved for CorvusARBridge.Dispatch. Fires once per final
        /// frame, on the Unity main thread, with an IntentResponse populated from the
        /// new wire format (FinalFrame).
        /// </summary>
        public event Action<IntentResponse, CorvusLatency> OnIntentResponseReceived;

        public event Action OnWakeDetected;

        private async void Start()
        {
            try
            {
                _webSocketClient = new WebSocketClient(_serverUrl);
                _webSocketClient.OnMessageReceived += HandleMessageReceived;

                await _webSocketClient.ConnectAsync();
                _ = _webSocketClient.StartListeningAsync();

                if (_audioStreamer != null)
                    _audioStreamer.Initialize(_webSocketClient);
                else
                    Debug.LogError("[CorvusController] AudioStreamer reference not set");

                SetupWakeWord();

                Debug.Log("CORVUS initialized successfully");
            }
            catch (Exception ex)
            {
                Debug.LogError($"Failed to initialize CORVUS: {ex.Message}");
            }
        }

        private void SetupWakeWord()
        {
            try
            {
                _wakeRecognizer = new KeywordRecognizer(_wakeWords, ConfidenceLevel.Medium);
                _wakeRecognizer.OnPhraseRecognized += OnWakeWordDetected;
                _wakeRecognizer.Start();
                Debug.Log("CORVUS wake word listening: 'hey corvus'");
            }
            catch (Exception ex)
            {
                Debug.LogError($"Failed to start wake word recognition: {ex}");
            }
        }

        private void OnWakeWordDetected(PhraseRecognizedEventArgs args)
        {
            Debug.Log($"Wake word detected: {args.text}");
            if (_state != State.IDLE) return;

            _state = State.WAKE;
            OnWakeDetected?.Invoke();
            StartStreaming();
        }

        private async void StartStreaming()
        {
            if (_audioStreamer == null) { _state = State.IDLE; return; }

            try
            {
                var startMsg = JsonUtility.ToJson(new StartMessage());
                _stopWatch.Restart();
                await _webSocketClient.SendAsync(startMsg);

                _audioStreamer.StartStreaming();
                _state = State.STREAMING;

                if (_timeoutCoroutine != null) StopCoroutine(_timeoutCoroutine);
                _timeoutCoroutine = StartCoroutine(StreamingTimeoutWatchdog());
            }
            catch (Exception ex)
            {
                Debug.LogError($"[CorvusController] StartStreaming failed: {ex.Message}");
                _state = State.IDLE;
            }
        }

        private IEnumerator StreamingTimeoutWatchdog()
        {
            yield return new WaitForSeconds(_streamingTimeoutSec);
            if (_state == State.STREAMING)
            {
                Debug.LogWarning("[CorvusController] Streaming timeout — sending stop");
                _ = SendStopAsync();
                StopStreamingAndReturnIdle();
            }
        }

        private async Task SendStopAsync()
        {
            try
            {
                var stopMsg = JsonUtility.ToJson(new StopMessage());
                await _webSocketClient.SendAsync(stopMsg);
            }
            catch (Exception ex)
            {
                Debug.LogError($"[CorvusController] SendStop failed: {ex.Message}");
            }
        }

        private void StopStreamingAndReturnIdle()
        {
            if (_audioStreamer != null && _audioStreamer.IsStreaming)
                _audioStreamer.StopStreaming();
            _state = State.IDLE;
        }

        private async void HandleMessageReceived(string message)
        {
            try
            {
                if (string.IsNullOrEmpty(message)) return;

                var envelope = JsonUtility.FromJson<FrameEnvelope>(message);
                if (envelope == null || string.IsNullOrEmpty(envelope.type))
                {
                    Debug.LogWarning($"[CorvusController] Dropped malformed frame: {message}");
                    return;
                }

                switch (envelope.type)
                {
                    case "final":
                        await HandleFinalFrame(message);
                        break;

                    // "partial" frames are reserved by the contract but Python EVA server
                    // does not currently emit them. Silently ignore if one ever arrives.
                    case "partial":
                        break;

                    default:
                        Debug.LogWarning($"[CorvusController] Unknown frame type: {envelope.type}");
                        break;
                }
            }
            catch (Exception ex)
            {
                Debug.LogError($"[CorvusController] Error processing message: {ex.Message}");
            }
        }

        private async Task HandleFinalFrame(string message)
        {
            _stopWatch.Stop();
            _roundTripLatency = _stopWatch.ElapsedMilliseconds;

            var finalFrame = JsonUtility.FromJson<FinalFrame>(message);
            _serverProcessingLatency = (long)finalFrame.latency_ms;
            _networkOnlyLatency = _roundTripLatency - _serverProcessingLatency;

            UnityMainThreadDispatcher.Instance().Enqueue(StopStreamingAndReturnIdle);

            _state = State.SPEAKING;

            // Build the IntentResponse object the existing CorvusARBridge.Dispatch reads.
            // Python EVA server omits `parameters` in Phase 1 (single-label NN), so we
            // leave it null and rely on Dispatch's null-safe `p?.SLOT` accessors.
            var ir = new IntentResponse
            {
                intent     = string.IsNullOrEmpty(finalFrame.intent) ? "unhandled" : finalFrame.intent,
                confidence = finalFrame.confidence,
                response   = finalFrame.response ?? "",
                parameters = null,
                latency_ms = finalFrame.latency_ms,
                // status / matched_keywords / request_id / timestamp / transcript:
                // left at their zero-value defaults; Dispatch does not read them.
            };

            var latency = new CorvusLatency
            {
                STT = 0, // Unity no longer transcribes
                classification = _serverProcessingLatency,
                network = _networkOnlyLatency,
                roundTrip = _roundTripLatency,
                TTS = _ttsLatency, // set asynchronously after Dispatch decides to speak
                total = _roundTripLatency + _ttsLatency
            };

            UnityMainThreadDispatcher.Instance().Enqueue(() =>
            {
                // Legacy 4-arg event for CorvusHalo + IntentDisplayUI
                OnIntentReceived?.Invoke(ir.intent, ir.confidence, ir.response, latency);
                // Structured event for CorvusARBridge.Dispatch
                OnIntentResponseReceived?.Invoke(ir, latency);
            });

            LogToLMCC(finalFrame.transcript, ir.intent, ir.confidence);

            _state = State.IDLE;
        }

        private void LogToLMCC(string transcript, string intent, float confidence)
        {
            if (_lmcc == null)
            {
                Debug.LogWarning("LMCC not assigned - skipping log");
                return;
            }

            var payload = new Dictionary<string, object>()
            {
                {"transcript", transcript ?? ""},
                {"intent", intent ?? ""},
                {"confidence", confidence},
                {"timestamp", DateTime.UtcNow.ToString("o")}
            };

            _lmcc.SendJsonData(payload, "CORVUS", 4);
            Debug.Log($"Logged to LMCC: {intent} ({confidence})");
        }

        // For Testing — preserves the existing public API on CorvusController
        public void TriggerWakeDetected()
        {
            OnWakeDetected?.Invoke();
        }

        private async void OnDestroy()
        {
            try
            {
                if (_webSocketClient != null)
                    _webSocketClient.OnMessageReceived -= HandleMessageReceived;

                if (_audioStreamer != null && _audioStreamer.IsStreaming)
                    _audioStreamer.StopStreaming();

                if (IsConnected) await _webSocketClient.DisconnectAsync();

                if (_wakeRecognizer != null && _wakeRecognizer.IsRunning)
                {
                    _wakeRecognizer.Stop();
                    _wakeRecognizer.Dispose();
                }

                Debug.Log("CORVUS cleaned up successfully");
            }
            catch (Exception ex)
            {
                Debug.LogError($"Error during cleanup: {ex.Message}");
            }
        }
    }
```

(Make sure the namespace's closing brace `}` remains after this class — same shape as the original file.)

- [ ] **Step 4: Verify expected compile state**

After this edit, exactly ONE compile error remains: `CorvusTest.cs` calls `_corvusController.SendCommandAsync(phrase)` which no longer exists. That's fixed in Task 7. No other references to `SendCommandAsync` / `StartRecording` / `StopRecording` / `OnRecordStop` / `_whisper` / `_microphoneRecord` exist in `Assets/CLAWS/`:

```bash
grep -rIn "SendCommandAsync\|StartRecording\|StopRecording\|OnRecordStop\|_microphoneRecord\|_whisper\b\|using Whisper" Assets --include="*.cs"
```

Expected: only matches in `Assets/CLAWS/Testing/CorvusTest.cs` for `SendCommandAsync`. If any matches show up outside that file, STOP and report — the plan missed a reference.

The `WhisperManager` and `MicrophoneRecord` types still exist (the package is still installed); that's intentional — Task 10 removes the package after the smoke test.

- [ ] **Step 5: DO NOT commit**

Continue to Task 7. Tasks 5-7 commit together.

---

## Task 7: CorvusTest.cs — drop SendCommandAsync call

**Why:** `SendCommandAsync` was removed in Task 6. The keyboard harness has a built-in `SimulateIntent` fallback that exercises the same `Dispatch` path locally — make it the only path. Voice testing happens via the wake word.

**Files:**
- Modify: `Assets/CLAWS/Testing/CorvusTest.cs`

- [ ] **Step 1: Locate the `SendVoicePhraseAsync` method**

In `Assets/CLAWS/Testing/CorvusTest.cs`, find the `SendVoicePhraseAsync(int index)` method (currently lines 64-96 approximately). It calls `_corvusController.SendCommandAsync(phrase)` inside the `if (_corvusController.IsConnected)` branch.

- [ ] **Step 2: Replace `SendVoicePhraseAsync` with a synchronous `SimulateIntent`-only path**

Replace the entire `SendVoicePhraseAsync(int index)` method (including its `async Task` signature) with:

```csharp
        void SendVoicePhrase(int index)
        {
            if (index < 0 || index >= VoicePhrases.Length) return;

            string phrase = VoicePhrases[index];
            Debug.Log($"[CORVUS][KeyboardVoice] Simulating intent for phrase: \"{phrase}\"");

            // STT now runs on Python via the streaming protocol. The keyboard harness
            // exercises Dispatch locally without going through the wire — production
            // voice testing happens via the wake word.
            if (_corvusARBridge == null)
                _corvusARBridge = FindObjectOfType<CorvusARBridge>();

            if (_corvusARBridge == null)
            {
                Debug.LogError("[CORVUS][KeyboardVoice] No CorvusARBridge for simulation.");
                return;
            }

            SimulateFallback(index, phrase);
        }
```

- [ ] **Step 3: Update the `Update` method to call the new sync method**

Find the `Update` method (currently calls `_ = SendVoicePhraseAsync(...)` for each digit key). Replace every `_ = SendVoicePhraseAsync(N)` call with `SendVoicePhrase(N)`. The keys-to-index mapping is unchanged.

Concrete: in the digit-key dispatch (10 lines), change each line from
```csharp
            if (keyboard.digit1Key.wasPressedThisFrame)       _ = SendVoicePhraseAsync(0);
```
to
```csharp
            if (keyboard.digit1Key.wasPressedThisFrame)       SendVoicePhrase(0);
```
…repeating for digits 2-9 (indices 1-8).

- [ ] **Step 4: Remove the now-unused `_simulateWhenDisconnected` SerializeField**

The flag was gating the simulation fallback; simulation is now the only path. Remove the field declaration (currently around lines 17-18):

```csharp
        [Tooltip("If true and Python is unreachable, fall back to CorvusARBridge.SimulateIntent (skips NLU).")]
        [SerializeField] private bool _simulateWhenDisconnected;
```

Also remove `using System.Threading.Tasks;` from the top of the file if no other method needs it (the `async Task` signature is gone). Keep `using System;`, `using UnityEngine;`, `using UnityEngine.InputSystem;`, `using CLAWS.Networking;`.

- [ ] **Step 5: Verify expected compile state**

Run the grep from Task 6 Step 4 again:

```bash
grep -rIn "SendCommandAsync\|StartRecording\|StopRecording\|OnRecordStop\|_microphoneRecord\|_whisper\b\|using Whisper" Assets --include="*.cs"
```

Expected: zero matches. If any remain, STOP and report.

If Unity is reachable, open Unity and confirm the Console shows no compile errors after script reload. If not, walk through CorvusTest.cs by inspection and verify it has no remaining references to `SendCommandAsync` / `_simulateWhenDisconnected` / async patterns.

- [ ] **Step 6: Commit Tasks 5-7 together**

```bash
git add Assets/CLAWS/Backend/Networking/CorvusController.cs \
        Assets/CLAWS/Testing/CorvusTest.cs
git commit -m "$(cat <<'EOF'
refactor(corvus): state-machine controller + PCM streaming transport

Replaces Whisper-on-Unity + text-command protocol with WebSocket streaming
to the Python EVA server:
- New DTOs: StartMessage, StopMessage, FrameEnvelope, FinalFrame
- Removed: CommandRequest, Whisper plumbing (_whisper, _microphoneRecord,
  OnRecordStop, StartRecording, StopRecording, SendCommandAsync,
  Whisper.InitModel)
- New: state machine (IDLE/WAKE/STREAMING/SPEAKING), 5s timeout watchdog,
  AudioStreamer reference

Preserves:
- IntentResponse + IntentParameters + CorvusLatency classes
- Events OnIntentReceived, OnIntentResponseReceived, OnWakeDetected
- CorvusARBridge.Dispatch entry point (unchanged)

CorvusTest.cs's keyboard harness now always exercises SimulateIntent
locally — voice testing goes through the wake word + Python NLU.
EOF
)"
```

---

## Task 8: Corvus.prefab — YAML surgery

**Why:** The prefab currently has two dead `WhisperManager` and `MicrophoneRecord` MonoBehaviour components on the `CorvusController` GameObject. Remove them and add an `AudioStreamer` component wired to `CorvusController._audioStreamer`.

**Files:**
- Modify: `Assets/CLAWS/Phase-1/Features/AIA/Corvus.prefab`

This task edits Unity scene YAML directly. The plan walks through it surgically because Unity is not always available from the execution shell. If you have Unity open, you may alternatively perform these edits in the Inspector — the net result is the same.

**Reference: prefab structure as of baseline `ee599ff`** (line numbers approximate):
- Line 3-24: GameObject "CorvusController", `&1231975340194177141`
- Line 10-17: GameObject's `m_Component` list — 7 entries
- Line 13: `{fileID: 5878582405643141107}` — WhisperManager component (REMOVE)
- Line 14: `{fileID: 8268116696425847718}` — MicrophoneRecord component (REMOVE)
- Line 137-169: WhisperManager MonoBehaviour block `&5878582405643141107` (DELETE)
- Line 170-198: MicrophoneRecord MonoBehaviour block `&8268116696425847718` (DELETE)
- Line 212-228: CorvusController MonoBehaviour block `&5274132973516829717`
- Line 227-228: `_whisper: {fileID: 0}` and `_microphoneRecord: {fileID: 0}` (DELETE both lines)

- [ ] **Step 1: Remove the two component references from the GameObject's `m_Component` list**

Find:
```yaml
  m_Component:
  - component: {fileID: 269189780623091327}
  - component: {fileID: 3756909812807984232}
  - component: {fileID: 5878582405643141107}
  - component: {fileID: 8268116696425847718}
  - component: {fileID: 5606444795247275643}
  - component: {fileID: 5274132973516829717}
  - component: {fileID: 5577986797817232464}
```

Replace with (drop the two whisper component lines):
```yaml
  m_Component:
  - component: {fileID: 269189780623091327}
  - component: {fileID: 3756909812807984232}
  - component: {fileID: 5606444795247275643}
  - component: {fileID: 5274132973516829717}
  - component: {fileID: 5577986797817232464}
```

- [ ] **Step 2: Delete the WhisperManager and MicrophoneRecord MonoBehaviour blocks**

Find the block starting `--- !u!114 &5878582405643141107` (WhisperManager) and continuing through the line `--- !u!114 &5606444795247275643` (the start of the next block, which is CorvusTTS). Remove everything from `--- !u!114 &5878582405643141107` up to but NOT INCLUDING `--- !u!114 &5606444795247275643`.

The block to remove starts with:
```yaml
--- !u!114 &5878582405643141107
MonoBehaviour:
  m_ObjectHideFlags: 0
  m_CorrespondingSourceObject: {fileID: 0}
  m_PrefabInstance: {fileID: 0}
  m_PrefabAsset: {fileID: 0}
  m_GameObject: {fileID: 1231975340194177141}
  m_Enabled: 1
  m_EditorHideFlags: 0
  m_Script: {fileID: 11500000, guid: d9370225a2ca94276b870d5f87b0db55, type: 3}
  m_Name: 
  m_EditorClassIdentifier: com.whisper.unity::Whisper.WhisperManager
```

…and ends just before:
```yaml
--- !u!114 &5606444795247275643
MonoBehaviour:
  ...
  m_EditorClassIdentifier: Assembly-CSharp::CLAWS.Networking.CorvusTTS
```

That's 2 MonoBehaviour blocks (62 lines total) being removed.

- [ ] **Step 3: Remove the orphan `_whisper` and `_microphoneRecord` lines on CorvusController**

Find the CorvusController serialized fields block:
```yaml
  m_EditorClassIdentifier: Assembly-CSharp::CLAWS.Networking.CorvusController
  _serverUrl: ws://localhost:8765
  _corvusTTS: {fileID: 0}
  _lmcc: {fileID: 0}
  _whisper: {fileID: 0}
  _microphoneRecord: {fileID: 0}
```

Replace with:
```yaml
  m_EditorClassIdentifier: Assembly-CSharp::CLAWS.Networking.CorvusController
  _serverUrl: ws://localhost:8765
  _corvusTTS: {fileID: 0}
  _lmcc: {fileID: 0}
  _audioStreamer: {fileID: 7400000000000000001}
  _streamingTimeoutSec: 5
```

Note: `7400000000000000001` is a placeholder fileID that we'll assign to the new AudioStreamer block in the next step. Generate a fresh unique fileID — Unity uses large signed-int64 values; any value not already present in the file works. A safe approach: take any existing fileID in the prefab, add a large prime (e.g., `1000003`), then verify it doesn't collide:

```bash
# Pick a candidate and confirm it's not in the file:
grep -c "7400000000000000001" Assets/CLAWS/Phase-1/Features/AIA/Corvus.prefab
# Expected: 0 (after you write the value to _audioStreamer but before you add the block)
```

For the rest of this task, the example uses `7400000000000000001`. Substitute your chosen fileID.

- [ ] **Step 4: Add the AudioStreamer component reference to the GameObject's `m_Component` list**

Find:
```yaml
  m_Component:
  - component: {fileID: 269189780623091327}
  - component: {fileID: 3756909812807984232}
  - component: {fileID: 5606444795247275643}
  - component: {fileID: 5274132973516829717}
  - component: {fileID: 5577986797817232464}
```

Append the AudioStreamer ref:
```yaml
  m_Component:
  - component: {fileID: 269189780623091327}
  - component: {fileID: 3756909812807984232}
  - component: {fileID: 5606444795247275643}
  - component: {fileID: 5274132973516829717}
  - component: {fileID: 5577986797817232464}
  - component: {fileID: 7400000000000000001}
```

- [ ] **Step 5: Add the AudioStreamer MonoBehaviour block at the end of the prefab file**

At the very end of `Corvus.prefab`, after the last `--- !u!4` / `--- !u!114` / `--- !u!1` block but before any trailing newline-only lines, append:

```yaml
--- !u!114 &7400000000000000001
MonoBehaviour:
  m_ObjectHideFlags: 0
  m_CorrespondingSourceObject: {fileID: 0}
  m_PrefabInstance: {fileID: 0}
  m_PrefabAsset: {fileID: 0}
  m_GameObject: {fileID: 1231975340194177141}
  m_Enabled: 1
  m_EditorHideFlags: 0
  m_Script: {fileID: 11500000, guid: <AUDIOSTREAMER_META_GUID>, type: 3}
  m_Name: 
  m_EditorClassIdentifier: Assembly-CSharp::CLAWS.Networking.AudioStreamer
  _microphoneDevice: 
```

**Replace `<AUDIOSTREAMER_META_GUID>` with the 32-hex-char GUID you generated for `AudioStreamer.cs.meta` in Task 4 Step 2.** You can read it with:

```bash
grep "^guid:" Assets/CLAWS/Backend/Networking/AudioStreamer.cs.meta
```

- [ ] **Step 6: Verify the prefab parses**

Run a quick YAML sanity check:

```bash
python3 -c "import yaml; list(yaml.safe_load_all(open('Assets/CLAWS/Phase-1/Features/AIA/Corvus.prefab')))" && echo "YAML parse OK"
```

Expected: `YAML parse OK`. If parse fails, the offending line will be reported — most likely a YAML indentation issue or a missing block terminator. Restore from git and retry (`git checkout Assets/CLAWS/Phase-1/Features/AIA/Corvus.prefab`).

Also confirm the script GUID is correct:
```bash
echo "AudioStreamer GUID in meta:"
grep "^guid:" Assets/CLAWS/Backend/Networking/AudioStreamer.cs.meta
echo "AudioStreamer GUID in prefab:"
grep "m_Script.*type: 3" Assets/CLAWS/Phase-1/Features/AIA/Corvus.prefab | grep -v "d9370225\|3bc03a4c" | tail -1
```

The GUIDs in the last two lines must match.

- [ ] **Step 7: Confirm no stale Whisper references remain in the prefab**

```bash
grep -n "WhisperManager\|MicrophoneRecord\|_whisper:\|_microphoneRecord:" Assets/CLAWS/Phase-1/Features/AIA/Corvus.prefab
```

Expected: zero matches.

- [ ] **Step 8: If Unity is reachable, verify the prefab opens cleanly**

Open the prefab in Unity. The Inspector should show on the CorvusController GameObject:
- Transform
- AudioSource
- CorvusTTS
- CorvusController (with `_audioStreamer` wired to the new component)
- CorvusTest
- AudioStreamer (newly added)

No "Missing (Mono Script)" entries. If anything looks off, capture the symptom and STOP.

- [ ] **Step 9: Commit**

```bash
git add Assets/CLAWS/Phase-1/Features/AIA/Corvus.prefab
git commit -m "scene(prefab): swap Whisper components for AudioStreamer on Corvus.prefab"
```

---

## Task 9: End-to-end smoke test (manual)

**Why:** Verify the Unity port talks to the Python EVA server correctly.

**Files:** none modified.

- [ ] **Step 1: Start the Python EVA server**

In the separate Python repo (`CORVUS_PythonServer` on branch `AI-new-corvus-server`), from the repo root:

```bash
source .venv/bin/activate
corvus-eva
```

Expected log lines:
```
[INFO]    Starting CORVUS-EVA Server...
[SUCCESS] Classifier loaded (NNClassifier)
[SUCCESS] Whisper STT loaded
[SUCCESS] Silero VAD loaded
[SUCCESS] Server running on ws://0.0.0.0:8765
[INFO]    Waiting for Unity connection...
```

If the server fails to boot, check that the Whisper checkpoint and NN checkpoint exist (Python prints install hints if not). Resolve before continuing.

- [ ] **Step 2: Open `Assets/CLAWS/GEMINI.unity` in Unity and press Play**

Watch the Unity Console for:
- `WebSocket connected successfully!`
- `CORVUS wake word listening: 'hey corvus'`

If either is missing, capture the error and STOP — see "Failure modes" below.

- [ ] **Step 3: Say "hey corvus" then a phrase from the Python intent vocabulary**

Try one parameter-free intent (most reliable) and one that exercises a screen change:
- "Hey corvus, what is my heart rate?" — expects `intent: vitals_heart_rate`, vitals readout spoken.
- "Hey corvus, open the navigation menu." — expects `intent: open_menu_navigation`, ScreenManager opens screen 1.

Expected Console events in order:
1. `Wake word detected: hey corvus`
2. `[AudioStreamer] Streaming started`
3. (Python receives PCM, finalizes via VAD)
4. `[AudioStreamer] Streaming stopped`
5. Piper speaks the response
6. `Dispatch` fires the matching Unity action
7. Halo wake → answer → idle, DialogueManager shows the response text

- [ ] **Step 4: Also exercise the keyboard harness**

With the scene still in Play mode, press digit keys 1-9. Each should fire `SimulateIntent` locally (no Python required). Verify at least:
- Digit 1 → `open_menu_vitals` → vitals screen opens, "Opening vitals" or equivalent spoken.
- Digit 2 → `vitals_heart_rate` → vitals readout spoken (offline value).

- [ ] **Step 5: Failure modes — what to capture if anything fails**

| Symptom | Likely cause |
|---|---|
| `Failed to connect: ...` | Python server not running on `ws://localhost:8765`. Or `_serverUrl` in the inspector is set to a non-local host (check Inspector). |
| Wake word fires but no `[AudioStreamer] Streaming started` | `_audioStreamer` slot on `CorvusController` not wired in the prefab. |
| Streaming started but Python sees nothing | Microphone permission denied or wrong device. Look for `[AudioStreamer] No microphone devices available`. |
| `Streaming timeout — sending stop` | Python isn't returning `final` within 5 s — check Python logs. Or VAD never detected end-of-speech (long silence at start). |
| Piper speaks but Dispatch doesn't fire | Check that the `final` frame's `intent` field is being read — log the raw `message` in `HandleMessageReceived`. |
| Unity compile error after Play | A previous task left a stale reference. Run the grep from Task 6 Step 4. |

If any of these surface, capture the exact Console output and the Python server's stdout, and open a fresh debugging session — do NOT keep modifying the plan in place.

- [ ] **Step 6: If smoke passed, commit a note** (optional)

```bash
# Only if something noteworthy turned up — otherwise skip.
git commit --allow-empty -m "test: STT-offload smoke test passed on GEMINI"
```

---

## Task 10: Remove the whisper.unity package and model — GATED

**Why:** Frees ~77 MB of Whisper model from the build and removes the now-unused package. **Run this task ONLY after Task 9's smoke test passes**, so a regression doesn't conflate "package removal broke something" with "the port itself is broken."

**Files:**
- Modify: `Packages/manifest.json`
- Delete: `Assets/StreamingAssets/Whisper/ggml-tiny.en.bin` (+ meta)
- Delete: `Assets/StreamingAssets/Whisper/` folder (+ meta)
- Modified by Unity after reimport: `Packages/packages-lock.json`

- [ ] **Step 1: Confirm no surviving C# references**

```bash
grep -rIn "WhisperManager\|MicrophoneRecord\|using Whisper" Assets --include="*.cs"
```

Expected: zero matches. If any appear (likely from a scene we haven't touched, e.g., a CORVUS_Latency scene), STOP — those need to be cleaned up first, scope-permitting.

```bash
grep -n "com.whisper.unity" Packages/manifest.json
```

Expected: one match (the package line we'll remove).

- [ ] **Step 2: Edit `Packages/manifest.json`**

Open `Packages/manifest.json` and remove the entire line containing `"com.whisper.unity"`. Mind the trailing comma — JSON is strict. The line before and after must remain syntactically valid; specifically, if the whisper.unity line was followed by a comma and another dependency, the previous line's comma stays. If it was the last entry in `dependencies`, remove the trailing comma on the preceding line.

After editing, validate:

```bash
python3 -c "import json; json.load(open('Packages/manifest.json')); print('manifest OK')"
```

Expected: `manifest OK`.

- [ ] **Step 3: Open Unity and let it reimport**

Switch focus to Unity. Unity detects the manifest change, removes the package from `Library/PackageCache/`, and regenerates `Packages/packages-lock.json` without the whisper.unity entry.

Watch the Console for errors. If a scene still references `WhisperManager` / `MicrophoneRecord` via YAML, Unity shows them as "Missing (Mono Script)" components — that's harmless residue. The prefab we cleaned in Task 8 is the one the EVA pipeline uses.

- [ ] **Step 4: Delete the Whisper model + folder via the Unity Project window**

In Unity's Project window, navigate to `Assets/StreamingAssets/Whisper/`. Right-click → `Delete`. Unity will remove `ggml-tiny.en.bin`, `ggml-tiny.en.bin.meta`, and the folder's `.meta`.

If Unity is not reachable, delete from the shell instead (the package is already gone, so Unity's meta tracking can't get confused now):

```bash
rm -rf Assets/StreamingAssets/Whisper/
rm -f Assets/StreamingAssets/Whisper.meta
```

- [ ] **Step 5: Re-run the smoke test from Task 9**

Verify the GEMINI.unity scene still loads, wake-word fires, audio streams, and the EVA pipeline responds. Watch for any new errors that might have surfaced from the package removal.

- [ ] **Step 6: Commit**

```bash
git add Packages/manifest.json Packages/packages-lock.json
git add -A Assets/StreamingAssets   # only this folder, by name — captures deletes + folder meta
git commit -m "$(cat <<'EOF'
chore(corvus): remove whisper.unity package and bundled model

STT now runs on the Python EVA server via PCM streaming; no Whisper
on Unity. Frees ~77 MB from the build.

Pre-flight grep confirmed zero remaining C# references to WhisperManager,
MicrophoneRecord, or `using Whisper`. Scene-level orphan components in
non-prefab scenes (if any) become "Missing (Mono Script)" warnings —
harmless residue, cleaned up in follow-up if needed.
EOF
)"
```

---

## Self-Review

Run against the spec (`docs/superpowers/specs/2026-05-17-gemini-transport-port-design.md`):

**Spec coverage check:**
- §2 Goal: transport-only swap → Tasks 3-8 (no `CorvusARBridge.Dispatch` edit; events preserved).
- §4 Audit findings — all surfaced in the relevant task:
  - Whisper path dead → Task 6 strips it
  - Three events preserved → Task 6 declares all three
  - `CorvusTest` SendCommandAsync → Task 7
  - Prefab is source of truth → Task 8
  - Default WS URL `172.20.10.3` → Task 6 sets `ws://localhost:8765`
  - `parameters` always null → Task 6 builds `IntentResponse` with `parameters = null`
  - `intent: "unhandled"` → Task 6 coerces empty intent to `"unhandled"`
  - 87-label vocab covers Dispatch → confirmed in Task 9 smoke phrases
- §5 Architecture: state machine matches → Task 6
- §7 Wire contract: start/stop/PCM/final → Tasks 4 (PCM), 5+6 (DTOs + state machine)
- §8 Preservation contract: events, classes, files-not-touched → enforced by Hard constraints + Task 6's class body
- §9 Files: add/modify/delete table → Tasks 0, 1, 2, 3, 4, 6, 7, 8, 10 cover every row
- §10 CorvusController shape → Task 6 includes the exact rewrite
- §11 Test harness → Task 7
- §12 Error handling: timeout, disconnect, malformed, empty response → Task 6 handles each (StreamingTimeoutWatchdog, OnDestroy unwiring, FrameEnvelope null check, empty response is fine because Piper just speaks nothing)
- §13 Testing strategy: pure C# tests (Tasks 0-2) + manual integration (Task 9)
- §14 Risks: prefab YAML risk → Task 8 has surgical boundaries + YAML parse verification; meta GUID risk → Tasks 0+1+4 explicitly use fresh GUIDs; main-thread event firing → Task 6 wraps in `UnityMainThreadDispatcher.Instance().Enqueue`; WS URL → Task 6 uses `localhost`
- §15 Out of scope: not touched. Hard constraints explicitly preserve `CorvusARBridge`, `CorvusHalo`, `IntentDisplayUI`, `CorvusTTS`.

**Placeholder scan:** None. Every step has concrete code blocks or shell commands.

**Type consistency:**
- `OnIntentReceived(string, float, string, CorvusLatency)` — Task 6 declaration matches what `CorvusHalo` + `IntentDisplayUI` subscribe to.
- `OnIntentResponseReceived(IntentResponse, CorvusLatency)` — Task 6 declaration matches what `CorvusARBridge.Start` subscribes to.
- `FinalFrame` fields: `type`, `response`, `transcript`, `intent`, `confidence`, `latency_ms` — match the Python team's spec.
- `IntentResponse` shape: unchanged — Task 6 explicitly preserves it and constructs an instance from `FinalFrame`.
- `PcmConverter.FloatsToInt16` — same name in Task 1 implementation, Task 1 tests, Task 4 caller.
- `WebSocketClient.SendBinaryAsync` — added in Task 3, called by `AudioStreamer` in Task 4.
- `CorvusController._audioStreamer` SerializeField — declared in Task 6, wired in Task 8 (matching fileID).

**Ambiguity check:**
- "Append the AudioStreamer block at the end of the prefab" — explicit anchor: "after the last `--- !u!4` / `--- !u!114` / `--- !u!1` block". Safe.
- Fresh-GUID generation specified via `python3 -c "import uuid; print(uuid.uuid4().hex)"`.
- All commit messages quoted via heredoc where multi-line.
- "If Unity is reachable" branches present everywhere a Unity-side check is meaningful, with a fallback inspection path.

No issues found.

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-17-gemini-transport-port-plan.md`. Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task with two-stage review between tasks. Best when you're driving the execution from a coordinator session.
2. **Inline Execution** — execute tasks in the current session using `superpowers:executing-plans` with checkpoints between tasks. Best when you're working hands-on alongside the executor.

If you start a fresh Claude session inside `/mnt/c/Users/sunaa/Documents/CLAWS/GEMINI`, point it at this file and either skill will be able to take it from here.
