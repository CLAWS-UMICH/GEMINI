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
        {
            Debug.LogError("CorvusController not found in scene!");
            return;
        }

        _corvusController.OnWakeDetected += OnWake;
        _corvusController.OnIntentReceived += OnIntentReceived;
    }
   void OnDestroy()
    {
        if (_corvusController != null)
        {
            _corvusController.OnWakeDetected -= OnWake;
            _corvusController.OnIntentReceived -= OnIntentReceived;
        }
    }

    private void OnWake()
    {
        AIA_Animator.SetBool("isAwake", true);
    }

    private void OnIntentReceived(string intent, float confidence, string response, CorvusLatency latency)
    {
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
