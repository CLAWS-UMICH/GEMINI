using System;
using System.Collections;
using System.Collections.Generic;
using System.Threading.Tasks;
using UnityEngine;
using UnityEngine.Windows.Speech;
using CLAWS.Networking;
using PimDeWitte.UnityMainThreadDispatcher;

namespace CLAWS.Networking
{
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

}