using UnityEngine;
using UnityEngine.Events;
using UnityEngine.Rendering;
using System.Collections;
using System.Collections.Generic;
using TMPro;
using MixedReality.Toolkit.UX;

[System.Serializable]
public class RadialMenuEntry
{
    public string label;
    [Tooltip("Single character or emoji shown on the wedge if Icon Sprite is not set.")]
    public string iconUnicode;
    [Tooltip("Optional: assign a sprite to show an image on the wedge instead of icon Unicode text. Takes priority over Icon Unicode.")]
    public Sprite iconSprite;
    public UnityEvent onClick;
}

public class RadialMenuBuilder : MonoBehaviour
{
    [Header("Layout")]
    [Range(2, 12)]
    public int segmentCount = 5;

    [Tooltip("Inner radius where wedge geometry starts (meters). Set greater than Center Disc Radius by a few mm to leave a radial gap so the hub does not overlap wedges.")]
    public float innerRadius = 0.04f;
    public float outerRadius = 0.09f;

    [Tooltip("Thickness / depth of the wedge plate (meters)")]
    public float thickness = 0.002f;

    public float gapDegrees = 4f;

    [Tooltip("90 = first wedge starts at top")]
    public float startAngleOffset = 90f;

    public int arcSegments = 24;

    [Header("Visuals")]
    [Tooltip("Material for front/back faces of wedges")]
    public Material wedgeMaterial;

    [Tooltip("Material for the side edges (lighter color for MRTK-style border)")]
    public Material edgeMaterial;

    public Material centerMaterial;

    [Tooltip("Radius of the center hub mesh and collider (meters), independent of Inner Radius. Increase Inner Radius (and optionally Outer Radius) to spread wedges outward without changing hub size.")]
    public float centerDiscRadius = 0.035f;

    public Color wedgeTint = new Color(0.15f, 0.2f, 0.55f, 1f);

    [Tooltip("Tint for the side edges — typically lighter than wedgeTint")]
    public Color edgeTint = new Color(0.6f, 0.65f, 0.85f, 1f);

    [Tooltip("Local -Z offset (meters) for the rim overlay mesh toward the viewer (MRTK-style frontplate separation).")]
    [SerializeField] private float rimForwardOffset = 0.005f;

    [Header("Interaction")]
    [Tooltip("Minimum collider extent along local Z (meters) for PressableButton / XRI; matches the idea used on the minimap (≈1 cm) so thin plates are easier to hit.")]
    [SerializeField] private float interactionColliderMinDepth = 0.01f;
    [Tooltip("Meters beyond Center Disc Radius: wedge InteractionDepth boxes are clamped so no XY corner comes closer to the hub axis than this (avoids stealing center hits).")]
    [SerializeField] private float wedgeDepthHubClearance = 0.005f;
    [Tooltip("Floor on wedge InteractionDepth width/height in the plate plane (meters); shrink steps stop here so poke still has some volume.")]
    [SerializeField] private float wedgeDepthMinPlanarSize = 0.012f;

    [Header("Icons")]
    public TMP_FontAsset iconFont;
    public float iconSize = 0.5f;
    [Tooltip("Scale of sprite icons on wedges (smaller = smaller icons). Multiplied by wedge width.")]
    [Range(0.1f, 1f)]
    public float iconSpriteScale = 0.25f;

    [Header("Label tab (gaze)")]
    [Tooltip("Uniform scale on the duplicate wedge mesh when the gaze label tab is fully open.")]
    [SerializeField] private float labelExtensionMaxScale = 1.1f;
    [SerializeField] private float labelExtensionTweenDuration = 0.2f;
    [Tooltip("Local +Z offset (meters) on the scaled duplicate: pushes it behind the main wedge (away from the viewer) to reduce z-fighting with the wedge face and icon.")]
    [SerializeField] private float labelExtensionVisualZBias = 0.001f;
    [Tooltip("Where the label sits radially between the original outer arc (t=0) and scaled outer arc (t=1).")]
    [Range(0f, 1f)]
    [SerializeField] private float labelExtensionRadialT = 0.52f;
    [SerializeField] private float labelExtensionFontSize = 0.125f;
    [Tooltip("Extra outward radial offset at full gaze (meters).")]
    [SerializeField] private float labelExtensionRadialRevealPop = 0.004f;
    [Tooltip("Angular inset from each wedge edge (degrees) so curved text stays inside the wedge.")]
    [SerializeField] private float labelExtensionAngleMarginDegrees = 2.5f;
    [Tooltip("If text reads backwards along the arc, enable to swap start/end mapping.")]
    [SerializeField] private bool labelExtensionInvertArcText = false;

    [Header("Menu Items")]
    [Tooltip("Assign label and Icon Sprite (or Icon Unicode) per entry in the Inspector. For static menus, set these before play; they are used when the menu is built.")]
    public List<RadialMenuEntry> entries = new List<RadialMenuEntry>();

    [Header("Center Button")]
    [Tooltip("Label shown in the center (e.g. 'Begin Navigation' or 'Back'). Updated at runtime via SetCenterLabel().")]
    public string centerLabel = "";
    [Tooltip("Font size for the center button label.")]
    [SerializeField] private float centerLabelFontSize = 0.22f;
    public UnityEvent onCenterClick;

    [Header("Animation")]
    public float animationDuration = 0.25f;
    public bool startHidden = false;

    private GameObject centerDisc;
    private TextMeshPro centerLabelTMP;
    private bool isOpen;
    private Coroutine animCoroutine;

    private static readonly int BaseColorId = Shader.PropertyToID("_Base_Color_");
    private static readonly int ColorId = Shader.PropertyToID("_Color");
    private static readonly int BaseColorUrpId = Shader.PropertyToID("_BaseColor");
    private static readonly int RimUvModeId = Shader.PropertyToID("_RimUvMode");
    private static readonly int AngleSpanRadId = Shader.PropertyToID("_AngleSpanRad");
    private static readonly int InnerRadiusShaderId = Shader.PropertyToID("_InnerRadius");
    private static readonly int OuterRadiusShaderId = Shader.PropertyToID("_OuterRadius");
    private static readonly int RimHighlightId = Shader.PropertyToID("_RimHighlight");
    private static readonly int RimColorId = Shader.PropertyToID("_RimColor");
    private static readonly int RimWidthWorldId = Shader.PropertyToID("_RimWidthWorld");
    private static readonly int RimSoftnessWorldId = Shader.PropertyToID("_RimSoftnessWorld");
    private static readonly int RimWidthUvId = Shader.PropertyToID("_RimWidth");
    private static readonly int RimSoftnessUvId = Shader.PropertyToID("_RimSoftness");

