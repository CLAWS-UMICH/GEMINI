using UnityEngine;

public class UiaOverlayGate : MonoBehaviour
{
    [Tooltip("Root GameObject containing the QRCodePlacer + PrefabChanger. Enabled in UIA mode, disabled otherwise.")]
    public GameObject qrOverlayRoot;

    private void Awake()
    {
        if (qrOverlayRoot != null) qrOverlayRoot.SetActive(false);
    }

    public void EnterUiaMode()
    {
        if (qrOverlayRoot != null) qrOverlayRoot.SetActive(true);
    }

    public void ExitUiaMode()
    {
        if (qrOverlayRoot != null) qrOverlayRoot.SetActive(false);
    }
}
