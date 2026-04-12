using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.InputSystem;
using UnityEngine.UI;
using MixedReality.Toolkit.UX;

/// <summary>
/// Radial Add: dual minimap handoff (small chrome shrinks, large grows), north-up placement camera, click to publish waypoint.
/// Uses BoxCollider + PressableButton so MRTK3 XRI (gaze, hand ray, spatial mouse) can interact with the large minimap.
/// </summary>
public class MinimapWaypointPlacement : MonoBehaviour
{
    enum PlacementPhase { Idle, AnimatingExpand, AwaitingClick, Processing }

    [SerializeField] NavigationController navigationController;

    [Header("Small minimap (shrinks away)")]
    [Tooltip("Optional: root containing mask, border, time. If empty, parent multi-child Canvas of Small Map Root is used when applicable.")]
    [SerializeField] RectTransform smallMinimapChromeRoot;

    [Tooltip("Small map anchor (e.g. Mask). Used with Chrome Root / parent heuristic to resolve what scales to zero.")]
    [SerializeField] RectTransform smallMapRoot;

    [Header("Large minimap (grows in)")]
    [Tooltip("Large map tween root (e.g. Mask under MiniMapLarge).")]
    [SerializeField] RectTransform largeMinimapRoot;

    [Tooltip("Optional: parent that includes large Raw Image + border + time. If empty, only Large Minimap Root is tweened.")]
    [SerializeField] RectTransform largeMinimapChromeRoot;

    [Tooltip("Large map Raw Image (for clicks). Same render texture as the minimap camera.")]
    [SerializeField] RawImage minimapRawImage;

    [Header("Large layout (optional)")]
    [Tooltip("Optional layout RectTransform. When set and valid, the large root reparents beside it and tweens to match its rect.")]
    [SerializeField] RectTransform placementExpandedLayoutTarget;

    [Header("Animation")]
    [SerializeField] float tweenDuration = 0.35f;

    [Header("Placement camera")]
    [SerializeField] float placementCameraHeight = 80f;
    [SerializeField] float placementOrthographicSize = 20.9f;

    [Header("Bounds")]
    [SerializeField] float maxPlaceRadiusFromOrigin = 500f;

    [Header("Canvas")]
    [SerializeField] int canvasSortOrderBoost = 40;

    [Header("Placement crosshair (large minimap)")]
    [Tooltip("Total span of each crosshair arm in UI units (horizontal bar width = vertical bar height).")]
    [SerializeField] float placementCrosshairSpan = 24f;
    [Tooltip("Thickness of the crosshair lines.")]
    [SerializeField] float placementCrosshairThickness = 2f;
    [SerializeField] Color placementCrosshairColor = new Color(1f, 0.92f, 0.16f, 0.95f);

    NavigationController Nav => navigationController != null ? navigationController : GetComponent<NavigationController>();

    PlacementPhase _phase = PlacementPhase.Idle;
    bool _busy;
    RadialMenuNavigationController _radial;
    Pathfinding _pathfind;

    RectTransform _smallRt;
    RectTransform _largeRt;
    RectSnapshot _smallVisibleSnap;
    RectSnapshot _smallGoneSnap;
    RectSnapshot _largeHiddenSnap;
    RectSnapshot _largeShownSnap;
    Transform _largeRestoreParent;
    int _largeRestoreSiblingIndex;
    bool _largeUsedLayoutReparent;
    bool _smallRaycastBlockedCached;
    readonly List<(Graphic graphic, bool raycastTarget)> _smallGraphicRaycastRestore = new List<(Graphic, bool)>();
    int _savedCanvasSort;
    bool _hadCanvasSortOverride;
    Canvas _parentCanvas;

    Camera _minimapCam;
    CamSnapshot _camCollapsed;
    MinimapCameraScript _followScript;
    bool _hadFollowScript;

    BoxCollider _addedCollider;
    PressableButton _addedButton;
    GameObject _cursorGo;

    Coroutine _expandRoutine;
    WaypointType _placementWaypointType = WaypointType.POI;

    readonly List<GameObject> _activatedAncestors = new List<GameObject>();
    readonly List<GameObject> _activatedPlacementHostChain = new List<GameObject>();

