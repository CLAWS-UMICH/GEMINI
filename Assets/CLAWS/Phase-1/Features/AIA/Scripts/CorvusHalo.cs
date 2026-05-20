using UnityEngine;
using System.Collections;
using CLAWS.Networking;

public class CorvusHalo : MonoBehaviour
{

    [SerializeField] private Animator AIA_Animator;
    [SerializeField] CorvusController _corvusController;
    [SerializeField] private CorvusTTS _corvusTTS;

    // Start is called once before the first execution of Update after the MonoBehaviour is created
    void Start()
    {
        if (_corvusController == null)
            _corvusController = FindObjectOfType<CorvusController>();
        if (_corvusTTS == null)
            _corvusTTS = FindObjectOfType<CorvusTTS>();

        Debug.Log($"[CorvusHalo] Start running. controller={(_corvusController != null)}, animator={(AIA_Animator != null)}, tts={(_corvusTTS != null)}");

        if (_corvusController == null)
        {
            Debug.LogError("CorvusController not found in scene!");
            return;
        }

        if (AIA_Animator == null)
        {
            Debug.LogError("[CorvusHalo] AIA_Animator is NOT assigned — animation will never play!");
        }

        _corvusController.OnWakeDetected += OnWake;
        _corvusController.OnIntentReceived += OnIntentReceived;
        _corvusController.OnStreamingTimeout += OnStreamingTimeout;
        Debug.Log("[CorvusHalo] Subscribed to OnWakeDetected + OnIntentReceived + OnStreamingTimeout");
    }
   void OnDestroy()
    {
        if (_corvusController != null)
        {
            _corvusController.OnWakeDetected -= OnWake;
            _corvusController.OnIntentReceived -= OnIntentReceived;
            _corvusController.OnStreamingTimeout -= OnStreamingTimeout;
        }
    }

    private void OnStreamingTimeout()
    {
        Debug.LogWarning("[CorvusHalo] OnStreamingTimeout fired — reverting halo to idle");
        if (AIA_Animator == null) return;
        AIA_Animator.SetBool("isAwake", false);
        AIA_Animator.SetBool("foundAnswer", false);
    }

    private void OnWake()
    {
        Debug.Log($"[CorvusHalo] OnWake fired. animator={(AIA_Animator != null)}, isActiveAndEnabled={isActiveAndEnabled}");
        if (AIA_Animator == null) { Debug.LogError("[CorvusHalo] AIA_Animator is null in OnWake"); return; }
        AIA_Animator.SetBool("isAwake", true);
        Debug.Log($"[CorvusHalo] SetBool isAwake=true. Current isAwake param = {AIA_Animator.GetBool("isAwake")}");
    }

    private void OnIntentReceived(string intent, float confidence, string response, CorvusLatency latency)
    {
        Debug.Log($"[CorvusHalo] OnIntentReceived intent={intent} confidence={confidence}");
        if (AIA_Animator == null) { Debug.LogError("[CorvusHalo] AIA_Animator is null in OnIntentReceived"); return; }
        AIA_Animator.SetBool("foundAnswer", true);
        StartCoroutine(WaitForTTSEnd());
    }

    private void OnIdle()
    {
        AIA_Animator.SetBool("isAwake", false);
        AIA_Animator.SetBool("foundAnswer", false);
    }

    private IEnumerator WaitForTTSEnd()
    {
        yield return new WaitForSeconds(0.1f);

        while(_corvusTTS.IsSpeaking())
        {
            yield return null;
        }

        AIA_Animator.SetBool("isAwake", false);
        AIA_Animator.SetBool("foundAnswer", false);
    }

}
