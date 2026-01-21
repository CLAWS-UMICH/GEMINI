using System;
using UnityEngine;
using UnityEngine.InputSystem;
using Piper;
using CLAWS.Networking;

namespace CLAWS.Testing
{
    public class PiperTest : MonoBehaviour
    {
        [SerializeField] private CorvusTTS _corvusTTS;

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
            if (_corvusTTS == null)
            {
                Debug.LogError("[PiperTest] CorvusTTS not assigned!");
                return;
            }
            
            try {
                await _corvusTTS.Speak(_testPhrase);
                Debug.Log("[PiperTest] Speech complete");
            }
            catch (Exception ex)
            {
                Debug.LogError($"[PiperTest] Error: {ex.Message}");
            }
        }

    }
}