using UnityEngine;
using TMPro;
using CLAWS.Networking;

namespace CLAWS.UI
{
    public class IntentDisplayUI : MonoBehaviour
    {
        // References to the 3D TextMeshPro components
        [SerializeField] private CorvusController _corvusController;
        [SerializeField] private TMP_Text _intentText;
        [SerializeField] private TMP_Text _confidenceText;
        [SerializeField] private TMP_Text _latencyText;

        private void Start()
        {

            if(_corvusController == null)
            {
                Debug.LogError("CorvusController not found in scene!");
                return;
            }

            // Subscribe to the OnIntentReceived event
            _corvusController.OnIntentReceived += UpdateDisplay;

            // Set initial text
            _intentText.text = "Intent: None";
            _confidenceText.text = "Confidence: 0%";
            _latencyText.text = "Latency: 0ms";

            Debug.Log("IntentDisplayUI initialized");
        }

        private void UpdateDisplay(string intent, float confidence, float latency)
        {
            // Update the text displays
            _intentText.text = $"Intent: {intent}";
            _confidenceText.text = $"Confidence: {confidence:P0}";
            _latencyText.text = $"Latency: {latency:F0}ms";

            // Color based on confidence level
            if(confidence >= 0.8f)
            {
                _confidenceText.color = Color.green;    // High confidence
            } else if (confidence >= 0.5f) 
            {
                _confidenceText.color = Color.yellow;   // Medium confidence
            } else
            {
                _confidenceText.color = Color.red;      // Low confidence
            }

            Debug.Log($"UI Updated - Intent: {intent}, Confidence: {confidence}, Latency: {latency}ms");
        }

        private void OnDestroy()
        {
            if(_corvusController != null)
            {
                _corvusController.OnIntentReceived -= UpdateDisplay;
            }
        }
 
    }

}