    struct RectSnapshot
    {
        public Vector2 AnchorMin;
        public Vector2 AnchorMax;
        public Vector2 Pivot;
        public Vector2 AnchoredPosition;
        public Vector2 SizeDelta;
        public Vector3 LocalScale;

        public static RectSnapshot From(RectTransform rt)
        {
            return new RectSnapshot
            {
                AnchorMin = rt.anchorMin,
                AnchorMax = rt.anchorMax,
                Pivot = rt.pivot,
                AnchoredPosition = rt.anchoredPosition,
                SizeDelta = rt.sizeDelta,
                LocalScale = rt.localScale
            };
        }

        public static RectSnapshot Lerp(RectSnapshot a, RectSnapshot b, float t)
        {
            return new RectSnapshot
            {
                AnchorMin = Vector2.Lerp(a.AnchorMin, b.AnchorMin, t),
                AnchorMax = Vector2.Lerp(a.AnchorMax, b.AnchorMax, t),
                Pivot = Vector2.Lerp(a.Pivot, b.Pivot, t),
                AnchoredPosition = Vector2.Lerp(a.AnchoredPosition, b.AnchoredPosition, t),
                SizeDelta = Vector2.Lerp(a.SizeDelta, b.SizeDelta, t),
                LocalScale = Vector3.Lerp(a.LocalScale, b.LocalScale, t)
            };
        }

        public static RectSnapshot WithScale(RectSnapshot s, Vector3 scale)
        {
            s.LocalScale = scale;
            return s;
        }
    }

    struct CamSnapshot
    {
        public bool Valid;
        public Vector3 Position;
        public Quaternion Rotation;
        public bool Orthographic;
        public float OrthographicSize;
    }

    void Awake()
    {
        if (navigationController == null)
            navigationController = GetComponent<NavigationController>();
    }

    static float EaseOutCubic(float u)
    {
        return 1f - Mathf.Pow(1f - u, 3f);
    }

    RectTransform ResolveChromeGroupRoot(RectTransform configuredLeafOrPanel, RectTransform explicitChromeRoot)
    {
        if (explicitChromeRoot != null)
            return explicitChromeRoot;
        if (configuredLeafOrPanel == null)
            return null;
        var parentRt = configuredLeafOrPanel.parent as RectTransform;
        if (parentRt == null)
            return configuredLeafOrPanel;
        if (parentRt.childCount > 1 && parentRt.GetComponent<Canvas>() != null)
            return parentRt;
        return configuredLeafOrPanel;
    }

    RectTransform ResolveSmallShrinkRoot()
    {
        return ResolveChromeGroupRoot(smallMapRoot, smallMinimapChromeRoot);
    }

    RectTransform LargeTweenRoot()
    {
        return largeMinimapChromeRoot != null ? largeMinimapChromeRoot : largeMinimapRoot;
    }

    /// <summary>Entry point from radial Add wedge (defaults to POI).</summary>
    public void BeginFromRadial(RadialMenuNavigationController radial, Pathfinding pathfinding)
    {
        BeginFromRadial(radial, pathfinding, WaypointType.POI);
    }

