using System;
using System.Net.WebSockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine;

namespace CLAWS.Networking
{
    public class WebSocketClient
    {
        // WebSocket connection
        private ClientWebSocket _webSocket;

        // Python server URL
        private readonly string _serverURL;

        // Used to cancel async operations
        private CancellationTokenSource _cancellationTokenSource;

        public bool IsConnected => _webSocket?.State == WebSocketState.Open;

        public event Action<string> OnMessageReceived;

        // Constructor
        public WebSocketClient(string serverURL)
        {
            _serverURL = serverURL;
        }

        public async Task ConnectAsync()
        {
            try
            {
                // WebSocket instance
                _webSocket = new ClientWebSocket();

                // Cancellation token
                _cancellationTokenSource = new CancellationTokenSource();

                // Server connection Attempt
                Debug.Log($"Connecting to {_serverURL}");
                await _webSocket.ConnectAsync(
                    new Uri(_serverURL),
                    _cancellationTokenSource.Token
                );

                Debug.Log("WebSocket connected successfully!");
            }
            catch (Exception ex)
            {
                Debug.LogError($"Failed to connect: {ex.Message}");
                throw;
            }
        }

        public async Task SendAsync(string message)
        {
            // Check WebSocket connection
            if(!IsConnected)
            {
                Debug.LogError("Cannot send message: WebSocket is not connected");
                return;
            }

            try
            {
                // Convert string to bytes
                byte[] messageBytes = Encoding.UTF8.GetBytes(message);

                // Wrap bytes in ArraySegment
                var buffer = new ArraySegment<byte>(messageBytes);

                // Send message
                await _webSocket.SendAsync(
                    buffer,
                    WebSocketMessageType.Text,
                    true,
                    _cancellationTokenSource.Token
                );

                Debug.Log($"Sent: {message}");
            }
            catch (Exception ex)
            {
                Debug.LogError($"Failed to send message: {ex.Message}");
                throw;
            }
        }

        public async Task<string> ReceiveAsync()
        {
            // Check WebSocket connection
            if(!IsConnected)
            {
                Debug.LogError("Cannot receive: WebSocket is not connected");
                return null;
            }

            try
            {
                // Buffer to hold incoming data
                var buffer = new ArraySegment<byte>(new byte[8192]);

                // Receive data from server
                WebSocketReceiveResult result = await _webSocket.ReceiveAsync(
                    buffer,
                    _cancellationTokenSource.Token
                );

                // Convert bytes to string
                string message = Encoding.UTF8.GetString(buffer.Array, 0, result.Count);

                Debug.Log($"Received: {message}");
                return message;
            }
            catch (Exception ex)
            {
                Debug.LogError($"Failed to receive message: {ex.Message}");
                throw;
            }
        }

        public async Task DisconnectAsync()
        {
            try
            {
                // Cancel ongoing operations (send/receive)
                _cancellationTokenSource?.Cancel();

                // Close the WebSocket connection gracefully
                if(_webSocket?.State == WebSocketState.Open)
                {
                    await _webSocket.CloseAsync(
                        WebSocketCloseStatus.NormalClosure, // Normal close (not an error)
                        "Closing connection",               // Close message
                        CancellationToken.None              // New token (old one is cancelled)
                    );
                    Debug.Log("WebSocket disconnected");
                }
            }
            catch (Exception ex)
            {
                Debug.LogError($"Error during disconnect: {ex.Message}");
            }
            finally
            {
                // Dispose resources
                _webSocket?.Dispose();
                _cancellationTokenSource?.Dispose();
            }
        }

        public async Task StartListeningAsync()
        {
            if(!IsConnected)
            {
                Debug.LogError("Cannot start listening: not connected");
                return;
            }

            Debug.Log("Started listening for messages...");

            try
            {
                // Look until cancelled or disconnected
                while (IsConnected && !_cancellationTokenSource.Token.IsCancellationRequested)
                {
                    // Wait for a message
                    string message = await ReceiveAsync();

                    // Notify subscribers
                    OnMessageReceived?.Invoke(message);
                }
                
            }
            catch (OperationCanceledException)
            {
                Debug.Log("Listening cancelled");
            }
            catch (Exception ex)
            {
                Debug.LogError($"Error while listening: {ex.Message}");
            }
        }

    }
}