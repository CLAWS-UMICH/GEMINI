using System;
using System.Threading.Tasks;
using UnityEngine;
using Piper;

namespace CLAWS.Networking
{
    public class CorvusTTS : MonoBehaviour
    {
        
        [SerializeField] private PiperManager _piperManager;
        [SerializeField] private AudioSource _audioSource;

        private bool _isSpeaking = false;

        public async Task Speak(string text)
        {
            if (_piperManager == null || _audioSource == null)
            {
                Debug.LogError("[CorvusTTS] Components not assigned!");
                return;
            }

            try
            {
                _isSpeaking = true;

                var sw = System.Diagnostics.Stopwatch.StartNew();
                var audioClip = await _piperManager.TextToSpeech(text);
                sw.Stop();

                Debug.Log($"[CorvusTTS] Generated in {sw.ElapsedMilliseconds}ms \"{text}\"");

                // Clean up old clip
                if (_audioSource.clip != null)
                    Destroy(_audioSource.clip);

                // Play new clip
                _audioSource.clip = audioClip;
                _audioSource.Play();

            } catch (Exception ex)
            {
                Debug.LogError($"[CorvusTTS] Error: {ex.Message}");
                _isSpeaking = false;
            }
        }

        public async Task Warmup()
        {
            await _piperManager.TextToSpeech("warmup");
            Destroy(clip);
            Debug.Log("[CorvusTTS] Warmup complete");
        }

        public bool IsSpeaking()
        {
            return _audioSource != null && _audioSource.isPlaying;
        }

        public void Stop()
        {
            if (_audioSource != null)
            {
                _audioSource.Stop();
            }
            _isSpeaking = false;
        }

        private void OnDestroy()
        {
            if (_audioSource != null && _audioSource.clip != null)
            {
                Destroy(_audioSource.clip);
            }
        }

    }
}