    void OnValidate()
    {
        if (innerRadius < centerDiscRadius)
            Debug.LogWarning(
                $"{nameof(RadialMenuBuilder)} on '{name}': {nameof(innerRadius)} ({innerRadius}) is less than {nameof(centerDiscRadius)} ({centerDiscRadius}). The hub overlaps the wedges radially; increase Inner Radius to add clearance.",
                this);
    }

    void Start()
    {
        BuildMenu();
        if (startHidden)
        {
            transform.localScale = Vector3.zero;
            isOpen = false;
        }
        else
        {
            isOpen = true;
        }
    }

    public void ToggleMenu()
    {
        if (isOpen) CloseMenu(); else OpenMenu();
    }

    public void OpenMenu()
    {
        if (isOpen) return;
        isOpen = true;
        if (animCoroutine != null) StopCoroutine(animCoroutine);
        animCoroutine = null;
        // StartCoroutine requires active GameObject, apply final state if inactive (e.g. ScreenManager hides menu)
        if (!gameObject.activeInHierarchy)
        {
            transform.localScale = Vector3.one;
            return;
        }
        animCoroutine = StartCoroutine(AnimateScale(Vector3.zero, Vector3.one));
    }

    public void CloseMenu()
    {
        if (!isOpen) return;
        isOpen = false;
        if (animCoroutine != null) StopCoroutine(animCoroutine);
        animCoroutine = null;
        if (!gameObject.activeInHierarchy)
        {
            transform.localScale = Vector3.zero;
            return;
        }
        animCoroutine = StartCoroutine(AnimateScale(Vector3.one, Vector3.zero));
    }

    private IEnumerator AnimateScale(Vector3 from, Vector3 to)
    {
        float elapsed = 0f;
        transform.localScale = from;
        while (elapsed < animationDuration)
        {
            elapsed += Time.deltaTime;
            float t = Mathf.Clamp01(elapsed / animationDuration);
            float eased = 1f - Mathf.Pow(1f - t, 3f);
            transform.localScale = Vector3.Lerp(from, to, eased);
            yield return null;
        }
        transform.localScale = to;
        animCoroutine = null;
    }

    // ── Build ──────────────────────────────────────────────

    [ContextMenu("Rebuild Menu")]
    public void BuildMenu()
    {
        ClearChildren();
        CreateCenterDisc();
        CreateWedges();
    }

    private void ClearChildren()
    {
        for (int i = transform.childCount - 1; i >= 0; i--)
        {
            if (Application.isPlaying)
                Destroy(transform.GetChild(i).gameObject);
            else
                DestroyImmediate(transform.GetChild(i).gameObject);
        }
        centerDisc = null;
        centerLabelTMP = null;
    }

    private void ApplyTint(Material mat, Color tint)
    {
        if (mat.HasProperty(BaseColorId))
            mat.SetColor(BaseColorId, tint);
        if (mat.HasProperty(BaseColorUrpId))
            mat.SetColor(BaseColorUrpId, tint);
        if (mat.HasProperty(ColorId))
            mat.SetColor(ColorId, tint);
    }

    private Material ResolveFaceMaterial(Material preferred)
    {
        if (preferred != null) return preferred;
        return GetDefaultRadialFaceMaterial();
    }

    private Material GetDefaultRadialFaceMaterial()
    {
        Shader sh = Shader.Find("CLAWS/RadialWedgeFace");
        if (sh == null || !sh.isSupported)
            return GetFallbackMaterial();
        return new Material(sh);
    }

    private static void ConfigureFaceRimUv(Material faceMat, float rimUvMode)
    {
        if (faceMat != null && faceMat.HasProperty(RimUvModeId))
            faceMat.SetFloat(RimUvModeId, rimUvMode);
    }

    private static void CopyRadialRimMaterialSettings(Material source, Material dest)
    {
        if (source == null || dest == null) return;
        void CopyFloat(int id)
        {
            if (source.HasProperty(id) && dest.HasProperty(id))
                dest.SetFloat(id, source.GetFloat(id));
        }
        void CopyColor(int id)
        {
            if (source.HasProperty(id) && dest.HasProperty(id))
                dest.SetColor(id, source.GetColor(id));
        }
        CopyFloat(RimUvModeId);
        CopyFloat(AngleSpanRadId);
        CopyFloat(InnerRadiusShaderId);
        CopyFloat(OuterRadiusShaderId);
        CopyFloat(RimWidthWorldId);
        CopyFloat(RimSoftnessWorldId);
        CopyFloat(RimWidthUvId);
        CopyFloat(RimSoftnessUvId);
        CopyColor(RimColorId);
    }

    private void TryAddRimOverlayChild(GameObject root, Material faceMat, Mesh frontFaceMesh)
    {
        if (root == null || frontFaceMesh == null || faceMat == null) return;
        if (!faceMat.HasProperty(RimHighlightId)) return;
        Shader rimSh = Shader.Find("CLAWS/RadialWedgeRimOverlay");
        if (rimSh == null || !rimSh.isSupported) return;

        faceMat.SetFloat(RimHighlightId, 0f);
        Material rimMat = new Material(rimSh);
        CopyRadialRimMaterialSettings(faceMat, rimMat);
        rimMat.SetFloat(RimHighlightId, 0f);

        GameObject overlay = new GameObject(RadialWedgeHighlight.RimOverlayTransformName);
        overlay.transform.SetParent(root.transform, false);
        overlay.transform.localPosition = new Vector3(0f, 0f, -rimForwardOffset);
        overlay.transform.localRotation = Quaternion.identity;
        overlay.transform.localScale = Vector3.one;

        MeshFilter omf = overlay.AddComponent<MeshFilter>();
        omf.sharedMesh = frontFaceMesh;
        MeshRenderer omr = overlay.AddComponent<MeshRenderer>();
        omr.sharedMaterial = rimMat;
        omr.shadowCastingMode = ShadowCastingMode.Off;
        omr.receiveShadows = false;
    }

