using UnityEngine;
using CLAWS.Networking;

public class CorvusARBridge : MonoBehaviour
{
    [SerializeField] private CorvusController _corvusController;
    [SerializeField] private DialogueManager _dialogueManager;
    [SerializeField] private GameObject _vitalsPanel;

    private void Start()
    {
        if(_corvusController == null)
        {
            Debug.LogError("CorvusController not found in Scene!");
            return;
        }
        _corvusController.OnIntentReceived += OnIntentReceived;
    }

    private void OnDestroy()
    {
        if(_corvusController != null)
            _corvusController.OnIntentReceived -= OnIntentReceived;
    }

    private void OnIntentReceived(string intent, float confidence, string response, CorvusLatency latency)
    {
        RouteIntent(intent, response);
    }

    private void RouteIntent(string intent, string response)
    {
        switch(intent)
        {
            case "check_vitals":
                _vitalsPanel.SetActive(true);
                break;
            case "close_vitals":
                _vitalsPanel.SetActive(false);
                break;
            default:
                DisplayResponse(intent, response);
                break;
        }
    }

    private void DisplayResponse(string intent, string responseText)
    {
        if(_dialogueManager == null) return;

        string displayText = string.IsNullOrEmpty(responseText)
            ? intent.Replace("_", " ")
            : responseText;

        Dialogue response = new Dialogue();
        response.name = "CORVUS";
        response.sentences = new string[] { displayText } ;
        _dialogueManager.StartDialogue(response);
        _dialogueManager.DisplayNextSentence();
    }
}