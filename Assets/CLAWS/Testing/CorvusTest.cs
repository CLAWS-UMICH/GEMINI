using System;
using UnityEngine;
using System.Threading.Tasks;
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
            "check my vitals",
            "navigate to airlock",
            "check oxygen level",
            "show battery status",
            "emergency abort"
        };

        private void Update()
        {
            if(_corvusController == null || !_corvusController.IsConnected)
            {
                return;
            }

            // 1-5 send test commands
            if(Input.GetKeyDown(KeyCode.Alpha1))
            {
                _ = SendTestCommandAsync(0);    // "check my vitals"
            } else if (Input.GetKeyDown(KeyCode.Alpha2))
            {
                _ = SendTestCommandAsync(1);    // "navigate to airlock"
            } else if (Input.GetKeyDown(KeyCode.Alpha3))
            {
                _ = SendTestCommandAsync(2);    // "check oxygen level"
            } else if (Input.GetKeyDown(KeyCode.Alpha4))
            {
                _ = SendTestCommandAsync(3);    // "show battery status"
            } else if (Input.GetKeyDown(KeyCode.Alpha5))
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