    /// <summary>World-space rim on wedge faces so outline stays thin for large angular spans (e.g. 180°).</summary>
    private void ConfigureWedgeFaceRimGeometry(Material faceMat, float startDeg, float endDeg)
    {
        if (faceMat == null || !faceMat.HasProperty(AngleSpanRadId)) return;
        float spanDeg = Mathf.Abs(endDeg - startDeg);
        faceMat.SetFloat(AngleSpanRadId, spanDeg * Mathf.Deg2Rad);
        if (faceMat.HasProperty(InnerRadiusShaderId))
            faceMat.SetFloat(InnerRadiusShaderId, innerRadius);
        if (faceMat.HasProperty(OuterRadiusShaderId))
            faceMat.SetFloat(OuterRadiusShaderId, outerRadius);
    }

    private Material GetFallbackMaterial()
    {
        Material mat = new Material(Shader.Find("Universal Render Pipeline/Lit"));
        if (mat.shader == null || mat.shader.name == "Hidden/InternalErrorShader")
            mat = new Material(Shader.Find("Standard"));
        mat.color = wedgeTint;
        return mat;
    }

    private Material ResolveMaterial(Material preferred, Material fallback)
    {
        if (preferred != null) return preferred;
        if (fallback != null) return fallback;
        return GetFallbackMaterial();
    }

    /// <summary>Disable MRTK StateVisualizer on procedural buttons to avoid NullReferenceException (it expects prefab targets).</summary>
    private static void DisableStateVisualizer(GameObject go)
    {
        if (go == null) return;
        DisableStateVisualizerOn(go);
        for (int i = 0; i < go.transform.childCount; i++)
            DisableStateVisualizerOn(go.transform.GetChild(i).gameObject);
    }

    private static void DisableStateVisualizerOn(GameObject target)
    {
        foreach (var c in target.GetComponents<MonoBehaviour>())
        {
            if (c != null && c.GetType().Name == "StateVisualizer")
            {
                c.enabled = false;
                return;
            }
        }
    }

    /// <summary>Convex mesh collider matching rendered geometry (avoids axis-aligned box overlap with the hub / neighbors that caused hover churn).</summary>
    private static void AddConvexMeshCollider(GameObject target, Mesh mesh)
    {
        var mc = target.AddComponent<MeshCollider>();
        mc.sharedMesh = mesh;
        mc.convex = true;
    }

    /// <summary>Wedges: exact mesh for raycasts (convex hulls on thin annular slices are unreliable). Static collider, no Rigidbody.</summary>
    private static void AddNonConvexMeshCollider(GameObject target, Mesh mesh)
    {
        var mc = target.AddComponent<MeshCollider>();
        mc.sharedMesh = mesh;
        mc.convex = false;
    }

    /// <summary>Poke depth aligned to wedge bisector; XY clamped so OBB corners stay outside the hub guard (center disc + clearance).</summary>
    private void TryAddWedgeFrontDepthCollider(GameObject wedgeRoot, float startDeg, float endDeg)
    {
        float depth = Mathf.Max(interactionColliderMinDepth, 1e-4f);
        if (depth <= thickness + 1e-5f)
            return;

        float halfT = thickness * 0.5f;
        float midDeg = (startDeg + endDeg) * 0.5f;
        float midRad = midDeg * Mathf.Deg2Rad;
        float midR = (innerRadius + outerRadius) * 0.5f;
        float halfDeltaRad = Mathf.Abs(endDeg - startDeg) * 0.5f * Mathf.Deg2Rad;
        halfDeltaRad = Mathf.Max(halfDeltaRad, 1e-5f);

        float radialSpan = outerRadius - innerRadius;
        float tangentialSpan = 2f * midR * Mathf.Tan(halfDeltaRad);

        const float inset = 0.92f;
        float sizeX = Mathf.Max(radialSpan * inset, 1e-4f);
        float sizeY = Mathf.Max(tangentialSpan * inset, 1e-4f);
        float radialDist = midR;

        ClampWedgeDepthBoxForHub(midRad, ref sizeX, ref sizeY, ref radialDist);

        GameObject depthGo = new GameObject("InteractionDepth");
        depthGo.transform.SetParent(wedgeRoot.transform, false);
        depthGo.transform.localRotation = Quaternion.Euler(0f, 0f, midDeg);
        depthGo.transform.localPosition = new Vector3(
            Mathf.Cos(midRad) * radialDist,
            Mathf.Sin(midRad) * radialDist,
            -halfT - depth * 0.5f);

        var box = depthGo.AddComponent<BoxCollider>();
        box.center = Vector3.zero;
        box.size = new Vector3(sizeX, sizeY, depth);
    }

