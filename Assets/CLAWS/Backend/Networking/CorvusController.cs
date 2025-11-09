using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Windows.Speech;
using Newtonsoft.Json.Linq;
using Newtonsoft.Json;

// Last Updated:
//     Molly M. -- 11/9/2025

// add in cases for menu navigation, etc. that does not require LLM processing before sending to LMCC

public class VoiceAssistant : MonoBehaviour
{
    public LMCC lmcc;
    private KeywordRecognizer wakeRecognizer;
    private string[] wakeWords = new string[] { "hey corvus", "corvus" }; // you can add variants
    private DictationRecognizer dictationRecognizer;
    private bool isListening = false;
    private float maxListenSeconds = 10f;
    private float dictationStartTime;

    void Start()
    {
        SetupWakeRecognizer();
        SetupDictation();
    }

    void SetupWakeRecognizer()
    {
        try
        {
            wakeRecognizer = new KeywordRecognizer(wakeWords, ConfidenceLevel.Medium);
            wakeRecognizer.OnPhraseRecognized += OnWakePhrase;
            wakeRecognizer.Start();
            Debug.Log("Wake recognizer started");
        }
        catch (Exception ex)
        {
            Debug.LogError("Failed to start KeywordRecognizer: " + ex);
        }
    }

    void SetupDictation()
    {
        dictationRecognizer = new DictationRecognizer();
        dictationRecognizer.DictationResult += (text, confidence) =>
        {
            Debug.Log($"Dictation result: {text} (confidence {confidence})");
            OnFinalTranscript(text, (float)confidence);
        };
        dictationRecognizer.DictationHypothesis += (text) =>
        {
            Debug.Log($"Hypothesis: {text}");
        };
        dictationRecognizer.DictationComplete += (completionCause) =>
        {
            Debug.Log("Dictation complete: " + completionCause);
            StopListening();
        };
        dictationRecognizer.DictationError += (error, hresult) =>
        {
            Debug.LogError($"Dictation error: {error} (hr:{hresult})");
            StopListening();
        };
    }

    private void OnWakePhrase(PhraseRecognizedEventArgs args)
    {
        Debug.Log($"Wake phrase recognized: {args.text} (confidence {args.confidence})");
        // Optionally check confidence or require double-wake
        StartListening();
    }

    private void StartListening()
    {
        if (isListening) return;
        try
        {
            dictationRecognizer.Start();
            isListening = true;
            dictationStartTime = Time.time;
            Debug.Log("Dictation started");
            // optional: show UI indicator
        }
        catch (Exception ex)
        {
            Debug.LogError("Failed to start dictation: " + ex);
            isListening = false;
        }
    }

    private void StopListening()
    {
        if (!isListening) return;
        try
        {
            dictationRecognizer.Stop();
        }
        catch (Exception) { }
        isListening = false;
        Debug.Log("Stopped listening");
    }

    void Update()
    {
        // safety: stop if exceeds max listen seconds
        if (isListening && Time.time - dictationStartTime > maxListenSeconds)
        {
            Debug.Log("Max listen time reached, stopping");
            StopListening();
        }
    }

    private void OnFinalTranscript(string transcript, float confidence)
    {
        // here is where to decide if further processing is needed before sending to LMCC

        // --- Build message object to send to LMCC ---
        var payload = new Dictionary<string, object>()
        {
            { "transcript", transcript },
            { "confidence", confidence },
            { "timestamp", DateTime.UtcNow.ToString("o") },
            { "context", GetContextSnapshot() }
        };

        // Send to LMCC as "CORVUS_TEXT" in case type "CORVUS" (clientId 4 -> LMCC)
        lmcc.SendJsonData(payload, "voice_text", 4);
    }

    private Dictionary<string, object> GetContextSnapshot()
    {
        // return relevant context data as needed
        // brainstorm with team on what context is useful
        // Vitals, location, current task, etc.
        return new Dictionary<string, object>()
        {
            { "example_key", "example_value" }
        };
    }

    private void OnDestroy()
    {
        if (wakeRecognizer != null && wakeRecognizer.IsRunning) wakeRecognizer.Stop();
        if (dictationRecognizer != null && dictationRecognizer.Status == SpeechSystemStatus.Running) dictationRecognizer.Stop();
    }
}