    /// <summary>Entry point after user picked waypoint type on the radial. Radial stays open; use center Back to cancel.</summary>
    public void BeginFromRadial(RadialMenuNavigationController radial, Pathfinding pathfinding, WaypointType waypointType)
    {
        if (_busy)
        {
            Debug.LogError("MinimapWaypointPlacement: already busy.");
            radial?.ResetRadialToCategoriesAndOpen();
            return;
        }

        if (smallMapRoot == null || largeMinimapRoot == null || minimapRawImage == null)
        {
            Debug.LogError("MinimapWaypointPlacement: assign Small Map Root, Large Minimap Root, and Minimap Raw Image.");
            radial?.ResetRadialToCategoriesAndOpen();
            return;
        }

        if (!minimapRawImage.transform.IsChildOf(largeMinimapRoot) &&
            (largeMinimapChromeRoot == null || !minimapRawImage.transform.IsChildOf(largeMinimapChromeRoot)))
        {
            Debug.LogError("MinimapWaypointPlacement: Minimap Raw Image must be under Large Minimap Root or Large Minimap Chrome Root.");
            radial?.ResetRadialToCategoriesAndOpen();
            return;
        }

        _minimapCam = Nav != null && Nav.minimapCamera != null ? Nav.minimapCamera.GetComponent<Camera>() : null;
        if (_minimapCam == null)
        {
            Debug.LogError("MinimapWaypointPlacement: NavigationController.minimapCamera is not set.");
            radial?.ResetRadialToCategoriesAndOpen();
            return;
        }

        EnsurePlacementHostActiveForCoroutines();
        if (!gameObject.activeInHierarchy)
        {
            Debug.LogError(
                "MinimapWaypointPlacement: this GameObject is not active in the hierarchy (inactive parent?). Cannot run placement.");
            DeactivatePlacementHostChainWeActivated();
            radial?.ResetRadialToCategoriesAndOpen();
            return;
        }

        _smallRt = ResolveSmallShrinkRoot();
        _largeRt = LargeTweenRoot();
        _smallVisibleSnap = RectSnapshot.From(_smallRt);
        _smallGoneSnap = RectSnapshot.WithScale(_smallVisibleSnap, Vector3.zero);
        _largeRestoreParent = _largeRt.parent;
        _largeRestoreSiblingIndex = _largeRt.GetSiblingIndex();
        _largeUsedLayoutReparent = PlacementExpandedLayoutTargetIsUsableFor(_largeRt);
        RectSnapshot largeDesign = RectSnapshot.From(_largeRt);
        _largeHiddenSnap = RectSnapshot.WithScale(largeDesign, Vector3.zero);
        _largeShownSnap = RectSnapshot.WithScale(largeDesign, Vector3.one);

        if (MapUiRootIsUnderNavigation(_smallRt) || MapUiRootIsUnderNavigation(_largeRt))
        {
            ActivateAncestorsForPlacement();
            HideLegacyWaypointUiUnderNavigation();
        }

        EnsureWorldSpaceCanvasHasEventCamera();

        _radial = radial;
        _pathfind = pathfinding;
        _pathfind?.ClearTarget();
        _placementWaypointType = waypointType;
        _busy = true;

        _parentCanvas = _largeRt != null ? _largeRt.GetComponentInParent<Canvas>() : null;
        if (_parentCanvas != null)
        {
            _savedCanvasSort = _parentCanvas.sortingOrder;
            _parentCanvas.sortingOrder = _savedCanvasSort + canvasSortOrderBoost;
            _hadCanvasSortOverride = true;
        }

        _largeRt.gameObject.SetActive(true);
        ApplyRect(_largeRt, _largeHiddenSnap);

        CacheCamera();
        if (_expandRoutine != null)
            StopCoroutine(_expandRoutine);
        _expandRoutine = StartCoroutine(ExpandRoutine());
    }

    public bool IsPlacementInProgress => _busy;

    bool MapUiRootIsUnderNavigation(RectTransform rt)
    {
        if (rt == null || Nav == null)
            return false;
        return rt.transform.IsChildOf(Nav.transform);
    }

    bool PlacementExpandedLayoutTargetIsUsableFor(RectTransform mover)
    {
        if (placementExpandedLayoutTarget == null || mover == null)
            return false;
        if (placementExpandedLayoutTarget == mover)
            return false;
        if (placementExpandedLayoutTarget.transform.IsChildOf(mover))
            return false;
        if (placementExpandedLayoutTarget.parent == null)
            return false;
        if (mover.parent == null)
            return false;
        return true;
    }

    void ActivateAncestorsForPlacement()
    {
        _activatedAncestors.Clear();
        if (_smallRt != null && MapUiRootIsUnderNavigation(_smallRt))
            ActivateAncestorsForRect(_smallRt);
        if (_largeRt != null && MapUiRootIsUnderNavigation(_largeRt))
            ActivateAncestorsForRect(_largeRt);
    }

    void ActivateAncestorsForRect(RectTransform mapRt)
    {
        var nav = Nav;
        if (nav == null || mapRt == null)
            return;

        Transform navRoot = nav.transform;
        var chain = new List<Transform>();
        for (Transform t = mapRt.transform; t != null && t != navRoot; t = t.parent)
            chain.Add(t);

        chain.Reverse();
        foreach (Transform t in chain)
        {
            GameObject go = t.gameObject;
            if (!go.activeSelf)
            {
                go.SetActive(true);
                _activatedAncestors.Add(go);
            }
        }
    }

