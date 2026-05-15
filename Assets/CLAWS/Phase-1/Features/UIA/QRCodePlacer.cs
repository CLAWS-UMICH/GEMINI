using Microsoft.MixedReality.OpenXR;
using UnityEngine;
using UnityEngine.XR.ARSubsystems;

public class QRCodePlacer : MonoBehaviour
{
    [Header("QR Matching")]
    [Tooltip("The exact string encoded in the printed QR code.")]
    [SerializeField] private string expectedQrText = "UIA_PANEL";

    [Header("Tracking Behavior")]
    [Tooltip("0 = snap every frame. 0.9 = smooth, slow follow. Reduces jitter from head motion.")]
    [Range(0f, 0.99f)]
    [SerializeField] private float smoothing = 0.8f;

    [Tooltip("If true, stop updating pose after the QR is first locked.")]
    [SerializeField] private bool lockAfterFirstDetection = false;

    [Header("Debug")]
    [Tooltip("Log every detected marker and per-frame status. Turn off for production.")]
    [SerializeField] private bool verboseLogging = true;

    [Tooltip("Optional. If set, mirrors debug messages to this on-headset text display.")]
    [SerializeField] private TMPro.TextMeshProUGUI debugDisplay;

    public event System.Action OnQrLocked;
    public event System.Action OnQrLost;

    private ARMarker trackedMarker;
    private bool hasInitialPose;
    private float lastPositionLogTime;
    private TrackingState lastLoggedTrackingState = (TrackingState)(-99);

    private void Awake()
    {
        Log($"Awake. Expecting QR text: '{expectedQrText}'");
    }

    private void Start()
    {
        if (ARMarkerManager.Instance == null)
        {
            LogError("Start: No ARMarkerManager.Instance found. Add an ARMarkerManager component to your XR Origin in this scene.");
            return;
        }

        Log($"Start: ARMarkerManager found on '{ARMarkerManager.Instance.name}'.");

        var types = ARMarkerManager.Instance.enabledMarkerTypes;
        string typesString = (types == null || types.Length == 0)
            ? "(none — QR codes will NOT be detected!)"
            : string.Join(", ", types);
        Log($"Start: Enabled marker types: {typesString}");

        Log($"Start: Subsystem running = {ARMarkerManager.Instance.subsystem?.running}");
    }

    private void OnEnable()
    {
        if (ARMarkerManager.Instance == null)
        {
            LogError("OnEnable: No ARMarkerManager.Instance. Cannot subscribe to marker events.");
            return;
        }
        ARMarkerManager.Instance.markersChanged += OnMarkersChanged;
        Log("OnEnable: Subscribed to markersChanged.");
    }

    private void OnDisable()
    {
        if (ARMarkerManager.Instance != null)
        {
            ARMarkerManager.Instance.markersChanged -= OnMarkersChanged;
            Log("OnDisable: Unsubscribed.");
        }
    }

    private void OnMarkersChanged(ARMarkersChangedEventArgs args)
    {
        int added = args.added?.Count ?? 0;
        int updated = args.updated?.Count ?? 0;
        int removed = args.removed?.Count ?? 0;

        if (added > 0 || removed > 0 || verboseLogging)
        {
            Log($"markersChanged: added={added}, updated={updated}, removed={removed}");
        }

        if (args.added != null)
        {
            foreach (var m in args.added) HandleSighting(m, "ADDED");
        }
        if (args.updated != null)
        {
            foreach (var m in args.updated) HandleSighting(m, "UPDATED");
        }
        if (args.removed != null)
        {
            foreach (var m in args.removed)
            {
                Log($"REMOVED marker id={m.trackableId}");
                if (m == trackedMarker)
                {
                    LogWarning("Lost the QR we were tracking!");
                    trackedMarker = null;
                    hasInitialPose = false;
                    lastLoggedTrackingState = (TrackingState)(-99);
                    OnQrLost?.Invoke();
                }
            }
        }
    }

    private void HandleSighting(ARMarker marker, string phase)
    {
        string decoded = marker.GetDecodedString();
        string decodedSafe = string.IsNullOrEmpty(decoded) ? "(empty)" : decoded;

        if (phase == "ADDED" || verboseLogging)
        {
            Log($"{phase}: id={marker.trackableId} text='{decodedSafe}' state={marker.trackingState} size={marker.size} pos={marker.transform.position}");
        }

        TryClaim(marker, decoded);
    }

    private void TryClaim(ARMarker marker, string decoded)
    {
        if (trackedMarker != null) return;

        if (decoded == expectedQrText)
        {
            trackedMarker = marker;
            Log($"=== LOCKED onto QR '{expectedQrText}' (id={marker.trackableId}) ===");
            OnQrLocked?.Invoke();
        }
        else if (verboseLogging)
        {
            Log($"Ignored QR: decoded='{decoded ?? "(null)"}' != expected='{expectedQrText}'");
        }
    }

    private void Update()
    {
        if (trackedMarker == null) return;

        if (trackedMarker.trackingState != lastLoggedTrackingState)
        {
            Log($"Tracking state: {lastLoggedTrackingState} -> {trackedMarker.trackingState}");
            lastLoggedTrackingState = trackedMarker.trackingState;
        }

        if (lockAfterFirstDetection && hasInitialPose) return;
        if (trackedMarker.trackingState != TrackingState.Tracking) return;

        var src = trackedMarker.transform;
        if (!hasInitialPose)
        {
            transform.SetPositionAndRotation(src.position, src.rotation);
            hasInitialPose = true;
            Log($"First pose applied. pos={src.position} rot={src.rotation.eulerAngles}");
        }
        else
        {
            float k = 1f - smoothing;
            transform.position = Vector3.Lerp(transform.position, src.position, k);
            transform.rotation = Quaternion.Slerp(transform.rotation, src.rotation, k);
        }

        if (verboseLogging && Time.time - lastPositionLogTime > 2f)
        {
            lastPositionLogTime = Time.time;
            Log($"Tracking heartbeat: pos={transform.position}");
        }
    }

    [ContextMenu("Dump State")]
    private void DumpState()
    {
        Log("--- Dump ---");
        Log($"ARMarkerManager.Instance = {(ARMarkerManager.Instance == null ? "null" : ARMarkerManager.Instance.name)}");
        Log($"trackedMarker = {(trackedMarker == null ? "null" : trackedMarker.trackableId.ToString())}");
        Log($"hasInitialPose = {hasInitialPose}");
        Log($"this.transform.position = {transform.position}");
    }

    private void Log(string msg)
    {
        Debug.Log($"[QRCodePlacer] {msg}");
        if (debugDisplay != null) debugDisplay.text = msg;
    }

    private void LogWarning(string msg)
    {
        Debug.LogWarning($"[QRCodePlacer] {msg}");
        if (debugDisplay != null) debugDisplay.text = "WARN: " + msg;
    }

    private void LogError(string msg)
    {
        Debug.LogError($"[QRCodePlacer] {msg}");
        if (debugDisplay != null) debugDisplay.text = "ERROR: " + msg;
    }
}
