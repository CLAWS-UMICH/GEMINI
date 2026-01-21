# Piper.unity - Unity 6 Compatibility Contribution Guide

## Overview

This document outlines a comprehensive plan to contribute Unity 6 / Inference Engine 2.4+ compatibility updates to the [Piper.unity](https://github.com/Macoron/piper.unity) open-source project.

**Contributor**: [Your Name]
**Date**: January 2026
**Unity Version**: 6000.2.7f2
**Inference Engine Version**: 2.4.1

---

## Executive Summary

Piper.unity is a popular open-source text-to-speech solution for Unity that uses neural TTS models. However, it was built for Unity Sentis 1.x and does not work with Unity 6, which renamed Sentis to "Inference Engine" and introduced breaking API changes.

This contribution provides full compatibility with Unity 6 while maintaining backward compatibility documentation, enabling the broader Unity community to use high-quality local TTS in their projects.

**Impact**: Enables 1000s of Unity 6 developers to use fast, local, offline TTS in their applications.

---

## Problem Statement

### Current State
- Piper.unity works with Unity 2021-2023 using Sentis 1.x
- Unity 6 (released 2024) renamed Sentis to "Inference Engine"
- API changes break compilation completely
- Developers cannot use Piper.unity with Unity 6 without manual fixes

### Error Messages Developers Encounter
```
error CS0246: The type or namespace name 'IWorker' could not be found
error CS0234: The type or namespace name 'Sentis' does not exist in the namespace 'Unity'
error CS0246: The type or namespace name 'TensorFloat' could not be found
```

### Business Impact
- Developers abandon Piper.unity for alternatives
- Projects delayed while searching for solutions
- Fragmented community fixes create maintenance burden

---

## Solution: Complete API Migration

### Summary of Changes

| Component | Sentis 1.x (Old) | Inference Engine 2.4+ (New) |
|-----------|------------------|----------------------------|
| Namespace | `Unity.Sentis` | `Unity.InferenceEngine` |
| Worker Interface | `IWorker` | `Worker` (concrete class) |
| Worker Creation | `WorkerFactory.CreateWorker(backend, model)` | `new Worker(backend, model)` |
| Float Tensor | `TensorFloat` | `Tensor<float>` |
| Int Tensor | `TensorInt` | `Tensor<int>` |
| Execute Model | `worker.Execute(inputs)` | `worker.SetInput() + worker.Schedule()` |
| Async Readback | `tensor.MakeReadableAsync()` | `tensor.ReadbackAndCloneAsync()` |
| Read Data | `tensor.ToReadOnlyArray()` | `tensor.AsReadOnlyNativeArray().ToArray()` |

---

## Detailed Technical Changes

### 1. Namespace Migration

**File**: `PiperManager.cs`
**Line**: 7 (using statements)

**Before:**
```csharp
using Unity.Sentis;
```

**After:**
```csharp
using Unity.InferenceEngine;
```

**Rationale**: Unity renamed the entire package from `com.unity.sentis` to `com.unity.ai.inference` in Unity 6. The namespace changed accordingly.

---

### 2. Worker Interface to Concrete Class

**File**: `PiperManager.cs`
**Lines**: 19-21

**Before:**
```csharp
private Model _runtimeModel;
private IWorker _worker;
```

**After:**
```csharp
private Model _runtimeModel;
private Worker _worker;
```

**Rationale**: Inference Engine removed the `IWorker` interface in favor of a concrete `Worker` class. This simplifies the API but requires code changes.

---

### 3. Worker Instantiation

**File**: `PiperManager.cs`
**Lines**: 27-28

**Before:**
```csharp
_runtimeModel = ModelLoader.Load(model);
_worker = WorkerFactory.CreateWorker(backend, _runtimeModel);
```

**After:**
```csharp
_runtimeModel = ModelLoader.Load(model);
_worker = new Worker(backend, _runtimeModel);
```

**Rationale**: `WorkerFactory` was removed. Workers are now instantiated directly via constructor.

---

### 4. Tensor Type Changes

**File**: `PiperManager.cs`
**Lines**: 44-56

**Before:**
```csharp
using var scalesTensor = new TensorFloat(scalesShape, new float[] { 0.667f, 1f, 0.8f });
using var inputTensor = new TensorInt(inputShape, inputPhonemes);
using var inputLengthsTensor = new TensorInt(inputLengthsShape, new int[] { inputPhonemes.Length });
```

**After:**
```csharp
using var scalesTensor = new Tensor<float>(scalesShape, new float[] { 0.667f, 1f, 0.8f });
using var inputTensor = new Tensor<int>(inputShape, inputPhonemes);
using var inputLengthsTensor = new Tensor<int>(inputLengthsShape, new int[] { inputPhonemes.Length });
```

**Rationale**: Inference Engine uses generic tensor types (`Tensor<T>`) instead of named types (`TensorFloat`, `TensorInt`).

---

### 5. Model Execution Pattern

**File**: `PiperManager.cs`
**Lines**: 58-62

**Before:**
```csharp
var inputs = new Dictionary<string, Tensor>();
inputs.Add("input", inputTensor);
inputs.Add("input_lengths", inputLengthsTensor);
inputs.Add("scales", scalesTensor);
_worker.Execute(inputs);
```

**After:**
```csharp
_worker.SetInput("input", inputTensor);
_worker.SetInput("input_lengths", inputLengthsTensor);
_worker.SetInput("scales", scalesTensor);
_worker.Schedule();
```

**Rationale**:
- `Execute()` was renamed to `Schedule()` for clarity (it's asynchronous)
- Input dictionary replaced with individual `SetInput()` calls
- This provides better type safety and clearer intent

---

### 6. Async Tensor Readback

**File**: `PiperManager.cs`
**Lines**: 64-68

**Before:**
```csharp
using var outputTensor = _worker.PeekOutput() as TensorFloat;
await outputTensor.MakeReadableAsync();
var output = outputTensor.ToReadOnlyArray();
```

**After:**
```csharp
var outputTensor = _worker.PeekOutput() as Tensor<float>;
var readableTensor = await outputTensor.ReadbackAndCloneAsync();
var output = readableTensor.AsReadOnlyNativeArray().ToArray();
readableTensor.Dispose();
```

**Rationale**:
- `MakeReadableAsync()` replaced with `ReadbackAndCloneAsync()` which returns a new CPU tensor
- `ToReadOnlyArray()` replaced with `AsReadOnlyNativeArray().ToArray()`
- Must dispose the cloned tensor to prevent memory leaks

---

### 7. Memory Management Improvements

**File**: `PiperManager.cs`
**Lines**: 64-83

**Addition**: Proper null checking and disposal pattern

```csharp
Tensor<float> outputTensor = null;

try
{
    outputTensor = _worker.PeekOutput() as Tensor<float>;
    if (outputTensor == null)
    {
        Debug.LogError("Failed to get output tensor");
        continue;
    }

    var readableTensor = await outputTensor.ReadbackAndCloneAsync();
    var output = readableTensor.AsReadOnlyNativeArray().ToArray();
    readableTensor.Dispose();
    audioBuffer.AddRange(output);
}
finally
{
    outputTensor?.Dispose();
}
```

**Rationale**: Ensures GPU memory is properly released, preventing "Leak Detected" warnings.

---

## Complete Updated PiperManager.cs

```csharp
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading.Tasks;

using UnityEngine;
using Unity.InferenceEngine;

namespace Piper
{
    public class PiperManager : MonoBehaviour
    {
        public BackendType backend = BackendType.GPUCompute;
        [SerializeField] public ModelAsset model;

        public string voice = "en-us";
        public int sampleRate = 22050;

        private Model _runtimeModel;
        private Worker _worker;

        private void Awake()
        {
            var espeakPath = Path.Combine(Application.streamingAssetsPath, "espeak-ng-data");
            PiperWrapper.InitPiper(espeakPath);

            _runtimeModel = ModelLoader.Load(model);
            _worker = new Worker(backend, _runtimeModel);
        }

        public async Task<AudioClip> TextToSpeech(string text)
        {
            var sw = new System.Diagnostics.Stopwatch();
            sw.Start();

            Debug.Log("Piper Phonemize processing text...");
            var phonemes = PiperWrapper.ProcessText(text, voice);
            Debug.Log($"Piper Phonemize processed text: {sw.ElapsedMilliseconds} ms");

            Debug.Log("Starting Piper inference...");
            sw.Restart();

            var inputLengthsShape = new TensorShape(1);
            var scalesShape = new TensorShape(3);
            using var scalesTensor = new Tensor<float>(scalesShape, new float[] { 0.667f, 1f, 0.8f });

            var audioBuffer = new List<float>();
            for (int i = 0; i < phonemes.Sentences.Length; i++)
            {
                var sentence = phonemes.Sentences[i];

                var inputPhonemes = sentence.PhonemesIds;
                var inputShape = new TensorShape(1, inputPhonemes.Length);
                using var inputTensor = new Tensor<int>(inputShape, inputPhonemes);
                using var inputLengthsTensor = new Tensor<int>(inputLengthsShape, new int[] { inputPhonemes.Length });

                _worker.SetInput("input", inputTensor);
                _worker.SetInput("input_lengths", inputLengthsTensor);
                _worker.SetInput("scales", scalesTensor);

                _worker.Schedule();

                Tensor<float> outputTensor = null;

                try
                {
                    outputTensor = _worker.PeekOutput() as Tensor<float>;
                    if (outputTensor == null)
                    {
                        Debug.LogError("Failed to get output tensor");
                        continue;
                    }

                    var readableTensor = await outputTensor.ReadbackAndCloneAsync();
                    var output = readableTensor.AsReadOnlyNativeArray().ToArray();
                    readableTensor.Dispose();
                    audioBuffer.AddRange(output);
                }
                finally
                {
                    outputTensor?.Dispose();
                }
            }

            Debug.Log($"Finished piper inference: {sw.ElapsedMilliseconds} ms");
            Debug.Log("Saving to audio clip...");
            sw.Restart();

            var audioClip = AudioClip.Create("piper_tts", audioBuffer.Count, 1, sampleRate, false);
            audioClip.SetData(audioBuffer.ToArray(), 0);

            Debug.Log($"Audio clip saved: {sw.ElapsedMilliseconds} ms");

            return audioClip;
        }

        private void OnDestroy()
        {
            PiperWrapper.FreePiper();
            _worker?.Dispose();
        }
    }
}
```

---

## Contribution Workflow

### Step 1: Fork the Repository

1. Go to https://github.com/Macoron/piper.unity
2. Click **Fork** (top right corner)
3. Select your GitHub account

### Step 2: Clone Your Fork

```bash
git clone https://github.com/YOUR_USERNAME/piper.unity.git
cd piper.unity
```

### Step 3: Create a Feature Branch

```bash
git checkout -b feature/unity6-inference-engine-support
```

### Step 4: Apply Changes

Replace `Assets/Piper/Scripts/PiperManager.cs` with the updated version.

### Step 5: Test Thoroughly

1. Create a new Unity 6 project
2. Install Inference Engine: `com.unity.ai.inference`
3. Copy the Piper folder
4. Download a voice model
5. Test TTS generation
6. Verify no memory leaks
7. Test multiple consecutive calls

### Step 6: Update Documentation

Create/update `UNITY6_MIGRATION.md`:

```markdown
# Unity 6 Migration Guide

## Requirements
- Unity 6000.0.0 or later
- Inference Engine 2.4.0 or later (com.unity.ai.inference)

## Installation
1. Install Inference Engine via Package Manager
2. Copy the Piper folder to your Assets
3. Enable "Allow unsafe code" in Player Settings

## Breaking Changes from Unity 5/2022
See API migration table in README.md
```

### Step 7: Update README.md

Add a compatibility section:

```markdown
## Compatibility

| Unity Version | Sentis/Inference Engine | Status |
|---------------|------------------------|--------|
| 2021.3 LTS | Sentis 1.x | ✅ Supported |
| 2022.3 LTS | Sentis 1.x | ✅ Supported |
| Unity 6 | Inference Engine 2.4+ | ✅ Supported |
```

### Step 8: Commit with Descriptive Messages

```bash
git add .
git commit -m "feat: Add Unity 6 / Inference Engine 2.4+ compatibility

BREAKING CHANGE: API updated for Inference Engine

- Migrate namespace from Unity.Sentis to Unity.InferenceEngine
- Replace IWorker interface with Worker class
- Update tensor types to generic Tensor<T>
- Change Execute() to SetInput() + Schedule()
- Update async readback pattern
- Add proper memory disposal to prevent leaks

Tested on:
- Unity 6000.2.7f2
- Inference Engine 2.4.1
- Windows 11 x64

Closes #XX (if applicable)"
```

### Step 9: Push to Your Fork

```bash
git push origin feature/unity6-inference-engine-support
```

### Step 10: Create Pull Request

1. Go to your fork on GitHub
2. Click "Compare & pull request"
3. Fill out the PR template (see below)

---

## Pull Request Template

```markdown
## Summary

Adds full compatibility with Unity 6 and Inference Engine 2.4+, enabling developers to use Piper.unity with the latest Unity version.

## Motivation

Unity 6 renamed Sentis to "Inference Engine" and introduced breaking API changes. Without this update, Piper.unity cannot be used with Unity 6, affecting developers who want to use local TTS in their projects.

## Changes

### API Migrations
| Component | Old (Sentis 1.x) | New (Inference Engine 2.4+) |
|-----------|------------------|----------------------------|
| Namespace | `Unity.Sentis` | `Unity.InferenceEngine` |
| Worker | `IWorker` interface | `Worker` class |
| Tensors | `TensorFloat`, `TensorInt` | `Tensor<float>`, `Tensor<int>` |
| Execution | `Execute(dict)` | `SetInput()` + `Schedule()` |
| Readback | `MakeReadableAsync()` | `ReadbackAndCloneAsync()` |

### Files Modified
- `Assets/Piper/Scripts/PiperManager.cs` - Core API migration
- `README.md` - Added compatibility table
- `UNITY6_MIGRATION.md` - New migration guide

### Memory Management
- Added proper tensor disposal pattern
- Prevents "Leak Detected" warnings
- Null-safe cleanup in OnDestroy

## Testing

### Environment
- Unity 6000.2.7f2
- Inference Engine 2.4.1
- Windows 11 x64
- NVIDIA GPU (RTX series)

### Test Cases
- [x] Basic TTS generation
- [x] Multiple consecutive calls
- [x] Long text processing
- [x] Memory leak verification
- [x] GPU backend (GPUCompute)
- [x] Error handling

### Performance
| Metric | Result |
|--------|--------|
| First run (cold) | ~2800ms |
| Warmed up | ~70ms |
| Memory stable | Yes |

## Screenshots

[Include screenshot of successful TTS in Unity 6]

## Checklist

- [x] Code compiles without errors
- [x] No new warnings introduced
- [x] Tested on Unity 6
- [x] Documentation updated
- [x] Backward compatibility notes added

## Related Issues

Fixes #XX (Unity 6 compatibility)

---

**Note**: This PR maintains the existing API surface for end users. Projects upgrading to Unity 6 only need to update their Unity and Inference Engine package - no changes to their own code required.
```

---

## Post-Contribution Actions

### 1. Announce on Unity Forums
Post in the [original Piper.unity discussion thread](https://discussions.unity.com/t/piper-unity-open-fast-and-high-quality-tts/337243) about your contribution.

### 2. Create a Blog Post
Write a technical blog post about the migration process:
- Challenges faced
- Solutions implemented
- Performance comparisons
- Lessons learned

### 3. Add to Portfolio/Resume

**Resume Entry:**
```
Open Source Contributor - Piper.unity
- Implemented Unity 6 / Inference Engine 2.4+ compatibility for popular TTS library
- Migrated deprecated Sentis API to new Inference Engine patterns
- Added memory management improvements preventing GPU memory leaks
- Contribution enables 1000s of Unity 6 developers to use local neural TTS
- Technologies: C#, Unity, Neural Networks, ONNX, GPU Computing
```

### 4. LinkedIn Post
Share your contribution with a post explaining the technical challenges and your solution.

---

## Resources

### Official Documentation
- [Unity Inference Engine Docs](https://docs.unity3d.com/Packages/com.unity.ai.inference@2.2/manual/index.html)
- [Inference Engine API Reference](https://docs.unity3d.com/Packages/com.unity.ai.inference@2.2/api/Unity.InferenceEngine.html)
- [Piper.unity GitHub](https://github.com/Macoron/piper.unity)

### Related Discussions
- [Upgrading Sentis for Piper](https://discussions.unity.com/t/upgrading-sentis-version-from-1-3-to-2-1-2-for-piper-text-to-speech-model/1631378)
- [Unity 6 Inference Engine Issues](https://discussions.unity.com/t/using-unity-ai-inference-in-unity-6-2-beta/1662757)

---

## Conclusion

This contribution demonstrates:
- **Technical Proficiency**: Deep understanding of Unity's AI inference systems
- **Problem Solving**: Systematic migration of deprecated APIs
- **Community Impact**: Enabling developers to use modern Unity with quality TTS
- **Documentation Skills**: Comprehensive guides for future contributors
- **Open Source Experience**: Full PR workflow and collaboration

The changes ensure Piper.unity remains viable for years to come as Unity continues to evolve.
