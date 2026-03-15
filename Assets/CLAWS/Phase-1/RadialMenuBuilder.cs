using UnityEngine;
using UnityEngine.Events;
using System.Collections;
using System.Collections.Generic;
using TMPro;
using MixedReality.Toolkit.UX;

[System.Serializable]
public class RadialMenuEntry
{
    public string label;
    public string iconUnicode;
    public Sprite iconSprite;
    public UnityEvent onClick;
}

public class RadialMenuBuilder : MonoBehaviour
{
    [Header("Layout")]
    [Range(2, 12)]
    public int segmentCount = 5;

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

    public float centerDiscRadius = 0.035f;

    public Color wedgeTint = new Color(0.15f, 0.2f, 0.55f, 1f);

    [Tooltip("Tint for the side edges — typically lighter than wedgeTint")]
    public Color edgeTint = new Color(0.6f, 0.65f, 0.85f, 1f);

    [Header("Icons")]
    public TMP_FontAsset iconFont;
    public float iconSize = 0.5f;

    [Header("Menu Items")]
    public List<RadialMenuEntry> entries = new List<RadialMenuEntry>();

    [Header("Animation")]
    public float animationDuration = 0.25f;
    public bool startHidden = false;

    private List<GameObject> wedgeObjects = new List<GameObject>();
    private GameObject centerDisc;
    private bool isOpen;
    private Coroutine animCoroutine;

    private static readonly int BaseColorId = Shader.PropertyToID("_Base_Color_");
    private static readonly int ColorId = Shader.PropertyToID("_Color");

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
        animCoroutine = StartCoroutine(AnimateScale(Vector3.zero, Vector3.one));
    }

    public void CloseMenu()
    {
        if (!isOpen) return;
        isOpen = false;
        if (animCoroutine != null) StopCoroutine(animCoroutine);
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
        wedgeObjects.Clear();
        for (int i = transform.childCount - 1; i >= 0; i--)
        {
            if (Application.isPlaying)
                Destroy(transform.GetChild(i).gameObject);
            else
                DestroyImmediate(transform.GetChild(i).gameObject);
        }
        centerDisc = null;
    }

    private void ApplyTint(Material mat, Color tint)
    {
        if (mat.HasProperty(BaseColorId))
            mat.SetColor(BaseColorId, tint);
        if (mat.HasProperty(ColorId))
            mat.SetColor(ColorId, tint);
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

    // ── Center Disc ────────────────────────────────────────

    private void CreateCenterDisc()
    {
        centerDisc = new GameObject("CenterDisc");
        centerDisc.transform.SetParent(transform, false);

        MeshFilter mf = centerDisc.AddComponent<MeshFilter>();
        MeshRenderer mr = centerDisc.AddComponent<MeshRenderer>();

        mf.sharedMesh = CreateExtrudedDiscMesh(centerDiscRadius, thickness, 32);

        Material faceMat = new Material(ResolveMaterial(centerMaterial, wedgeMaterial));
        ApplyTint(faceMat, wedgeTint);
        Material sideMat = new Material(ResolveMaterial(edgeMaterial, wedgeMaterial));
        ApplyTint(sideMat, edgeTint);
        mr.sharedMaterials = new Material[] { faceMat, sideMat };
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
            wedgeObjects.Add(CreateSingleWedge(i, start, end, entries[i]));
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

        Material faceMat = new Material(ResolveMaterial(wedgeMaterial, null));
        ApplyTint(faceMat, wedgeTint);
        Material sideMat = new Material(ResolveMaterial(edgeMaterial, wedgeMaterial));
        ApplyTint(sideMat, edgeTint);
        mr.sharedMaterials = new Material[] { faceMat, sideMat };

        MeshCollider mc = go.AddComponent<MeshCollider>();
        mc.sharedMesh = mesh;

        PressableButton btn = go.AddComponent<PressableButton>();
        btn.OnClicked.AddListener(() => entry.onClick?.Invoke());

        CreateIcon(go.transform, startDeg, endDeg, entry);
        return go;
    }

    // ── Icons ──────────────────────────────────────────────

    private void CreateIcon(Transform parent, float startDeg, float endDeg, RadialMenuEntry entry)
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
            spriteGO.transform.localScale = Vector3.one * (outerRadius - innerRadius) * 0.5f;
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
            if (iconFont != null) tmp.font = iconFont;

            RectTransform rt = textGO.GetComponent<RectTransform>();
            rt.sizeDelta = new Vector2(0.03f, 0.03f);
        }

        if (!string.IsNullOrEmpty(entry.label))
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
}