    void DeactivateAncestorsWeActivated()
    {
        for (int i = _activatedAncestors.Count - 1; i >= 0; i--)
        {
            GameObject go = _activatedAncestors[i];
            if (go != null)
                go.SetActive(false);
        }

        _activatedAncestors.Clear();
    }

    void EnsurePlacementHostActiveForCoroutines()
    {
        _activatedPlacementHostChain.Clear();
        if (gameObject.activeInHierarchy)
            return;

        Transform topInactive = transform;
        while (topInactive.parent != null && !topInactive.parent.gameObject.activeSelf)
            topInactive = topInactive.parent;

        var path = new List<Transform>();
        for (Transform t = transform; t != null; t = t.parent)
        {
            path.Add(t);
            if (t == topInactive)
                break;
        }

        path.Reverse();
        foreach (Transform t in path)
        {
            if (!t.gameObject.activeSelf)
            {
                t.gameObject.SetActive(true);
                _activatedPlacementHostChain.Add(t.gameObject);
            }
        }
    }

    void DeactivatePlacementHostChainWeActivated()
    {
        for (int i = _activatedPlacementHostChain.Count - 1; i >= 0; i--)
        {
            GameObject go = _activatedPlacementHostChain[i];
            if (go != null)
                go.SetActive(false);
        }

        _activatedPlacementHostChain.Clear();
    }

    void HideLegacyWaypointUiUnderNavigation()
    {
        var nc = Nav;
        if (nc == null)
            return;

        static void Off(GameObject go)
        {
            if (go != null)
                go.SetActive(false);
        }

        Off(nc.CreateWaypointScreen);
        Off(nc.NavigationScreen);
        Off(nc.verticalButtonScreen);
        Off(nc.addWaypointButton);
        Off(nc.CompanionScreen);
        Off(nc.POIScreen);
        Off(nc.StationScreen);
        Off(nc.GeoScreen);
        Off(nc.DangerScreen);
    }

    void CacheCamera()
    {
        _camCollapsed = new CamSnapshot
        {
            Valid = true,
            Position = _minimapCam.transform.position,
            Rotation = _minimapCam.transform.rotation,
            Orthographic = _minimapCam.orthographic,
            OrthographicSize = _minimapCam.orthographicSize
        };

        _followScript = _minimapCam.GetComponent<MinimapCameraScript>();
        if (_followScript != null)
        {
            _hadFollowScript = _followScript.enabled;
            _followScript.enabled = false;
        }
    }

    void ApplyPlacementCamera()
    {
        _minimapCam.orthographic = true;
        _minimapCam.transform.SetPositionAndRotation(
            new Vector3(0f, placementCameraHeight, 0f),
            Quaternion.Euler(90f, 0f, 0f));
        _minimapCam.orthographicSize = placementOrthographicSize;
    }

    void RestoreCamera()
    {
        if (!_camCollapsed.Valid || _minimapCam == null)
            return;
        _minimapCam.orthographic = _camCollapsed.Orthographic;
        _minimapCam.orthographicSize = _camCollapsed.OrthographicSize;
        _minimapCam.transform.SetPositionAndRotation(_camCollapsed.Position, _camCollapsed.Rotation);
        if (_followScript != null && _hadFollowScript)
            _followScript.enabled = true;
    }

    IEnumerator ExpandRoutine()
    {
        _phase = PlacementPhase.AnimatingExpand;
        SetSmallChromeRaycastsBlocked(true);
        minimapRawImage.raycastTarget = true;

        if (_largeUsedLayoutReparent)
        {
            _largeRt.SetParent(placementExpandedLayoutTarget.parent, worldPositionStays: true);
            _largeRt.SetSiblingIndex(placementExpandedLayoutTarget.GetSiblingIndex() + 1);
            RectSnapshot largeFrom = RectSnapshot.WithScale(RectSnapshot.From(_largeRt), Vector3.zero);
            RectSnapshot largeTo = RectSnapshot.From(placementExpandedLayoutTarget);
            yield return DualTweenRect(_smallRt, _smallVisibleSnap, _smallGoneSnap, _largeRt, largeFrom, largeTo, tweenDuration);
        }
        else
        {
            yield return DualTweenRect(_smallRt, _smallVisibleSnap, _smallGoneSnap, _largeRt, _largeHiddenSnap, _largeShownSnap, tweenDuration);
        }

        ApplyPlacementCamera();
        EnsureClickReceiver();
        CreatePlacementCursor();
        _phase = PlacementPhase.AwaitingClick;
        _expandRoutine = null;
    }

