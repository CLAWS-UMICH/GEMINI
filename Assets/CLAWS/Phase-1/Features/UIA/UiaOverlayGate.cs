using Unity.XR.CoreUtils;
using UnityEngine;
using UnityEngine.XR.ARFoundation;
using UnityEngine.XR.ARSubsystems;
using UnityEngine.SubsystemsImplementation;

/// <summary>
/// Enables AR image tracking only while UIA feature mode is active.
/// Builds an AR Session + XR Origin + tracked image stack at runtime so the main MRTK rig stays unchanged.
/// </summary>
public class UiaOverlayGate : MonoBehaviour
{
    [Header("AR image tracking")]
    [Tooltip("Images to detect (must include a name matching the uia_image prefab root).")]
    public XRReferenceImageLibrary referenceImageLibrary;

    [Tooltip("Root prefab spawned on the marker; root name must match the library image name.")]
    public GameObject uiaImagePrefab;

    [Tooltip("Parent for the runtime AR rig (defaults to scene root).")]
    public Transform arRigParent;

    private GameObject _arRoot;
    private ARSession _arSession;
    private XROrigin _xrOrigin;
    private ARTrackedImageManager _imageManager;
    private PlaceTrackedImages _placeTracked;
    private bool _built;
    private bool _reportedUnsupported;

    private void Awake()
    {
        if (arRigParent == null)
        {
            arRigParent = transform.root;
        }
    }

    private void OnDisable()
    {
        SetArTrackingActive(false);
    }

    public void EnterUiaMode()
    {
        SetArTrackingActive(true);
    }

    public void ExitUiaMode()
    {
        SetArTrackingActive(false);
    }

    private void BuildArRigIfNeeded()
    {
        if (_built || referenceImageLibrary == null || uiaImagePrefab == null)
        {
            if (referenceImageLibrary == null || uiaImagePrefab == null)
            {
                Debug.LogWarning("UiaOverlayGate: Assign referenceImageLibrary and uiaImagePrefab for QR overlay tracking.");
            }
            return;
        }

        if (!IsArImageTrackingAvailable())
        {
            if (!_reportedUnsupported)
            {
                Debug.LogWarning(
                    "UiaOverlayGate: AR image tracking provider is not available on this runtime/platform. " +
                    "Enable a supported provider in XR Plug-in Management for your target device.");
                _reportedUnsupported = true;
            }
            return;
        }

        _arRoot = new GameObject("UIA_AR_ImageTracking");
        _arRoot.transform.SetParent(arRigParent, false);

        _arSession = _arRoot.AddComponent<ARSession>();
        _arSession.enabled = false;

        var originGo = new GameObject("XR Origin (ImageTracking)");
        originGo.transform.SetParent(_arRoot.transform, false);

        _xrOrigin = originGo.AddComponent<XROrigin>();
        AssignCameraToOrigin(_xrOrigin);

        _imageManager = originGo.AddComponent<ARTrackedImageManager>();
        _imageManager.referenceLibrary = referenceImageLibrary;
        _imageManager.enabled = false;

        _placeTracked = originGo.AddComponent<PlaceTrackedImages>();
        _placeTracked.ArPrefabs = new[] { uiaImagePrefab };
        _placeTracked.enabled = false;

        _built = true;
    }

    private static bool IsArImageTrackingAvailable()
    {
        var sessionDescriptors = new System.Collections.Generic.List<XRSessionSubsystemDescriptor>();
        SubsystemManager.GetSubsystemDescriptors(sessionDescriptors);
        if (sessionDescriptors.Count == 0)
        {
            return false;
        }

        var imageDescriptors = new System.Collections.Generic.List<XRImageTrackingSubsystemDescriptor>();
        SubsystemManager.GetSubsystemDescriptors(imageDescriptors);
        return imageDescriptors.Count > 0;
    }

    private static void AssignCameraToOrigin(XROrigin origin)
    {
        var cameras = FindObjectsByType<Camera>(FindObjectsSortMode.None);
        Camera best = null;
        var bestDepth = float.MinValue;
        foreach (var cam in cameras)
        {
            if (cam == null || !cam.enabled)
            {
                continue;
            }

            if (cam.targetTexture != null)
            {
                continue;
            }

            if (cam.orthographic)
            {
                continue;
            }

            if (cam.depth > bestDepth)
            {
                bestDepth = cam.depth;
                best = cam;
            }
        }

        if (best != null)
        {
            origin.Camera = best;
        }
        else if (Camera.main != null)
        {
            origin.Camera = Camera.main;
        }
    }

    private void SetArTrackingActive(bool active)
    {
        if (!active)
        {
            if (_built && _placeTracked != null)
            {
                _placeTracked.ClearInstantiatedPrefabs();
            }

            if (_placeTracked != null)
            {
                _placeTracked.enabled = false;
            }

            if (_imageManager != null)
            {
                _imageManager.enabled = false;
            }

            if (_arSession != null)
            {
                _arSession.enabled = false;
            }

            if (_arRoot != null)
            {
                Destroy(_arRoot);
            }

            _arRoot = null;
            _arSession = null;
            _xrOrigin = null;
            _imageManager = null;
            _placeTracked = null;
            _built = false;
            return;
        }

        if (!_built)
        {
            BuildArRigIfNeeded();
        }

        if (!_built || _arSession == null || _imageManager == null || _placeTracked == null)
        {
            return;
        }

        _arSession.enabled = true;
        _imageManager.enabled = true;
        _placeTracked.enabled = true;
    }
}
