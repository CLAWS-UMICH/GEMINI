using UnityEngine;
using System.Collections;

public class SideMenuTrigger : MonoBehaviour
{
    [Header("Settings")]
    public Transform objectToMove;
    public float shiftAmount = 0.2f;
    public float speed = 3f;

    [Tooltip("Seconds gaze must be off the menu before it retracts")]
    public float retractDelay = 0.5f;

    private Vector3 hiddenPos;
    private Coroutine slideCoroutine;
    private Coroutine watchCoroutine;
    private bool isOpen;

    void Start()
    {
        if (objectToMove != null)
            hiddenPos = objectToMove.localPosition;
    }

    public void ShiftMenu()
    {
        if (objectToMove == null || isOpen) return;
        isOpen = true;
        SlideTo(hiddenPos + new Vector3(shiftAmount, 0f, 0f));
        watchCoroutine = StartCoroutine(WatchGaze());
    }

    // No-op: retraction is handled entirely by WatchGaze.
    // Kept public so existing Inspector wiring doesn't throw errors.
    public void ShiftMenuBack() { }

    public void ShiftMenu(float timestamp) => ShiftMenu();
    public void ShiftMenuBack(float timestamp) { }

    IEnumerator WatchGaze()
    {
        Camera cam = Camera.main;
        float timeOffMenu = 0f;

        // Wait for the slide to finish before checking gaze
        while (slideCoroutine != null)
            yield return null;

        while (isOpen)
        {
            bool gazeHitsMenu = false;

            if (cam != null)
            {
                Ray ray = new Ray(cam.transform.position, cam.transform.forward);
                foreach (RaycastHit hit in Physics.RaycastAll(ray, 10f))
                {
                    if (hit.transform == objectToMove || hit.transform.IsChildOf(objectToMove))
                    {
                        gazeHitsMenu = true;
                        break;
                    }
                }
            }

            if (gazeHitsMenu)
            {
                timeOffMenu = 0f;
            }
            else
            {
                timeOffMenu += 0.1f;
                if (timeOffMenu >= retractDelay)
                {
                    isOpen = false;
                    watchCoroutine = null;
                    SlideTo(hiddenPos);
                    yield break;
                }
            }

            yield return new WaitForSeconds(0.1f);
        }
    }

    private void SlideTo(Vector3 target)
    {
        if (slideCoroutine != null)
            StopCoroutine(slideCoroutine);
        slideCoroutine = StartCoroutine(SlideObject(target));
    }

    IEnumerator SlideObject(Vector3 targetPos)
    {
        Vector3 startPos = objectToMove.localPosition;
        float t = 0f;

        while (t < 1f)
        {
            t += Time.deltaTime * speed;
            objectToMove.localPosition = Vector3.Lerp(startPos, targetPos, Mathf.Clamp01(t));
            yield return null;
        }

        objectToMove.localPosition = targetPos;
        slideCoroutine = null;
    }
}
