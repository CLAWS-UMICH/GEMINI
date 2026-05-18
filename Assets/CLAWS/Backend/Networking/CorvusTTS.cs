using System;
using System.Threading.Tasks;
using UnityEngine;
using MixedReality.Toolkit;
using MixedReality.Toolkit.Subsystems;

namespace CLAWS.Networking
{
    public class CorvusTTS : MonoBehaviour
    {

        [SerializeField] private AudioSource _audioSource;

        private TextToSpeechSubsystem _tts;

        private void Start()
        {
            _tts = XRSubsystemHelpers.GetFirstRunningSubsystem<TextToSpeechSubsystem>();
            if (_tts == null)
            {
                Debug.LogError("[CorvusTTS] No running TextToSpeechSubsystem. " +
                               "Check Project Settings -> MRTK3 -> Subsystems and confirm Windows Text-To-Speech Subsystem is enabled.");
            }
        }

        public async Task<long> Speak(string text)
        {
            if (_audioSource == null)
            {
                Debug.LogError("[CorvusTTS] AudioSource not assigned!");
                return -1;
            }
            // Re-resolve in case the subsystem started after our Start().
            if (_tts == null)
                _tts = XRSubsystemHelpers.GetFirstRunningSubsystem<TextToSpeechSubsystem>();
            if (_tts == null)
            {
                Debug.LogError("[CorvusTTS] TextToSpeechSubsystem unavailable on this platform.");
                return -1;
            }

            try
            {
                var sw = System.Diagnostics.Stopwatch.StartNew();
                bool ok = await _tts.TrySpeak(text, _audioSource);
                sw.Stop();
                return ok ? sw.ElapsedMilliseconds : -1;
            }
            catch (Exception ex)
            {
                Debug.LogError($"[CorvusTTS] Error: {ex.Message}");
                return -1;
            }
        }

        // No model to warm; the OS synthesizer is ready as soon as the subsystem starts.
        public Task Warmup() => Task.CompletedTask;

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
