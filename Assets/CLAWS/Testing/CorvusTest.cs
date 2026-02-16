using System;
using UnityEngine;
using System.Threading.Tasks;
using UnityEngine.InputSystem;
using CLAWS.Networking;

namespace CLAWS.Testing
{
    public class CorvusTest : MonoBehaviour
    {
        // Reference to CorvusController
        [SerializeField] private CorvusController _corvusController;

        // Test commands
        private readonly string[] _testCommands = new string[]
        {
            "check my vitals",          // 1
            "navigate to airlock",      // 2
            "check oxygen level",       // 3
            "show battery status",      // 4
            "emergency abort"           // 5
        };

        private void Update()
        {
            if(_corvusController == null || !_corvusController.IsConnected)
            {
                return;
            }

            var keyboard = Keyboard.current;
            if(keyboard == null) return;

            // 1-5 send test commands
            if(keyboard.digit1Key.wasPressedThisFrame)
            {
                _ = SendTestCommandAsync(0);    // "check my vitals"
            } else if (keyboard.digit2Key.wasPressedThisFrame)
            {
                _ = SendTestCommandAsync(1);    // "navigate to airlock"
            } else if (keyboard.digit3Key.wasPressedThisFrame)
            {
                _ = SendTestCommandAsync(2);    // "check oxygen level"
            } else if (keyboard.digit4Key.wasPressedThisFrame)
            {
                _ = SendTestCommandAsync(3);    // "show battery status"
            } else if (keyboard.digit5Key.wasPressedThisFrame)
            {
                _ = SendTestCommandAsync(4);    // "emergency abort"
            }
        }

        private async Task SendTestCommandAsync(int commandIndex)
        {
            // Validate index
            if(commandIndex < 0 || commandIndex >= _testCommands.Length)
            {
                Debug.LogError($"Invalid command index: {commandIndex}");
                return;
            }

            string command = _testCommands[commandIndex];

            try
            {
                Debug.Log($"[TEST] Sending command: {command}");
                await _corvusController.SendCommandAsync(command);
            }
            catch (Exception ex)
            {
                Debug.LogError($"[TEST] Failed to send command: {ex.Message}");
            }
        }
    }
}