using System;
using UnityEngine;
using UnityEngine.InputSystem;
using Piper;

namespace CLAWS.Testing
{
    public class PiperTest : MonoBehaviour
    {
        [SerializeField] private PiperManager _piperManager;
        [SerializeField] private AudioSource _audioSource;

        // Test phrase
        private string _testPhrase = "Hello, this is a test of the Piper text to speech system.";

        private void Update()
        {
            var keyboard = Keyboard.current;
            if (keyboard == null) return;

            // Press T to test TTS
            if (keyboard.tKey.wasPressedThisFrame)
            {
                _ = TestTTS();
            }

        }

        private async System.Threading.Tasks.Task TestTTS()
        {
            if (_piperManager == null || _audioSource == null)
            {
                Debug.LogError("[PiperTest] Components not assigned!");
                return;
            }
            
            try {
                Debug.Log($"[PiperTest] Generating: {_testPhrase}");

                var sw = System.Diagnostics.Stopwatch.StartNew();
                var audioClip = await _piperManager.TextToSpeech(_testPhrase);
                sw.Stop();

                Debug.Log($"[PiperTest] Generated in {sw.ElapsedMilliseconds}ms");

                // Clean up old clip
                if(_audioSource.clip != null)
                    Destroy(_audioSource.clip);

                // Play new clip
                _audioSource.clip = audioClip;
                _audioSource.Play();
            }
            catch (Exception ex)
            {
                Debug.LogError($"[PiperTest] Error: {ex.Message}");
            }
        }

    }
}