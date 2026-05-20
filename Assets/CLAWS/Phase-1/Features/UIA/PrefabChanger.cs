using UnityEngine;

public class PrefabChanger : MonoBehaviour
{
    [Header("Spawn Settings")]
    [Tooltip("The transform where the prefab spawns. Usually the QR-anchored object.")]
    public Transform overlayTarget;

    [Tooltip("Optional. Auto-found on this GameObject / parent if not set.")]
    public QRCodePlacer qrPlacer;

    [Header("Orientation")]
    [Tooltip("If true, the spawned prefab rotates each frame to face the user's camera, ignoring the QR's rotation.")]
    public bool faceCamera = true;

    [Tooltip("If true, the billboard ignores camera pitch (keeps the prefab upright).")]
    public bool lockVerticalAxis = true;

    private GameObject currentInstantiatedPrefab;
    private GameObject pendingPrefab;
    private bool qrLocked;

    void Awake()
    {
        if (qrPlacer == null) qrPlacer = GetComponent<QRCodePlacer>();
        if (qrPlacer == null) qrPlacer = GetComponentInParent<QRCodePlacer>();
    }

    void OnEnable()
    {
        if (qrPlacer != null)
        {
            qrPlacer.OnQrLocked += HandleQrLocked;
            qrPlacer.OnQrLost += HandleQrLost;
        }
        else
        {
            Debug.LogWarning("[PrefabChanger] No QRCodePlacer reference. Prefab will not spawn on QR detection.");
        }
    }

    void OnDisable()
    {
        if (qrPlacer != null)
        {
            qrPlacer.OnQrLocked -= HandleQrLocked;
            qrPlacer.OnQrLost -= HandleQrLost;
        }

        DestroyCurrent();
        qrLocked = false;
    }

    public void SetPrefab(GameObject prefab)
    {
        pendingPrefab = prefab;
        // Spawn immediately if QR is locked OR if we already have an instance (the QR may be
        // temporarily out of view — overlayTarget still holds the last known pose).
        if (qrLocked || currentInstantiatedPrefab != null) Spawn(prefab);
    }

    public void ClearPrefab()
    {
        pendingPrefab = null;
        DestroyCurrent();
    }

    private void HandleQrLocked()
    {
        qrLocked = true;
        // If an instance is already spawned, this is a re-acquisition after a lost/found cycle.
        // Leave the existing instance alone — QRCodePlacer will Lerp it to the new pose.
        if (currentInstantiatedPrefab != null) return;
        if (pendingPrefab == null) return;
        Spawn(pendingPrefab);
    }

    private void HandleQrLost()
    {
        qrLocked = false;
        // Don't destroy — leave the prefab frozen at its last pose. QRCodePlacer will resume
        // updating it when the QR is back in view. Cleanup happens via OnDisable / ClearPrefab.
    }

    private void Spawn(GameObject prefab)
    {
        DestroyCurrent();
        if (prefab == null || overlayTarget == null) return;
        currentInstantiatedPrefab = Instantiate(prefab);
        currentInstantiatedPrefab.transform.SetParent(overlayTarget, worldPositionStays: false);

        // Prefabs with VerticalizeQRPrefab opt out of billboarding so they stay locked to the QR
        // panel orientation. Adding FaceCamera here would fight VerticalizeQRPrefab in LateUpdate.
        bool prefabLocksOrientation = currentInstantiatedPrefab.GetComponentInChildren<VerticalizeQRPrefab>(true) != null;

        if (faceCamera && !prefabLocksOrientation)
        {
            var fc = currentInstantiatedPrefab.GetComponent<FaceCamera>();
            if (fc == null) fc = currentInstantiatedPrefab.AddComponent<FaceCamera>();
            fc.lockVertical = lockVerticalAxis;
        }
    }

    private void DestroyCurrent()
    {
        if (currentInstantiatedPrefab != null)
        {
            Destroy(currentInstantiatedPrefab);
            currentInstantiatedPrefab = null;
        }
    }
}
