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
