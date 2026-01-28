using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using UnityEngine;
using UnityEngine.Windows.Speech;
using Whisper;
using Whisper.Utils;
using CLAWS.Networking;

namespace CLAWS.Networking
{
    [System.Serializable]
    public class CommandRequest
    {
        public string command;
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
    }

    public class CorvusController : MonoBehaviour
    {
        // WebSocket connection to Python server
        private WebSocketClient _webSocketClient;
        private string _lastCommand;

        private KeywordRecognizer _wakeRecognizer;
        private string[] _wakeWords = new string[] {"hey corvus", "corvus"};

        // Server URL
        [SerializeField] private string _serverUrl = "ws://localhost:8765";
        [SerializeField] private CorvusTTS _corvusTTS;
        [SerializeField] private LMCC _lmcc;
        [SerializeField] private WhisperManager _whisper;
        [SerializeField] private MicrophoneRecord _microphoneRecord;

        // Check CORVUS connection
        public bool IsConnected => _webSocketClient?.IsConnected ?? false;

        // Fire event (received from Python)
        public event Action<string, float, float> OnIntentReceived;

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

        private string GetResponseForIntent(string intent, float confidence)
        {
            switch(intent)
            {
                case "check_vitals":
                    return "Checking your vitals now.";
                case "navigate_to_airlock":
                    return "Navigating to airlock.";
                case "check_oxygen_level":
                    return "Checking oxygen level.";
                case "check_battery":
                    return "Checking battery status.";
                case "emergency_abort":
                    return "Emergency abort initiated!";
                default:
                    if (confidence < 0.5f)
                        return "Sorry, I didn't understand. Please repeat.";
                    return $"Processing {intent.Replace("_", " ")}.";
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
            StartRecording();
        }

        private void HandleMessageReceived(string message)
        {
            try
            {
                Debug.Log($"Processing message: {message}");

                // Parse JSON message
                var response = JsonUtility.FromJson<IntentResponse>(message);

                // Event to notify UI
                OnIntentReceived?.Invoke(response.intent, response.confidence, response.latency_ms);

                Debug.Log($"Intent: {response.intent}, Confidence: {response.confidence}, Latency: {response.latency_ms}ms");

                // Log to LMCC for mission coordination
                LogToLMCC(_lastCommand, response.intent, response.confidence);

                // Speak the response
                if (_corvusTTS != null)
                {
                    string spokenText = GetResponseForIntent(response.intent, response.confidence);
                    _ = _corvusTTS.Speak(spokenText);
                }
                 

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
            }
        }

        public void StopRecording()
        {
            if(_microphoneRecord != null && _microphoneRecord.IsRecording)
            {
                _microphoneRecord.StopRecord();
                Debug.Log("CORVUS: Recording stopped");
            }
        }

        // Whisper finishes recording -> transcribe -> send to Python
        private async void OnRecordStop(AudioChunk recordedAudio)
        {
            var result = await _whisper.GetTextAsync(recordedAudio.Data, recordedAudio.Frequency, recordedAudio.Channels);
            if(result == null) return;

            Debug.Log($"CORVUS Transcription: {result.Result}");
            await SendCommandAsync(result.Result);
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