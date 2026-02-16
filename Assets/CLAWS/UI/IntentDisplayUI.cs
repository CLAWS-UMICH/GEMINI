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
        [SerializeField] private TMP_Text _sttLatency;
        [SerializeField] private TMP_Text _ttsLatency;

        [SerializeField] private TMP_Text _roundTripLatency;
        [SerializeField] private TMP_Text _networkOnlyLatency;
        [SerializeField] private TMP_Text _classificationLatency;

        [SerializeField] private TMP_Text _totalLatency;


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

            _sttLatency.text = "STT Latency: 0ms";
            _ttsLatency.text = "TTS Latency: 0ms";

            _roundTripLatency.text = "Round Trip Latency: 0ms";
            _networkOnlyLatency.text = "Network Latency: 0ms";
            _classificationLatency.text = "Classification Latency: 0ms";

            _totalLatency.text = "Total Latency: 0ms";

            Debug.Log("IntentDisplayUI initialized");
        }

        private void UpdateDisplay(string intent, float confidence, CorvusLatency clatency)
        {
            // Update the text displays
            _intentText.text = $"Intent: {intent}";
            _confidenceText.text = $"Confidence: {confidence:P0}";
            
            _sttLatency.text = $"STT Latency: {clatency.STT:F2}ms";
            _ttsLatency.text = $"TTS Latency: {clatency.TTS:F2}ms";

            _roundTripLatency.text = $"Round Trip Latency: {clatency.roundTrip:F2}ms";
            _networkOnlyLatency.text = $"Network Latency: {clatency.network:F2}ms";
            _classificationLatency.text = $"Classification Latency: {clatency.classification:F2}ms";

            _totalLatency.text = $"Total Latency: {clatency.total:F2}ms";

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

            Debug.Log($"UI Updated");
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