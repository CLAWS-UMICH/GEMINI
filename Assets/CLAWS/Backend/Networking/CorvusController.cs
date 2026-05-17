using System;
using System.Collections;
using System.Collections.Generic;
using System.Threading.Tasks;
using UnityEngine;
using UnityEngine.Windows.Speech;
using Whisper;
using Whisper.Utils;
using CLAWS.Networking;
using PimDeWitte.UnityMainThreadDispatcher;

namespace CLAWS.Networking
{
    [System.Serializable]
    public class CommandRequest
    {
        public string command;
    }
    [System.Serializable]
    public class IntentParameters
    {
        public string COORDINATE_TARGET_NAME;
        public string NAVIGATION_TARGET_NAME;
        public string WAYPOINT_NAME;
        public string TASK_NAME;
    }

    [System.Serializable]
    public class IntentResponse
    {
        public string status;
        public string intent;
        public float confidence;
        public string[] matched_keywords;
        public string request_id;
        public float latency_ms;
        public string timestamp; 
        public string response;
        public IntentParameters parameters;
    }
    public class CorvusLatency 
    {
        public long STT;
        public long classification;
        public long network;
        public long roundTrip;
        public long TTS;
        public long total;
    }

    public class CorvusController : MonoBehaviour
    {
        // Latency
        private System.Diagnostics.Stopwatch _stopWatch = new System.Diagnostics.Stopwatch();
        private long _ttsLatency;
        private long _sttLatency;
        private long _roundTripLatency;
        private long _networkOnlyLatency;
        

        // WebSocket connection to Python server
        private WebSocketClient _webSocketClient;
        private string _lastCommand;

        private KeywordRecognizer _wakeRecognizer;
        private string[] _wakeWords = new string[] {"hey corvus", "corvus"};

        [Tooltip("Max seconds to keep recording after wake before giving up if VAD never fires.")]
        [SerializeField] private float _recordingSafetyTimeoutSec = 6f;
        private Coroutine _recordingTimeoutCo;

        // Server URL
        [SerializeField] private string _serverUrl = "ws://172.20.10.3:8765";
        [SerializeField] private CorvusTTS _corvusTTS;
        [SerializeField] private LMCCWebSocketClient _lmcc;
        [SerializeField] private WhisperManager _whisper;
        [SerializeField] private MicrophoneRecord _microphoneRecord;

        // Check CORVUS connection
        public bool IsConnected => _webSocketClient?.IsConnected ?? false;

        // Fire event (received from Python)
        public event Action<string, float, string, CorvusLatency> OnIntentReceived;
        public event Action<IntentResponse, CorvusLatency> OnIntentResponseReceived;
        public event Action OnWakeDetected;

        private async void Start()
        {
            try
            {
                // Create WebSocket client
                _webSocketClient = new WebSocketClient(_serverUrl);

                // Subscribe to incoming messages
                _webSocketClient.OnMessageReceived += HandleMessageReceived;

                // Connect to Python server
                await _webSocketClient.ConnectAsync();

                // Start listening for messages
                _ = _webSocketClient.StartListeningAsync();

                Debug.Log("CORVUS initialized successfully");

                if(_microphoneRecord != null)
                {
                    await _whisper.InitModel();
                    _microphoneRecord.OnRecordStop += OnRecordStop;
                }

                SetupWakeWord();

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
                Debug.Log("CORVUS wake word listening: 'hey corvus");
            }
            catch (Exception ex)
            {
                Debug.LogError($"Failed to start wake word recognition: {ex}");
            }
        }

        private void OnWakeWordDetected(PhraseRecognizedEventArgs args)
        {
            Debug.Log($"Wake word detected: {args.text}");

            // Release the system speech service so Unity's Microphone API can own the mic.
            // Without this, Microphone.Start returns a clip but the buffer is silent on HoloLens.
            StopWakeRecognizer();

            OnWakeDetected?.Invoke();
            StartRecording();
        }

        private void StopWakeRecognizer()
        {
            try
            {
                if (_wakeRecognizer != null && _wakeRecognizer.IsRunning)
                    _wakeRecognizer.Stop();
            }
            catch (Exception ex)
            {
                Debug.LogWarning($"StopWakeRecognizer failed: {ex.Message}");
            }
        }

        private void RestartWakeRecognizer()
        {
            try
            {
                if (_wakeRecognizer != null && !_wakeRecognizer.IsRunning)
                    _wakeRecognizer.Start();
            }
            catch (Exception ex)
            {
                Debug.LogWarning($"RestartWakeRecognizer failed: {ex.Message}");
            }
        }

