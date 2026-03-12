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
            "check my vitals",              // 1
            "show me the map",              // 2
            "navigate to the LTV",          // 3
            "reroute around that crater",   // 4
            "start egress",                 // 5
            "start ERM",                    // 6
            "run diagnostics on the LTV",   // 7
            "what's my temperature",        // 8 
            "what's the cabin temperature", // 9
            "check my primary fan",         // 0
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
                _ = SendTestCommandAsync(1);    // "show me the map"
            } else if (keyboard.digit3Key.wasPressedThisFrame)
            {
                _ = SendTestCommandAsync(2);    // "navigate to the LTV"
            } else if (keyboard.digit4Key.wasPressedThisFrame)
            {
                _ = SendTestCommandAsync(3);    // "reroute around that crater"
            } else if (keyboard.digit5Key.wasPressedThisFrame)
            {
                _ = SendTestCommandAsync(4);    // "start egress"
            } else if (keyboard.digit6Key.wasPressedThisFrame)
            {
                _ = SendTestCommandAsync(5);    // "start ERM"
            } else if (keyboard.digit7Key.wasPressedThisFrame)
            {
                _ = SendTestCommandAsync(6);    // "run diagnostics on the LTV"
            } else if (keyboard.digit8Key.wasPressedThisFrame)
            {
                _ = SendTestCommandAsync(7);    // "what's my temperature"
            } else if (keyboard.digit9Key.wasPressedThisFrame)
            {
                _ = SendTestCommandAsync(8);    // "what's the cabin temperature"
            } else if (keyboard.digit0Key.wasPressedThisFrame)
            {
                _ = SendTestCommandAsync(9);    // "check my primary fan"
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