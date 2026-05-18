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
        if (!qrLocked) return;
        Spawn(prefab);
    }

    public void ClearPrefab()
    {
        pendingPrefab = null;
        DestroyCurrent();
    }

    private void HandleQrLocked()
    {
        qrLocked = true;
        if (pendingPrefab == null) return;
        Spawn(pendingPrefab);
    }

    private void HandleQrLost()
    {
        qrLocked = false;
        DestroyCurrent();
    }

    private void Spawn(GameObject prefab)
    {
        DestroyCurrent();
        if (prefab == null || overlayTarget == null) return;
        currentInstantiatedPrefab = Instantiate(prefab);
        currentInstantiatedPrefab.transform.SetParent(overlayTarget, worldPositionStays: false);

        if (faceCamera)
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
