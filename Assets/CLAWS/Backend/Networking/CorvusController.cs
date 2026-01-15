using System;
using System.Threading.Tasks;
using UnityEngine;
using CLAWS.Networking;

namespace CLAWS.Networking
{
    [System.Serializable]
    public class CommandRequest
    {
        public string command;
    }
    public class CorvusController : MonoBehaviour
    {
        // WebSocket connection to Python server
        private WebSocketClient _webSocketClient;

        // Server URL
        [SerializeField] private string _serverUrl = "ws://localhost:8765";

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

            }
            catch (Exception ex)
            {
                Debug.LogError($"Failed to initialize CORVUS: {ex.Message}");
            }
        }

        private void HandleMessageReceived(string message)
        {
            try
            {
                Debug.Log($"Processing message: {message}");

                // TODO: Parse JSON message

                // Temporary: Extract values manually
                string intent = "check_vitals";
                float confidence = 0.95f;
                float latency = 250f;

                // Event to notify UI
                OnIntentReceived?.Invoke(intent, confidence, latency);

                Debug.Log($"Intent: {intent}, Confidence: {confidence}, Latency: {latency}ms");

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

                // TODO: Format as JSON later
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

                Debug.Log("CORVUS cleaned up successfully");
            }
            catch (Exception ex)
            {
                Debug.LogError($"Error during cleanup: {ex.Message}");
            }
        }
 
     }

}