    void SetSmallChromeRaycastsBlocked(bool blocked)
    {
        if (_smallRt == null)
            return;
        if (blocked)
        {
            if (_smallRaycastBlockedCached)
                return;
            _smallGraphicRaycastRestore.Clear();
            foreach (Graphic g in _smallRt.GetComponentsInChildren<Graphic>(true))
            {
                _smallGraphicRaycastRestore.Add((g, g.raycastTarget));
                g.raycastTarget = false;
            }

            _smallRaycastBlockedCached = true;
        }
        else if (_smallRaycastBlockedCached)
        {
            for (int i = 0; i < _smallGraphicRaycastRestore.Count; i++)
            {
                (Graphic g, bool prev) = _smallGraphicRaycastRestore[i];
                if (g != null)
                    g.raycastTarget = prev;
            }

            _smallGraphicRaycastRestore.Clear();
            _smallRaycastBlockedCached = false;
        }
    }

    IEnumerator DualTweenRect(
        RectTransform smallRt,
        RectSnapshot smallFrom,
        RectSnapshot smallTo,
        RectTransform largeRt,
        RectSnapshot largeFrom,
        RectSnapshot largeTo,
        float duration)
    {
        float elapsed = 0f;
        while (elapsed < duration)
        {
            elapsed += Time.deltaTime;
            float u = Mathf.Clamp01(elapsed / duration);
            float e = EaseOutCubic(u);
            ApplyRect(smallRt, RectSnapshot.Lerp(smallFrom, smallTo, e));
            ApplyRect(largeRt, RectSnapshot.Lerp(largeFrom, largeTo, e));
            yield return null;
        }

        ApplyRect(smallRt, smallTo);
        ApplyRect(largeRt, largeTo);
    }

    static void ApplyRect(RectTransform rt, RectSnapshot s)
    {
        rt.anchorMin = s.AnchorMin;
        rt.anchorMax = s.AnchorMax;
        rt.pivot = s.Pivot;
        rt.anchoredPosition = s.AnchoredPosition;
        rt.sizeDelta = s.SizeDelta;
        rt.localScale = s.LocalScale;
    }

    // ── World Space Canvas camera ──────────────────────────

    void EnsureWorldSpaceCanvasHasEventCamera()
    {
        if (minimapRawImage == null)
            return;

        Canvas c = minimapRawImage.canvas;
        while (c != null && !c.isRootCanvas)
            c = c.transform.parent != null ? c.transform.parent.GetComponentInParent<Canvas>() : null;

        if (c == null || c.renderMode != RenderMode.WorldSpace)
            return;
        if (c.worldCamera != null)
            return;

        Camera cam = Camera.main;
        if (cam == null && Camera.allCamerasCount > 0)
            cam = Camera.allCameras[0];
        if (cam != null)
            c.worldCamera = cam;
    }

    // ── Collider + PressableButton (MRTK3 XRI click) ──────

    void EnsureClickReceiver()
    {
        if (minimapRawImage == null)
            return;

        GameObject go = minimapRawImage.gameObject;

        _addedCollider = go.GetComponent<BoxCollider>();
        if (_addedCollider == null)
            _addedCollider = go.AddComponent<BoxCollider>();
        SizeColliderToRect(_addedCollider, minimapRawImage.rectTransform);

        _addedButton = go.GetComponent<PressableButton>();
        if (_addedButton == null)
            _addedButton = go.AddComponent<PressableButton>();
        _addedButton.OnClicked.AddListener(OnPressableClicked);
    }

    void SizeColliderToRect(BoxCollider col, RectTransform rt)
    {
        Rect r = rt.rect;
        col.size = new Vector3(r.width, r.height, 0.01f);
        col.center = new Vector3(r.center.x, r.center.y, 0f);
    }

    void OnPressableClicked()
    {
        if (!_busy || _phase != PlacementPhase.AwaitingClick || _addedCollider == null)
            return;

        if (!TryGetWorldFromColliderHit(out Vector3 world))
            return;

        _phase = PlacementPhase.Processing;
        StartCoroutine(CollapseAndPublishRoutine(world));
    }