    /// <summary>Shrinks Y then X, then nudges the box outward along the bisector until all four XY corners are at least hubGuardRadius from the origin and inside outerRadius.</summary>
    private void ClampWedgeDepthBoxForHub(float midRad, ref float sizeX, ref float sizeY, ref float radialDist)
    {
        float hubGuardRadius = Mathf.Max(
            centerDiscRadius + Mathf.Max(0f, wedgeDepthHubClearance),
            innerRadius + 1e-4f);
        float hubGuardSqr = hubGuardRadius * hubGuardRadius;
        float outerLimit = Mathf.Max(outerRadius - 0.002f, innerRadius + 1e-4f);

        float halfFloor = Mathf.Max(1e-4f, wedgeDepthMinPlanarSize * 0.5f);

        Vector2 u = new Vector2(Mathf.Cos(midRad), Mathf.Sin(midRad));
        Vector2 v = new Vector2(-u.y, u.x);

        void CornerMinMax(float rDist, float hx, float hy, out float minSqr, out float maxR)
        {
            Vector2 c = u * rDist;
            minSqr = float.MaxValue;
            maxR = 0f;
            for (int du = -1; du <= 1; du += 2)
            {
                for (int dv = -1; dv <= 1; dv += 2)
                {
                    Vector2 p = c + u * (hx * du) + v * (hy * dv);
                    float s = p.sqrMagnitude;
                    minSqr = Mathf.Min(minSqr, s);
                    maxR = Mathf.Max(maxR, Mathf.Sqrt(s));
                }
            }
        }

        float hx = sizeX * 0.5f;
        float hy = sizeY * 0.5f;

        for (int iter = 0; iter < 220; iter++)
        {
            CornerMinMax(radialDist, hx, hy, out float minSqr, out float maxR);
            bool tooCloseToHub = minSqr < hubGuardSqr;
            bool pastOuter = maxR > outerLimit;

            if (!tooCloseToHub && !pastOuter)
                break;

            if (tooCloseToHub)
            {
                if (hy > halfFloor + 1e-6f)
                    hy = Mathf.Max(halfFloor, hy * 0.9f);
                else if (hx > halfFloor + 1e-6f)
                    hx = Mathf.Max(halfFloor, hx * 0.9f);
                else
                    radialDist = Mathf.Min(radialDist + 0.0015f, outerLimit - hx - hy);
            }

            if (pastOuter)
            {
                hx = Mathf.Max(halfFloor, hx * 0.95f);
                hy = Mathf.Max(halfFloor, hy * 0.95f);
            }
        }

        sizeX = hx * 2f;
        sizeY = hy * 2f;
    }

    /// <summary>Extra poke depth for the hub only: thin box on the front face, XY limited to a square inscribed in the disc so it does not extend past the circle into wedges.</summary>
    private void TryAddCenterFrontDepthCollider(GameObject centerRoot, float discRadius, float plateThickness)
    {
        float depth = Mathf.Max(interactionColliderMinDepth, 1e-4f);
        if (depth <= plateThickness + 1e-5f)
            return;

        float halfT = plateThickness * 0.5f;
        float inset = discRadius * Mathf.Sqrt(2f) * 0.98f;

        GameObject depthGo = new GameObject("InteractionDepth");
        depthGo.transform.SetParent(centerRoot.transform, false);
        depthGo.transform.localPosition = new Vector3(0f, 0f, -halfT - depth * 0.5f);
        depthGo.transform.localRotation = Quaternion.identity;
        depthGo.transform.localScale = Vector3.one;

        var box = depthGo.AddComponent<BoxCollider>();
        box.center = Vector3.zero;
        box.size = new Vector3(inset, inset, depth);
    }

    // ── Center Disc ────────────────────────────────────────

    private void CreateCenterDisc()
    {
        centerDisc = new GameObject("CenterDisc");
        centerDisc.transform.SetParent(transform, false);

        MeshFilter mf = centerDisc.AddComponent<MeshFilter>();
        MeshRenderer mr = centerDisc.AddComponent<MeshRenderer>();

        Mesh discMesh = CreateExtrudedDiscMesh(centerDiscRadius, thickness, 32);
        mf.sharedMesh = discMesh;

        Material faceSource = centerMaterial != null ? centerMaterial : wedgeMaterial;
        Material faceMat = new Material(ResolveFaceMaterial(faceSource));
        ApplyTint(faceMat, wedgeTint);
        ConfigureFaceRimUv(faceMat, 1f);
        if (faceMat.HasProperty(AngleSpanRadId))
            faceMat.SetFloat(AngleSpanRadId, 0f);
        Material sideMat = new Material(ResolveMaterial(edgeMaterial, wedgeMaterial));
        ApplyTint(sideMat, edgeTint);
        mr.sharedMaterials = new Material[] { faceMat, sideMat };

        Mesh discFrontOnly = CreateDiscFrontFaceMesh(centerDiscRadius, thickness, 32);
        TryAddRimOverlayChild(centerDisc, faceMat, discFrontOnly);

        AddConvexMeshCollider(centerDisc, discMesh);
        TryAddCenterFrontDepthCollider(centerDisc, centerDiscRadius, thickness);

        PressableButton centerBtn = centerDisc.AddComponent<PressableButton>();
        if (onCenterClick != null)
            centerBtn.OnClicked.AddListener(() => onCenterClick?.Invoke());
        DisableStateVisualizer(centerDisc);

        centerDisc.AddComponent<RadialWedgeHighlight>();

        GameObject labelGO = new GameObject("CenterLabel");
        labelGO.transform.SetParent(centerDisc.transform, false);
        labelGO.transform.localPosition = new Vector3(0, 0, -(thickness / 2f + 0.001f));
        centerLabelTMP = labelGO.AddComponent<TextMeshPro>();
        centerLabelTMP.text = centerLabel ?? "";
        centerLabelTMP.fontSize = centerLabelFontSize;
        centerLabelTMP.alignment = TextAlignmentOptions.Center;
        centerLabelTMP.color = Color.white;
        centerLabelTMP.enableWordWrapping = true;
        centerLabelTMP.overflowMode = TextOverflowModes.Overflow;
        centerLabelTMP.raycastTarget = false;
        labelGO.GetComponent<RectTransform>().sizeDelta = new Vector2(centerDiscRadius * 2f, centerDiscRadius * 2f);
        if (iconFont != null) centerLabelTMP.font = iconFont;
    }

    /// <summary>Update the center button label at runtime (e.g. "Begin Navigation" or "Back").</summary>
    public void SetCenterLabel(string label)
    {
        centerLabel = label ?? "";
        if (centerLabelTMP != null)
            centerLabelTMP.text = centerLabel;
    }

    // ── Wedges ─────────────────────────────────────────────

    private void CreateWedges()
    {
        int count = Mathf.Min(segmentCount, entries.Count);
        if (count == 0) return;

        float segmentAngle = (360f - gapDegrees * count) / count;

        for (int i = 0; i < count; i++)
        {
            float start = startAngleOffset + i * (segmentAngle + gapDegrees);
            float end = start + segmentAngle;
            CreateSingleWedge(i, start, end, entries[i]);
        }
    }

