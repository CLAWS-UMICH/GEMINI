/*
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
    private string[] wakeWords = new string[] { "corvus", "hello" }; // you can add variants
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
            wakeRecognizer = new KeywordRecognizer(wakeWords);
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
        Debug.Log($"Wake phrase recognized: {args.text})");
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
        Debug.Log($"DICTATION FINAL: {transcript}");

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

*/
using Stopwatch = System.Diagnostics.Stopwatch;
using UnityEngine;
using UnityEngine.UI;
using Button = UnityEngine.UI.Button;
using Toggle = UnityEngine.UI.Toggle;
using System;
using System.IO;
using System.Threading.Tasks;
using UnityEngine.Serialization;
using Whisper.Utils;
using Whisper;
using TMPro;
using Microsoft.MixedReality.GraphicsTools.Editor;



/// <summary>
/// Record audio clip from microphone and make a transcription.
/// </summary>
public class CorvusController : MonoBehaviour
    {
        public WhisperManager whisper;
        public MicrophoneRecord microphoneRecord;
        public bool streamSegments = true;
        public bool printLanguage = true;

        [Header("UI")] 
        public Button button;
        public TextMeshProUGUI outputText;
        public Text timeText;
        public Dropdown languageDropdown;
        public Toggle translateToggle;
        public Toggle vadToggle;
        public ScrollRect scroll;
        
        private string _buffer;
        /*
        private async void Start()
        {
            bool loaded = await whisper.IsLoaded;

            if (!loaded)
            {
                Debug.Log("Loading Whisper model...");
                await whisper.InitModel();   // <-- this is the key line for this package
            }

            Debug.Log("Whisper model ready!");
        }
        */
        private async void Start()
        {
            // Wait until Whisper model finishes loading
            while (!whisper.IsLoaded)
            {
                Debug.Log("Waiting for Whisper model to load...");
                await Task.Delay(100);
            }

            Debug.Log("Whisper model loaded!");
        }

        private void Awake()
        {
            whisper.OnNewSegment += OnNewSegment;
            whisper.OnProgress += OnProgressHandler;
            
            microphoneRecord.OnRecordStop += OnRecordStop;
            
            button.onClick.AddListener(OnButtonPressed);
            languageDropdown.value = languageDropdown.options
                .FindIndex(op => op.text == whisper.language);
            languageDropdown.onValueChanged.AddListener(OnLanguageChanged);

            translateToggle.isOn = whisper.translateToEnglish;
            translateToggle.onValueChanged.AddListener(OnTranslateChanged);

            vadToggle.isOn = microphoneRecord.vadStop;
            vadToggle.onValueChanged.AddListener(OnVadChanged);
        }

        private void OnVadChanged(bool vadStop)
        {
            microphoneRecord.vadStop = vadStop;
        }

        private void OnButtonPressed()
        {
            if (!microphoneRecord.IsRecording)
            {
                microphoneRecord.StartRecord();
            }
            else
            {
                microphoneRecord.StopRecord();
            }
        }
        
        private async void OnRecordStop(AudioChunk recordedAudio)
        {
            _buffer = "";

            var sw = new Stopwatch();
            sw.Start();
            
            var res = await whisper.GetTextAsync(recordedAudio.Data, recordedAudio.Frequency, recordedAudio.Channels);
            if (res == null || !outputText) 
                return;

            var time = sw.ElapsedMilliseconds;
            var rate = recordedAudio.Length / (time * 0.001f);
            timeText.text = $"Time: {time} ms\nRate: {rate:F1}x";

            var text = res.Result;
            if (printLanguage)
                text += $"\n\nLanguage: {res.Language}";
            
            outputText.text = text;
            UiUtils.ScrollDown(scroll);
        }
        
        private void OnLanguageChanged(int ind)
        {
            var opt = languageDropdown.options[ind];
            whisper.language = opt.text;
        }
        
        private void OnTranslateChanged(bool translate)
        {
            whisper.translateToEnglish = translate;
        }

        private void OnProgressHandler(int progress)
        {
            if (!timeText)
                return;
            timeText.text = $"Progress: {progress}%";
        }
        
        private void OnNewSegment(WhisperSegment segment)
        {
            if (!streamSegments || !outputText)
                return;

            _buffer += segment.Text;
            outputText.text = _buffer + "...";
            UiUtils.ScrollDown(scroll);
        }
    }
