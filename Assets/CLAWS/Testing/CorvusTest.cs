using System;
using System.Threading.Tasks;
using UnityEngine;
using UnityEngine.InputSystem;
using CLAWS.Networking;

namespace CLAWS.Testing
{
    /// <summary>
    /// Play-mode keyboard harness (keys 1–9). Sends natural-language phrases to the Python
    /// NLU server via <see cref="CorvusController"/>, same as a voice transcript — the model
    /// classifies the intent and <see cref="CorvusARBridge"/> executes it.
    /// </summary>
    public class CorvusTest : MonoBehaviour
    {
        [SerializeField] private CorvusController _corvusController;

        [Tooltip("If true and Python is unreachable, fall back to CorvusARBridge.SimulateIntent (skips NLU).")]
        [SerializeField] private bool _simulateWhenDisconnected;

        [SerializeField] private CorvusARBridge _corvusARBridge;

        [Header("Phrases use these slot values (keys 3–6)")]
        [SerializeField] private string _navTargetName = "EV2";
        [SerializeField] private string _waypointName = "Voice Test Alpha";
        [SerializeField] private string _taskName = "Inspect solar panel";

        // Phrases mirror example prompts from the AIA intent spec (easier NLU match).
        string[] VoicePhrases => new[]
        {
            "Open vitals menu",                                              // 1  open_menu_vitals
            "What is my heart rate?",                                        // 2  vitals_heart_rate
            $"Set destination to {_navTargetName}",                            // 3  Set_navigation_target
            $"Add waypoint {_waypointName}",                                   // 4  Add_waypoint
            $"Add task: {_taskName}",                                          // 5  Add_task
            $"Delete task {_taskName}",                                        // 6  Delete_task
            "Open task list",                                                // 7  open_menu_tasks
            "What are the current warnings?",                                // 8  get_warnings
            "Close menu",                                                    // 9  close_menu
        };

        private void Update()
        {
            if (_corvusController == null)
            {
                _corvusController = FindObjectOfType<CorvusController>();
                if (_corvusController == null) return;
            }

            var keyboard = Keyboard.current;
            if (keyboard == null) return;

            if (keyboard.digit1Key.wasPressedThisFrame) _ = SendVoicePhraseAsync(0);
            else if (keyboard.digit2Key.wasPressedThisFrame) _ = SendVoicePhraseAsync(1);
            else if (keyboard.digit3Key.wasPressedThisFrame) _ = SendVoicePhraseAsync(2);
            else if (keyboard.digit4Key.wasPressedThisFrame) _ = SendVoicePhraseAsync(3);
            else if (keyboard.digit5Key.wasPressedThisFrame) _ = SendVoicePhraseAsync(4);
            else if (keyboard.digit6Key.wasPressedThisFrame) _ = SendVoicePhraseAsync(5);
            else if (keyboard.digit7Key.wasPressedThisFrame) _ = SendVoicePhraseAsync(6);
            else if (keyboard.digit8Key.wasPressedThisFrame) _ = SendVoicePhraseAsync(7);
            else if (keyboard.digit9Key.wasPressedThisFrame) _ = SendVoicePhraseAsync(8);
        }

        async Task SendVoicePhraseAsync(int index)
        {
            if (index < 0 || index >= VoicePhrases.Length) return;

            string phrase = VoicePhrases[index];
            Debug.Log($"[CORVUS][KeyboardVoice] Sending transcript: \"{phrase}\"");

            if (_corvusController.IsConnected)
            {
                try
                {
                    await _corvusController.SendCommandAsync(phrase);
                }
                catch (Exception ex)
                {
                    Debug.LogError($"[CORVUS][KeyboardVoice] Send failed: {ex.Message}");
                }
                return;
            }

            Debug.LogWarning("[CORVUS][KeyboardVoice] Python server not connected (ws://localhost:8765). Start the NLU server or enable Simulate When Disconnected.");

            if (!_simulateWhenDisconnected) return;

            if (_corvusARBridge == null)
                _corvusARBridge = FindObjectOfType<CorvusARBridge>();

            if (_corvusARBridge == null)
            {
                Debug.LogError("[CORVUS][KeyboardVoice] No CorvusARBridge for fallback simulation.");
                return;
            }

            // Offline fallback only — production path is always SendCommandAsync above.
            SimulateFallback(index, phrase);
        }

        void SimulateFallback(int index, string phrase)
        {
            switch (index)
            {
                case 0: _corvusARBridge.SimulateIntent("open_menu_vitals", responseText: phrase); break;
                case 1: _corvusARBridge.SimulateIntent("vitals_heart_rate", responseText: phrase); break;
                case 2: _corvusARBridge.SimulateIntent("Set_navigation_target", Nav(_navTargetName), phrase); break;
                case 3: _corvusARBridge.SimulateIntent("Add_waypoint", Waypoint(_waypointName), phrase); break;
                case 4: _corvusARBridge.SimulateIntent("Add_task", Task(_taskName), phrase); break;
                case 5: _corvusARBridge.SimulateIntent("Delete_task", Task(_taskName), phrase); break;
                case 6: _corvusARBridge.SimulateIntent("open_menu_tasks", responseText: phrase); break;
                case 7: _corvusARBridge.SimulateIntent("get_warnings", responseText: phrase); break;
                case 8: _corvusARBridge.SimulateIntent("close_menu", responseText: phrase); break;
            }
        }

        static IntentParameters Nav(string name) => new IntentParameters { NAVIGATION_TARGET_NAME = name };
        static IntentParameters Waypoint(string name) => new IntentParameters { WAYPOINT_NAME = name };
        static IntentParameters Task(string name) => new IntentParameters { TASK_NAME = name };
    }
}