    private GameObject CreateSingleWedge(int index, float startDeg, float endDeg, RadialMenuEntry entry)
    {
        GameObject go = new GameObject($"Wedge_{index}_{entry.label}");
        go.transform.SetParent(transform, false);

        MeshFilter mf = go.AddComponent<MeshFilter>();
        MeshRenderer mr = go.AddComponent<MeshRenderer>();

        Mesh mesh = CreateExtrudedWedgeMesh(innerRadius, outerRadius, thickness, startDeg, endDeg, arcSegments);
        mf.sharedMesh = mesh;

        Material faceMat = new Material(ResolveFaceMaterial(wedgeMaterial));
        ApplyTint(faceMat, wedgeTint);
        ConfigureFaceRimUv(faceMat, 0f);
        ConfigureWedgeFaceRimGeometry(faceMat, startDeg, endDeg);
        Material sideMat = new Material(ResolveMaterial(edgeMaterial, wedgeMaterial));
        ApplyTint(sideMat, edgeTint);
        mr.sharedMaterials = new Material[] { faceMat, sideMat };

        Mesh wedgeFrontOnly = CreateWedgeFrontFaceMesh(innerRadius, outerRadius, thickness, startDeg, endDeg, arcSegments);
        TryAddRimOverlayChild(go, faceMat, wedgeFrontOnly);

        bool wantsLabelTab = !string.IsNullOrEmpty(entry.label);

        AddNonConvexMeshCollider(go, mesh);
        TryAddWedgeFrontDepthCollider(go, startDeg, endDeg);

        PressableButton btn = go.AddComponent<PressableButton>();
        btn.OnClicked.AddListener(() => entry.onClick?.Invoke());
        DisableStateVisualizer(go);

        go.AddComponent<RadialWedgeHighlight>();

        if (wantsLabelTab)
            CreateWedgeLabelExtensionSibling(go, index, entry, mesh, wedgeFrontOnly, startDeg, endDeg);

        CreateIcon(go.transform, startDeg, endDeg, entry, omitFloatingLabel: wantsLabelTab);
        return go;
    }

    private void CreateWedgeLabelExtensionSibling(
        GameObject interactiveWedge,
        int index,
        RadialMenuEntry entry,
        Mesh sharedWedgeMesh,
        Mesh wedgeFrontOnly,
        float startDeg,
        float endDeg)
    {
        GameObject extRoot = new GameObject($"Wedge_{index}_LabelExtension");
        extRoot.transform.SetParent(transform, false);

        GameObject visualHub = new GameObject("Visual");
        visualHub.transform.SetParent(extRoot.transform, false);
        visualHub.transform.localPosition = new Vector3(0f, 0f, labelExtensionVisualZBias);
        visualHub.transform.localRotation = Quaternion.identity;
        visualHub.transform.localScale = Vector3.one;

        MeshFilter mfExt = visualHub.AddComponent<MeshFilter>();
        mfExt.sharedMesh = sharedWedgeMesh;

        MeshRenderer mrExt = visualHub.AddComponent<MeshRenderer>();
        Material faceMatExt = new Material(ResolveFaceMaterial(wedgeMaterial));
        ApplyTint(faceMatExt, wedgeTint);
        ConfigureFaceRimUv(faceMatExt, 0f);
        ConfigureWedgeFaceRimGeometry(faceMatExt, startDeg, endDeg);
        Material sideMatExt = new Material(ResolveMaterial(edgeMaterial, wedgeMaterial));
        ApplyTint(sideMatExt, edgeTint);
        mrExt.sharedMaterials = new Material[] { faceMatExt, sideMatExt };
        mrExt.shadowCastingMode = ShadowCastingMode.Off;
        mrExt.receiveShadows = false;

        TryAddRimOverlayChild(visualHub, faceMatExt, wedgeFrontOnly);

        GameObject labelGO = new GameObject("Label");
        labelGO.transform.SetParent(extRoot.transform, false);
        TextMeshPro lbl = labelGO.AddComponent<TextMeshPro>();
        lbl.text = entry.label;
        lbl.fontSize = labelExtensionFontSize;
        lbl.alignment = TextAlignmentOptions.Center;
        lbl.color = Color.white;
        lbl.enableWordWrapping = false;
        lbl.overflowMode = TextOverflowModes.Overflow;
        lbl.raycastTarget = false;
        if (iconFont != null) lbl.font = iconFont;
        labelGO.GetComponent<RectTransform>().sizeDelta = new Vector2(1.2f, 0.12f);

        var labelExt = interactiveWedge.AddComponent<RadialWedgeLabelExtension>();
        labelExt.Initialize(
            extRoot.transform,
            visualHub.transform,
            lbl,
            outerRadius,
            thickness,
            startDeg,
            endDeg,
            labelExtensionInvertArcText,
            labelExtensionAngleMarginDegrees,
            labelExtensionMaxScale,
            labelExtensionTweenDuration,
            labelExtensionRadialT,
            labelExtensionRadialRevealPop,
            iconFont);
    }

    // ── Icons ──────────────────────────────────────────────