    void RemoveClickReceiver()
    {
        if (_addedButton != null)
        {
            _addedButton.OnClicked.RemoveListener(OnPressableClicked);
            Destroy(_addedButton);
            _addedButton = null;
        }

        if (_addedCollider != null)
        {
            Destroy(_addedCollider);
            _addedCollider = null;
        }

        DestroyPlacementCursor();
    }

    // ── Hit conversion (3D collider hit → minimap UV → world) ──

    bool TryRaycastMinimapCollider(out Vector3 hitWorldPoint, out Vector2 localPoint)
    {
        hitWorldPoint = default;
        localPoint = default;

        if (_addedCollider == null || minimapRawImage == null)
            return false;

        Camera cam = Camera.main;
        if (cam == null)
            return false;

        Vector2 mousePos = Mouse.current != null ? Mouse.current.position.ReadValue() : Vector2.zero;
        if (Mouse.current == null)
            return false;

        Ray ray = cam.ScreenPointToRay(mousePos);
        if (!_addedCollider.Raycast(ray, out RaycastHit hit, 100f))
            return false;

        hitWorldPoint = hit.point;
        localPoint = minimapRawImage.rectTransform.InverseTransformPoint(hit.point);
        return true;
    }

    bool TryGetWorldFromColliderHit(out Vector3 worldHit)
    {
        worldHit = default;

        if (!TryRaycastMinimapCollider(out _, out Vector2 local))
            return false;

        return LocalPointToWorld(local, out worldHit);
    }

    bool LocalPointToWorld(Vector2 local, out Vector3 worldHit)
    {
        worldHit = default;
        if (minimapRawImage == null || _minimapCam == null)
            return false;

        Rect r = minimapRawImage.rectTransform.rect;
        float u = Mathf.InverseLerp(r.xMin, r.xMax, local.x);
        float v = Mathf.InverseLerp(r.yMin, r.yMax, local.y);

        Ray ray = _minimapCam.ViewportPointToRay(new Vector3(u, v, 0f));
        var plane = new Plane(Vector3.up, Vector3.zero);
        if (!plane.Raycast(ray, out float enter))
            return false;

        worldHit = ray.GetPoint(enter);
        worldHit.y = 0f;

        if (maxPlaceRadiusFromOrigin > 0f)
        {
            var xz = new Vector2(worldHit.x, worldHit.z);
            if (xz.magnitude > maxPlaceRadiusFromOrigin)
            {
                xz = xz.normalized * maxPlaceRadiusFromOrigin;
                worldHit.x = xz.x;
                worldHit.z = xz.y;
            }
        }

        return true;
    }

    // ── Placement cursor (yellow indicator under pointer) ──

    void CreatePlacementCursor()
    {
        DestroyPlacementCursor();
        if (minimapRawImage == null)
            return;

        float span = Mathf.Max(4f, placementCrosshairSpan);
        float thick = Mathf.Max(1f, placementCrosshairThickness);

        _cursorGo = new GameObject("PlacementCursor");
        _cursorGo.transform.SetParent(minimapRawImage.rectTransform, false);
        var rootRt = _cursorGo.AddComponent<RectTransform>();
        rootRt.anchorMin = rootRt.anchorMax = new Vector2(0.5f, 0.5f);
        rootRt.pivot = new Vector2(0.5f, 0.5f);
        rootRt.sizeDelta = Vector2.zero;
        rootRt.anchoredPosition = Vector2.zero;

        CreateCrosshairBar(_cursorGo.transform, new Vector2(span, thick), placementCrosshairColor);
        CreateCrosshairBar(_cursorGo.transform, new Vector2(thick, span), placementCrosshairColor);

        _cursorGo.SetActive(false);
    }

    static void CreateCrosshairBar(Transform parent, Vector2 sizeDelta, Color color)
    {
        var go = new GameObject(sizeDelta.x > sizeDelta.y ? "Crosshair_H" : "Crosshair_V");
        go.transform.SetParent(parent, false);
        var rt = go.AddComponent<RectTransform>();
        rt.anchorMin = rt.anchorMax = new Vector2(0.5f, 0.5f);
        rt.pivot = new Vector2(0.5f, 0.5f);
        rt.sizeDelta = sizeDelta;
        rt.anchoredPosition = Vector2.zero;
        var img = go.AddComponent<Image>();
        img.color = color;
        img.raycastTarget = false;
    }

