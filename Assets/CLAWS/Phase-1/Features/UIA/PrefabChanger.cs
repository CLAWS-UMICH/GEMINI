using UnityEngine;

public class PrefabChanger : MonoBehaviour
{
    [Header("Prefab Settings")]
    [Tooltip("Drag and drop your prefabs here in the Inspector.")]
    public GameObject[] prefabs;

    [Tooltip("The transform where the prefabs will spawn. Can be an empty GameObject.")]
    public Transform overlayTarget;

    [Tooltip("Optional. If not set, will auto-find QRCodePlacer on this GameObject.")]
    public QRCodePlacer qrPlacer;

    private GameObject currentInstantiatedPrefab;
    private int currentIndex = 0;

    void Awake()
    {
        if (qrPlacer == null) qrPlacer = GetComponent<QRCodePlacer>();
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

        if (currentInstantiatedPrefab != null)
        {
            Destroy(currentInstantiatedPrefab);
            currentInstantiatedPrefab = null;
        }
    }

    void Update()
    {
        if (currentInstantiatedPrefab == null) return;

        if (Input.GetKeyDown(KeyCode.RightArrow))
        {
            NextPrefab();
        }
        else if (Input.GetKeyDown(KeyCode.LeftArrow))
        {
            PreviousPrefab();
        }
    }

    private void HandleQrLocked()
    {
        if (prefabs.Length == 0 || overlayTarget == null)
        {
            Debug.LogWarning("[PrefabChanger] QR locked but prefabs/overlayTarget not assigned.");
            return;
        }
        if (currentInstantiatedPrefab != null) return;
        InstantiatePrefab(currentIndex);
    }

    private void HandleQrLost()
    {
        if (currentInstantiatedPrefab != null)
        {
            Destroy(currentInstantiatedPrefab);
            currentInstantiatedPrefab = null;
        }
    }

    public void NextPrefab()
    {
        if (prefabs.Length == 0) return;

        currentIndex++;
        if (currentIndex >= prefabs.Length)
        {
            currentIndex = 0;
        }
        InstantiatePrefab(currentIndex);
    }

    public void PreviousPrefab()
    {
        if (prefabs.Length == 0) return;

        currentIndex--;
        if (currentIndex < 0)
        {
            currentIndex = prefabs.Length - 1;
        }
        InstantiatePrefab(currentIndex);
    }

    private void InstantiatePrefab(int index)
    {
        if (currentInstantiatedPrefab != null)
        {
            Destroy(currentInstantiatedPrefab);
        }

        currentInstantiatedPrefab = Instantiate(prefabs[index], overlayTarget.position, overlayTarget.rotation);
        currentInstantiatedPrefab.transform.SetParent(overlayTarget);
    }
}