    private void CreateIcon(Transform parent, float startDeg, float endDeg, RadialMenuEntry entry, bool omitFloatingLabel = false)
    {
        float midAngle = (startDeg + endDeg) / 2f * Mathf.Deg2Rad;
        float midRadius = (innerRadius + outerRadius) / 2f;
        float halfThick = thickness / 2f;
        Vector3 iconPos = new Vector3(
            Mathf.Cos(midAngle) * midRadius,
            Mathf.Sin(midAngle) * midRadius,
            -(halfThick + 0.0005f)
        );

        if (entry.iconSprite != null)
        {
            GameObject spriteGO = new GameObject("Icon_Sprite");
            spriteGO.transform.SetParent(parent, false);
            spriteGO.transform.localPosition = iconPos;
            SpriteRenderer sr = spriteGO.AddComponent<SpriteRenderer>();
            sr.sprite = entry.iconSprite;
            spriteGO.transform.localScale = Vector3.one * (outerRadius - innerRadius) * iconSpriteScale;
        }
        else if (!string.IsNullOrEmpty(entry.iconUnicode))
        {
            GameObject textGO = new GameObject("Icon_Text");
            textGO.transform.SetParent(parent, false);
            textGO.transform.localPosition = iconPos;

            TextMeshPro tmp = textGO.AddComponent<TextMeshPro>();
            tmp.text = entry.iconUnicode;
            tmp.fontSize = iconSize;
            tmp.alignment = TextAlignmentOptions.Center;
            tmp.color = Color.white;
            tmp.enableWordWrapping = false;
            tmp.overflowMode = TextOverflowModes.Overflow;
            tmp.raycastTarget = false;
            if (iconFont != null) tmp.font = iconFont;

            RectTransform rt = textGO.GetComponent<RectTransform>();
            rt.sizeDelta = new Vector2(0.03f, 0.03f);
        }

        if (!omitFloatingLabel && !string.IsNullOrEmpty(entry.label))
        {
            GameObject labelGO = new GameObject("Label");
            labelGO.transform.SetParent(parent, false);
            float a = (startDeg + endDeg) / 2f * Mathf.Deg2Rad;
            float r = outerRadius + 0.012f;
            labelGO.transform.localPosition = new Vector3(Mathf.Cos(a) * r, Mathf.Sin(a) * r, -(halfThick + 0.0005f));
            labelGO.SetActive(false);

            TextMeshPro lbl = labelGO.AddComponent<TextMeshPro>();
            lbl.text = entry.label;
            lbl.fontSize = 0.3f;
            lbl.alignment = TextAlignmentOptions.Center;
            lbl.color = Color.white;
            lbl.enableWordWrapping = false;
            lbl.raycastTarget = false;
            labelGO.GetComponent<RectTransform>().sizeDelta = new Vector2(0.05f, 0.015f);
        }
    }

    // ── Mesh Generation ────────────────────────────────────
    //
    // Submesh 0 = front + back faces  (wedgeMaterial)
    // Submesh 1 = side edges          (edgeMaterial)