        private void HandleMessageReceived(string message)
        {
            try
            {
                // Null Checker
                if (string.IsNullOrEmpty(message)) return;

                _stopWatch.Stop();
                _roundTripLatency = _stopWatch.ElapsedMilliseconds;
                
                Debug.Log($"Processing message: {message}");

                // Parse JSON message
                var response = JsonUtility.FromJson<IntentResponse>(message);
                Debug.Log($"Parsed - intent: {response?.intent}, confidence: {response?.confidence}"); 
                _networkOnlyLatency = (long)(_roundTripLatency - response.latency_ms);

                UnityMainThreadDispatcher.Instance().Enqueue(() =>
                {
                    StopRecording();
                    RestartWakeRecognizer();
                });

                // Latency (TTS now happens in CorvusARBridge after the dispatcher resolves the spoken text)
                CorvusLatency clatency = new CorvusLatency();
                clatency.STT = _sttLatency;
                clatency.classification = (long)(response.latency_ms);
                clatency.network = _networkOnlyLatency;
                clatency.roundTrip = _roundTripLatency;
                clatency.TTS = _ttsLatency;
                clatency.total = _sttLatency + _roundTripLatency + _ttsLatency;

                // Events to notify UI / bridge (legacy 4-arg kept for back-compat)
                UnityMainThreadDispatcher.Instance().Enqueue(() =>
                {
                    OnIntentReceived?.Invoke(response.intent, response.confidence, response.response, clatency);
                    OnIntentResponseReceived?.Invoke(response, clatency);
                });

                Debug.Log($"Intent: {response.intent}, Confidence: {response.confidence}, Latency: {response.latency_ms}ms");

                // Log to LMCC for mission coordination
                LogToLMCC(_lastCommand, response.intent, response.confidence);
            }
            catch (Exception ex)
            {
                Debug.LogError($"Error processing message: {ex.Message}");
            }
        }

        public async Task SendCommandAsync(string command)
        {
            if (!IsConnected)
            {
                Debug.LogError("Cannot send command: Not connected to server");
                return;
            }

            try
            {
                Debug.Log($"Sending command: {command}");

                _lastCommand = command;
                var request = new CommandRequest { command = command };
                string json = JsonUtility.ToJson(request);

                Debug.Log($"Sending: {json}");
                _stopWatch.Restart();
                await _webSocketClient.SendAsync(json);
                
            }
            catch (Exception ex)
            {
                Debug.LogError($"Failed to send command: {ex.Message}");
            }
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
                {"transcript", transcript},
                {"intent", intent},
                {"confidence", confidence},
                {"timestamp", DateTime.UtcNow.ToString("o")}
            };

            _lmcc.SendJsonData(payload, "CORVUS", 4);
            Debug.Log($"Logged to LMCC: {intent} ({confidence})");
        }

        public void StartRecording()
        {
            if(_microphoneRecord != null && !_microphoneRecord.IsRecording)
            {
                _microphoneRecord.StartRecord();
                Debug.Log("CORVUS: Recording started");

                if (_recordingTimeoutCo != null) StopCoroutine(_recordingTimeoutCo);
                _recordingTimeoutCo = StartCoroutine(RecordingSafetyTimeout());
            }
        }

        public void StopRecording()
        {
            if (_recordingTimeoutCo != null)
            {
                StopCoroutine(_recordingTimeoutCo);
                _recordingTimeoutCo = null;
            }

            if(_microphoneRecord != null && _microphoneRecord.IsRecording)
            {
                _microphoneRecord.StopRecord();
                Debug.Log("CORVUS: Recording stopped");
            }
        }

        // Guards against the "user said nothing after wake word" case where VAD never fires.
        private IEnumerator RecordingSafetyTimeout()
        {
            yield return new WaitForSeconds(_recordingSafetyTimeoutSec);
            if (_microphoneRecord != null && _microphoneRecord.IsRecording)
            {
                Debug.LogWarning("CORVUS: Recording safety timeout reached, stopping");
                _microphoneRecord.StopRecord();
            }
            RestartWakeRecognizer();
            _recordingTimeoutCo = null;
        }

        // Whisper finishes recording -> transcribe -> send to Python
        private async void OnRecordStop(AudioChunk recordedAudio)
        {
            try
            {
                var sw = System.Diagnostics.Stopwatch.StartNew();
                var result = await _whisper.GetTextAsync(recordedAudio.Data, recordedAudio.Frequency, recordedAudio.Channels);
                sw.Stop();
                _sttLatency = sw.ElapsedMilliseconds;

                if (result == null || string.IsNullOrWhiteSpace(result.Result))
                {
                    Debug.LogWarning("CORVUS: Empty transcription, skipping send");
                    UnityMainThreadDispatcher.Instance().Enqueue(RestartWakeRecognizer);
                    return;
                }

                Debug.Log($"CORVUS Transcription: {result.Result}");
                await SendCommandAsync(result.Result);
                // Note: happy-path restart happens in HandleMessageReceived once the server replies.
            }
            catch (Exception ex)
            {
                Debug.LogError($"CORVUS OnRecordStop failed: {ex.Message}");
                UnityMainThreadDispatcher.Instance().Enqueue(RestartWakeRecognizer);
            }
        }

        // For Testing
        public void TriggerWakeDetected()
        {
            OnWakeDetected?.Invoke();
        }


        private async void OnDestroy()
        {
            try
            {
                // Unsubscribe from event to prevent memory leaks
                if (_webSocketClient != null)
                {
                    _webSocketClient.OnMessageReceived -= HandleMessageReceived;
                }

                // Disconnect gracefully
                if (IsConnected)
                {
                    await _webSocketClient.DisconnectAsync();
                }

                // Unsubscribe from Whisper
                if (_microphoneRecord != null) {
                    _microphoneRecord.OnRecordStop -= OnRecordStop;
                }

                // Stop wake word recognition
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

}