    void DestroyPlacementCursor()
    {
        if (_cursorGo != null)
        {
            Destroy(_cursorGo);
            _cursorGo = null;
        }
    }

    void Update()
    {
        if (_phase != PlacementPhase.AwaitingClick || _cursorGo == null)
            return;

        if (TryRaycastMinimapCollider(out _, out Vector2 local))
        {
            Rect r = minimapRawImage.rectTransform.rect;
            if (r.Contains(local))
            {
                var rt = _cursorGo.GetComponent<RectTransform>();
                if (rt != null)
                    rt.anchoredPosition = local;
                _cursorGo.SetActive(true);
                return;
            }
        }

        _cursorGo.SetActive(false);
    }

    // ── Publish + collapse ─────────────────────────────────

    IEnumerator CollapseAndPublishRoutine(Vector3 world)
    {
        RemoveClickReceiver();
        PublishWaypoint(world);
        yield return AnimateCollapseToRestRoutine();
        EndPlacementCommon();
    }

    IEnumerator AnimateCollapseToRestRoutine()
    {
        RectSnapshot largeStart = RectSnapshot.From(_largeRt);
        if (_largeUsedLayoutReparent && _largeRestoreParent != null)
        {
            _largeRt.SetParent(_largeRestoreParent, worldPositionStays: true);
            largeStart = RectSnapshot.From(_largeRt);
        }

        yield return DualTweenRect(
            _smallRt,
            RectSnapshot.From(_smallRt),
            _smallVisibleSnap,
            _largeRt,
            largeStart,
            _largeHiddenSnap,
            tweenDuration);

        if (_largeUsedLayoutReparent)
            _largeRt.SetSiblingIndex(_largeRestoreSiblingIndex);

        SetSmallChromeRaycastsBlocked(false);
        if (minimapRawImage != null)
            minimapRawImage.raycastTarget = false;
    }

    void PublishWaypoint(Vector3 world)
    {
        var nav = Nav;
        if (nav == null)
            return;

        int nextId = nav.waypointList != null ? nav.waypointList.Count + 1 : 1;
        int indexForName = 0;
        switch (_placementWaypointType)
        {
            case WaypointType.STATION:
                indexForName = nav.StationWaypointList != null ? nav.StationWaypointList.Count : 0;
                break;
            case WaypointType.DANGER:
                indexForName = nav.DangerWaypointList != null ? nav.DangerWaypointList.Count : 0;
                break;
            default:
                indexForName = nav.POIWaypointList != null ? nav.POIWaypointList.Count : 0;
                break;
        }

        string name = WaypointNamingHelper.DefaultAddName(_placementWaypointType, indexForName);

        AuthorType author = AuthorType.EV1;
        if (AstronautInstance.User != null)
            author = AstronautInstance.User.id == 1 ? AuthorType.EV1 : AuthorType.EV2;

        var wp = new Waypoint
        {
            Use = "ADD",
            Id = nextId,
            Name = name,
            UNITYposX = world.x,
            UNITYposZ = world.z,
            Type = _placementWaypointType,
            Author = author
        };

        EventBus.Publish(new WaypointAddedEvent(wp));
    }

    void EndPlacementCommon()
    {
        RestoreCamera();
        if (_hadCanvasSortOverride && _parentCanvas != null)
        {
            _parentCanvas.sortingOrder = _savedCanvasSort;
            _hadCanvasSortOverride = false;
        }

        RemoveClickReceiver();

        DeactivateAncestorsWeActivated();
        DeactivatePlacementHostChainWeActivated();

        _radial?.ResetRadialToCategoriesAndOpen();
        _radial = null;
        _pathfind = null;
        _busy = false;
        _phase = PlacementPhase.Idle;
        _placementWaypointType = WaypointType.POI;
    }

    public void CancelPlacement()
    {
        if (!_busy)
            return;
        if (_phase == PlacementPhase.Processing)
            return;

        if (_phase != PlacementPhase.AwaitingClick && _phase != PlacementPhase.AnimatingExpand)
            return;

        StopAllCoroutines();
        _expandRoutine = null;
        StartCoroutine(CancelRoutine());
    }

    IEnumerator CancelRoutine()
    {
        _phase = PlacementPhase.Processing;
        RemoveClickReceiver();
        yield return AnimateCollapseToRestRoutine();
        EndPlacementCommon();
    }
}