    public static Mesh CreateExtrudedWedgeMesh(float innerR, float outerR, float depth, float startDeg, float endDeg, int segments)
    {
        Mesh mesh = new Mesh();
        mesh.name = $"Wedge_{startDeg:F0}_{endDeg:F0}";
        float halfD = depth / 2f;

        // ── Vertices ───────────────────────────────────────
        // Front face: (segments+1)*2 verts
        // Back  face: (segments+1)*2 verts
        // Side edges: inner arc, outer arc, left edge, right edge
        //   Inner arc: (segments+1)*2 verts (front+back rim)
        //   Outer arc: (segments+1)*2 verts
        //   Left  edge: 4 verts (inner-front, inner-back, outer-front, outer-back)
        //   Right edge: 4 verts

        int arcVerts = (segments + 1) * 2;
        int faceVertCount = arcVerts; // per face
        int sideInner = (segments + 1) * 2;
        int sideOuter = (segments + 1) * 2;
        int sideLeft = 4;
        int sideRight = 4;

        int totalVerts = faceVertCount * 2 + sideInner + sideOuter + sideLeft + sideRight;
        Vector3[] verts = new Vector3[totalVerts];
        Vector2[] uvs = new Vector2[totalVerts];
        Vector3[] normals = new Vector3[totalVerts];

        int vi = 0;

        // ── Front face verts (facing -Z) ───────────────────
        int frontStart = vi;
        for (int i = 0; i <= segments; i++)
        {
            float t = (float)i / segments;
            float angle = Mathf.Lerp(startDeg, endDeg, t) * Mathf.Deg2Rad;
            float cos = Mathf.Cos(angle), sin = Mathf.Sin(angle);

            verts[vi]   = new Vector3(cos * innerR, sin * innerR, -halfD);
            uvs[vi]     = new Vector2(t, 0f);
            normals[vi] = Vector3.back;
            vi++;
            verts[vi]   = new Vector3(cos * outerR, sin * outerR, -halfD);
            uvs[vi]     = new Vector2(t, 1f);
            normals[vi] = Vector3.back;
            vi++;
        }

        // ── Back face verts (facing +Z) ────────────────────
        int backStart = vi;
        for (int i = 0; i <= segments; i++)
        {
            float t = (float)i / segments;
            float angle = Mathf.Lerp(startDeg, endDeg, t) * Mathf.Deg2Rad;
            float cos = Mathf.Cos(angle), sin = Mathf.Sin(angle);

            verts[vi]   = new Vector3(cos * innerR, sin * innerR, halfD);
            uvs[vi]     = new Vector2(t, 0f);
            normals[vi] = Vector3.forward;
            vi++;
            verts[vi]   = new Vector3(cos * outerR, sin * outerR, halfD);
            uvs[vi]     = new Vector2(t, 1f);
            normals[vi] = Vector3.forward;
            vi++;
        }

        // ── Inner arc side verts ───────────────────────────
        int innerSideStart = vi;
        for (int i = 0; i <= segments; i++)
        {
            float t = (float)i / segments;
            float angle = Mathf.Lerp(startDeg, endDeg, t) * Mathf.Deg2Rad;
            float cos = Mathf.Cos(angle), sin = Mathf.Sin(angle);
            Vector3 norm = new Vector3(-cos, -sin, 0f).normalized;

            verts[vi]   = new Vector3(cos * innerR, sin * innerR, -halfD);
            uvs[vi]     = new Vector2(t, 0f);
            normals[vi] = norm;
            vi++;
            verts[vi]   = new Vector3(cos * innerR, sin * innerR, halfD);
            uvs[vi]     = new Vector2(t, 1f);
            normals[vi] = norm;
            vi++;
        }

        // ── Outer arc side verts ───────────────────────────
        int outerSideStart = vi;
        for (int i = 0; i <= segments; i++)
        {
            float t = (float)i / segments;
            float angle = Mathf.Lerp(startDeg, endDeg, t) * Mathf.Deg2Rad;
            float cos = Mathf.Cos(angle), sin = Mathf.Sin(angle);
            Vector3 norm = new Vector3(cos, sin, 0f).normalized;

            verts[vi]   = new Vector3(cos * outerR, sin * outerR, -halfD);
            uvs[vi]     = new Vector2(t, 0f);
            normals[vi] = norm;
            vi++;
            verts[vi]   = new Vector3(cos * outerR, sin * outerR, halfD);
            uvs[vi]     = new Vector2(t, 1f);
            normals[vi] = norm;
            vi++;
        }

        // ── Left straight edge (startAngle side) ──────────
        int leftStart = vi;
        {
            float angle = startDeg * Mathf.Deg2Rad;
            float cos = Mathf.Cos(angle), sin = Mathf.Sin(angle);
            Vector3 norm = new Vector3(-sin, cos, 0f).normalized;

            verts[vi] = new Vector3(cos * innerR, sin * innerR, -halfD); uvs[vi] = new Vector2(0, 0); normals[vi] = norm; vi++;
            verts[vi] = new Vector3(cos * innerR, sin * innerR,  halfD); uvs[vi] = new Vector2(0, 1); normals[vi] = norm; vi++;
            verts[vi] = new Vector3(cos * outerR, sin * outerR, -halfD); uvs[vi] = new Vector2(1, 0); normals[vi] = norm; vi++;
            verts[vi] = new Vector3(cos * outerR, sin * outerR,  halfD); uvs[vi] = new Vector2(1, 1); normals[vi] = norm; vi++;
        }

        // ── Right straight edge (endAngle side) ───────────
        int rightStart = vi;
        {
            float angle = endDeg * Mathf.Deg2Rad;
            float cos = Mathf.Cos(angle), sin = Mathf.Sin(angle);
            Vector3 norm = new Vector3(sin, -cos, 0f).normalized;

            verts[vi] = new Vector3(cos * innerR, sin * innerR, -halfD); uvs[vi] = new Vector2(0, 0); normals[vi] = norm; vi++;
            verts[vi] = new Vector3(cos * innerR, sin * innerR,  halfD); uvs[vi] = new Vector2(0, 1); normals[vi] = norm; vi++;
            verts[vi] = new Vector3(cos * outerR, sin * outerR, -halfD); uvs[vi] = new Vector2(1, 0); normals[vi] = norm; vi++;
            verts[vi] = new Vector3(cos * outerR, sin * outerR,  halfD); uvs[vi] = new Vector2(1, 1); normals[vi] = norm; vi++;
        }

        // ── Triangles ──────────────────────────────────────

        // Submesh 0: front + back faces
        List<int> faceTris = new List<int>();

        for (int i = 0; i < segments; i++)
        {
            int fv = frontStart + i * 2;
            faceTris.Add(fv);     faceTris.Add(fv + 2); faceTris.Add(fv + 1);
            faceTris.Add(fv + 1); faceTris.Add(fv + 2); faceTris.Add(fv + 3);
        }
        for (int i = 0; i < segments; i++)
        {
            int bv = backStart + i * 2;
            faceTris.Add(bv);     faceTris.Add(bv + 1); faceTris.Add(bv + 2);
            faceTris.Add(bv + 1); faceTris.Add(bv + 3); faceTris.Add(bv + 2);
        }

        // Submesh 1: all side edges
        List<int> sideTris = new List<int>();

        // Inner arc sides (faces inward, so reversed winding)
        for (int i = 0; i < segments; i++)
        {
            int sv = innerSideStart + i * 2;
            sideTris.Add(sv);     sideTris.Add(sv + 1); sideTris.Add(sv + 2);
            sideTris.Add(sv + 1); sideTris.Add(sv + 3); sideTris.Add(sv + 2);
        }
        // Outer arc sides
        for (int i = 0; i < segments; i++)
        {
            int sv = outerSideStart + i * 2;
            sideTris.Add(sv);     sideTris.Add(sv + 2); sideTris.Add(sv + 1);
            sideTris.Add(sv + 1); sideTris.Add(sv + 2); sideTris.Add(sv + 3);
        }
        // Left edge
        sideTris.Add(leftStart);     sideTris.Add(leftStart + 1); sideTris.Add(leftStart + 2);
        sideTris.Add(leftStart + 1); sideTris.Add(leftStart + 3); sideTris.Add(leftStart + 2);
        // Right edge
        sideTris.Add(rightStart);     sideTris.Add(rightStart + 2); sideTris.Add(rightStart + 1);
        sideTris.Add(rightStart + 1); sideTris.Add(rightStart + 2); sideTris.Add(rightStart + 3);

        mesh.vertices = verts;
        mesh.uv = uvs;
        mesh.normals = normals;
        mesh.subMeshCount = 2;
        mesh.SetTriangles(faceTris, 0);
        mesh.SetTriangles(sideTris, 1);
        mesh.RecalculateBounds();
        return mesh;
    }

    /// <summary>Front-facing annular sector only (same UVs as full wedge), for transparent rim overlay.</summary>
    public static Mesh CreateWedgeFrontFaceMesh(float innerR, float outerR, float depth, float startDeg, float endDeg, int segments)
    {
        Mesh mesh = new Mesh();
        mesh.name = "WedgeFrontFace";
        float halfD = depth / 2f;
        int vertCount = (segments + 1) * 2;
        Vector3[] verts = new Vector3[vertCount];
        Vector2[] uvs = new Vector2[vertCount];
        Vector3[] normals = new Vector3[vertCount];
        int vi = 0;
        for (int i = 0; i <= segments; i++)
        {
            float t = (float)i / segments;
            float angle = Mathf.Lerp(startDeg, endDeg, t) * Mathf.Deg2Rad;
            float cos = Mathf.Cos(angle), sin = Mathf.Sin(angle);

            verts[vi] = new Vector3(cos * innerR, sin * innerR, -halfD);
            uvs[vi] = new Vector2(t, 0f);
            normals[vi] = Vector3.back;
            vi++;
            verts[vi] = new Vector3(cos * outerR, sin * outerR, -halfD);
            uvs[vi] = new Vector2(t, 1f);
            normals[vi] = Vector3.back;
            vi++;
        }

        List<int> tris = new List<int>(segments * 6);
        for (int i = 0; i < segments; i++)
        {
            int fv = i * 2;
            tris.Add(fv); tris.Add(fv + 2); tris.Add(fv + 1);
            tris.Add(fv + 1); tris.Add(fv + 2); tris.Add(fv + 3);
        }

        mesh.vertices = verts;
        mesh.uv = uvs;
        mesh.normals = normals;
        mesh.triangles = tris.ToArray();
        mesh.RecalculateBounds();
        return mesh;
    }

