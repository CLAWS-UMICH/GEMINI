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

            if (keyboard.digit1Key.wasPressedThisFrame) SendVoicePhrase(0);
            else if (keyboard.digit2Key.wasPressedThisFrame) SendVoicePhrase(1);
            else if (keyboard.digit3Key.wasPressedThisFrame) SendVoicePhrase(2);
            else if (keyboard.digit4Key.wasPressedThisFrame) SendVoicePhrase(3);
            else if (keyboard.digit5Key.wasPressedThisFrame) SendVoicePhrase(4);
            else if (keyboard.digit6Key.wasPressedThisFrame) SendVoicePhrase(5);
            else if (keyboard.digit7Key.wasPressedThisFrame) SendVoicePhrase(6);
            else if (keyboard.digit8Key.wasPressedThisFrame) SendVoicePhrase(7);
            else if (keyboard.digit9Key.wasPressedThisFrame) SendVoicePhrase(8);
        }

        void SendVoicePhrase(int index)
        {
            if (index < 0 || index >= VoicePhrases.Length) return;

            string phrase = VoicePhrases[index];
            Debug.Log($"[CORVUS][KeyboardVoice] Simulating intent for phrase: \"{phrase}\"");

            // STT now runs on Python via the streaming protocol. The keyboard harness
            // exercises Dispatch locally without going through the wire — production
            // voice testing happens via the wake word.
            if (_corvusARBridge == null)
                _corvusARBridge = FindObjectOfType<CorvusARBridge>();

            if (_corvusARBridge == null)
            {
                Debug.LogError("[CORVUS][KeyboardVoice] No CorvusARBridge for simulation.");
                return;
            }

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