    public static Mesh CreateExtrudedDiscMesh(float radius, float depth, int segments)
    {
        Mesh mesh = new Mesh();
        mesh.name = "CenterDisc";
        float halfD = depth / 2f;

        // Front center + ring, back center + ring, side ring*2
        int totalVerts = (segments + 1) * 2 + segments * 2 * 2;
        // Slight overallocation is fine
        Vector3[] verts = new Vector3[(segments + 1) * 6];
        Vector2[] uvs = new Vector2[verts.Length];
        Vector3[] normals = new Vector3[verts.Length];

        int vi = 0;

        // Front face
        int frontCenter = vi;
        verts[vi] = new Vector3(0, 0, -halfD); uvs[vi] = new Vector2(0.5f, 0.5f); normals[vi] = Vector3.back; vi++;
        int frontRingStart = vi;
        for (int i = 0; i < segments; i++)
        {
            float angle = (float)i / segments * Mathf.PI * 2f;
            float cos = Mathf.Cos(angle), sin = Mathf.Sin(angle);
            verts[vi] = new Vector3(cos * radius, sin * radius, -halfD);
            uvs[vi] = new Vector2(cos * 0.5f + 0.5f, sin * 0.5f + 0.5f);
            normals[vi] = Vector3.back;
            vi++;
        }

        // Back face
        int backCenter = vi;
        verts[vi] = new Vector3(0, 0, halfD); uvs[vi] = new Vector2(0.5f, 0.5f); normals[vi] = Vector3.forward; vi++;
        int backRingStart = vi;
        for (int i = 0; i < segments; i++)
        {
            float angle = (float)i / segments * Mathf.PI * 2f;
            float cos = Mathf.Cos(angle), sin = Mathf.Sin(angle);
            verts[vi] = new Vector3(cos * radius, sin * radius, halfD);
            uvs[vi] = new Vector2(cos * 0.5f + 0.5f, sin * 0.5f + 0.5f);
            normals[vi] = Vector3.forward;
            vi++;
        }

        // Side rim
        int sideStart = vi;
        for (int i = 0; i < segments; i++)
        {
            float angle = (float)i / segments * Mathf.PI * 2f;
            float cos = Mathf.Cos(angle), sin = Mathf.Sin(angle);
            Vector3 norm = new Vector3(cos, sin, 0f);
            float t = (float)i / segments;

            verts[vi] = new Vector3(cos * radius, sin * radius, -halfD);
            uvs[vi] = new Vector2(t, 0f); normals[vi] = norm; vi++;
            verts[vi] = new Vector3(cos * radius, sin * radius, halfD);
            uvs[vi] = new Vector2(t, 1f); normals[vi] = norm; vi++;
        }

        // Trim arrays to actual count
        System.Array.Resize(ref verts, vi);
        System.Array.Resize(ref uvs, vi);
        System.Array.Resize(ref normals, vi);

        // Submesh 0: front + back face tris
        List<int> faceTris = new List<int>();
        for (int i = 0; i < segments; i++)
        {
            int next = (i + 1) % segments;
            faceTris.Add(frontCenter); faceTris.Add(frontRingStart + i); faceTris.Add(frontRingStart + next);
            faceTris.Add(backCenter);  faceTris.Add(backRingStart + next); faceTris.Add(backRingStart + i);
        }

        // Submesh 1: side rim tris
        List<int> sideTris = new List<int>();
        for (int i = 0; i < segments; i++)
        {
            int cur = sideStart + i * 2;
            int nxt = sideStart + ((i + 1) % segments) * 2;
            sideTris.Add(cur);     sideTris.Add(cur + 1); sideTris.Add(nxt);
            sideTris.Add(nxt);     sideTris.Add(cur + 1); sideTris.Add(nxt + 1);
        }

        mesh.vertices = verts;
        mesh.uv = uvs;
        mesh.normals = normals;
        mesh.subMeshCount = 2;
        mesh.SetTriangles(faceTris, 0);
        mesh.SetTriangles(sideTris, 1);
        mesh.RecalculateBounds();
        return mesh;
    }

    /// <summary>Front disc face only (center + ring at -Z), for transparent rim overlay.</summary>
    public static Mesh CreateDiscFrontFaceMesh(float radius, float depth, int segments)
    {
        Mesh mesh = new Mesh();
        mesh.name = "DiscFrontFace";
        float halfD = depth / 2f;
        Vector3[] verts = new Vector3[1 + segments];
        Vector2[] uvs = new Vector2[verts.Length];
        Vector3[] normals = new Vector3[verts.Length];
        int vi = 0;
        verts[vi] = new Vector3(0f, 0f, -halfD);
        uvs[vi] = new Vector2(0.5f, 0.5f);
        normals[vi] = Vector3.back;
        vi++;
        int ringStart = vi;
        for (int i = 0; i < segments; i++)
        {
            float angle = (float)i / segments * Mathf.PI * 2f;
            float cos = Mathf.Cos(angle), sin = Mathf.Sin(angle);
            verts[vi] = new Vector3(cos * radius, sin * radius, -halfD);
            uvs[vi] = new Vector2(cos * 0.5f + 0.5f, sin * 0.5f + 0.5f);
            normals[vi] = Vector3.back;
            vi++;
        }

        List<int> tris = new List<int>(segments * 3);
        for (int i = 0; i < segments; i++)
        {
            int next = (i + 1) % segments;
            tris.Add(0);
            tris.Add(ringStart + i);
            tris.Add(ringStart + next);
        }

        mesh.vertices = verts;
        mesh.uv = uvs;
        mesh.normals = normals;
        mesh.triangles = tris.ToArray();
        mesh.RecalculateBounds();
        return mesh;
    }
}
