using System.Collections;
using TMPro;
using UnityEngine;
using MixedReality.Toolkit.UX;

/// <summary>
/// Gaze-revealed duplicate wedge scale + label on a sibling "extension" root (see <see cref="RadialMenuBuilder"/>).
/// Bends TMP glyph vertices along the wedge arc so the string stays inside the extended wedge.
/// </summary>
[RequireComponent(typeof(PressableButton))]
public class RadialWedgeLabelExtension : MonoBehaviour
{
    private Transform extensionRoot;
    private Transform visualScaleHub;
    private TextMeshPro label;
    private MeshRenderer[] extensionRenderers;
    private PressableButton button;

    private float outerRadius;
    private float halfThickness;
    private float startAngleRad;
    private float endAngleRad;
    private float arcMarginRad;
    private bool invertArc;
    private float maxScale = 1.1f;
    private float tweenDuration = 0.2f;
    private float labelRadialT = 0.52f;
    private float radialRevealPop;
    private Color labelBaseColor = Color.white;

    private Coroutine tweenRoutine;
    private float displayT;
    private bool isPinned;

    public void Initialize(
        Transform extensionRootTransform,
        Transform visualScaleHubTransform,
        TextMeshPro labelTmp,
        float outerRadiusWorld,
        float plateThickness,
        float startAngleDegrees,
        float endAngleDegrees,
        bool invertArcText,
        float angleMarginDegrees,
        float extensionMaxScale,
        float durationSeconds,
        float labelRadiusLerp01,
        float radialPopMeters,
        TMP_FontAsset font)
    {
        extensionRoot = extensionRootTransform;
        visualScaleHub = visualScaleHubTransform;
        label = labelTmp;
        outerRadius = outerRadiusWorld;
        halfThickness = plateThickness * 0.5f;
        startAngleRad = startAngleDegrees * Mathf.Deg2Rad;
        endAngleRad = endAngleDegrees * Mathf.Deg2Rad;
        invertArc = invertArcText;
        arcMarginRad = Mathf.Max(0f, angleMarginDegrees) * Mathf.Deg2Rad;
        maxScale = Mathf.Max(1.001f, extensionMaxScale);
        tweenDuration = Mathf.Max(0.01f, durationSeconds);
        labelRadialT = Mathf.Clamp01(labelRadiusLerp01);
        radialRevealPop = radialPopMeters;
        if (label != null)
        {
            labelBaseColor = label.color;
            label.color = new Color(labelBaseColor.r, labelBaseColor.g, labelBaseColor.b, 0f);
            if (font != null) label.font = font;
            var lr = label.GetComponent<MeshRenderer>();
            if (lr != null)
                lr.sortingOrder = 15;
        }

        extensionRenderers = visualScaleHub != null
            ? visualScaleHub.GetComponentsInChildren<MeshRenderer>(true)
            : System.Array.Empty<MeshRenderer>();

        foreach (var r in extensionRenderers)
        {
            if (r != null)
                r.sortingOrder = 12;
        }

        SetRenderersEnabled(false);
        if (visualScaleHub != null)
            visualScaleHub.localScale = Vector3.one;
        ApplyLabelTransform(1f, 0f);
    }

    void Start()
    {
        button = GetComponent<PressableButton>();
        if (button != null && button.IsGazeHovered != null)
        {
            button.IsGazeHovered.OnEntered.AddListener(_ => OnGazeEnter());
            button.IsGazeHovered.OnExited.AddListener(_ => OnGazeExit());
        }
    }

    void OnDestroy()
    {
        if (tweenRoutine != null)
            StopCoroutine(tweenRoutine);
    }

    private void OnGazeEnter()
    {
        BeginDisplayTween(1f);
    }

    private void OnGazeExit()
    {
        if (isPinned)
            return;
        BeginDisplayTween(0f);
    }

    public void SetPinned(bool pinned)
    {
        isPinned = pinned;
        BeginDisplayTween(isPinned ? 1f : 0f);
    }

    public string GetLabelText()
    {
        return label != null ? label.text : string.Empty;
    }

    public void SetPinnedLabelImmediate(string text)
    {
        if (label != null)
            label.text = text;

        isPinned = true;
        if (tweenRoutine != null)
        {
            StopCoroutine(tweenRoutine);
            tweenRoutine = null;
        }

        displayT = 1f;
        SetRenderersEnabled(true);
        ApplyFrame(displayT);
    }

    public void SetLabelImmediate(string text)
    {
        if (label == null)
            return;

        label.text = text;
        ApplyFrame(displayT);
    }

    /// <summary>
    /// Hover exit can fire while this object is being disabled (e.g. menu teardown); coroutines cannot start on inactive objects.
    /// </summary>
    private void BeginDisplayTween(float targetT)
    {
        if (extensionRoot == null || visualScaleHub == null) return;
        if (tweenRoutine != null)
        {
            StopCoroutine(tweenRoutine);
            tweenRoutine = null;
        }

        if (!isActiveAndEnabled || !gameObject.activeInHierarchy)
        {
            displayT = targetT;
            ApplyFrame(displayT);
            if (targetT < 0.5f)
                SetRenderersEnabled(false);
            return;
        }

        tweenRoutine = StartCoroutine(TweenDisplay(targetT));
    }

    private IEnumerator TweenDisplay(float targetT)
    {
        float startT = displayT;
        float elapsed = 0f;
        if (targetT > 0.5f)
            SetRenderersEnabled(true);

        while (elapsed < tweenDuration)
        {
            elapsed += Time.unscaledDeltaTime;
            float u = Mathf.Clamp01(elapsed / tweenDuration);
            u = u * u * (3f - 2f * u);
            displayT = Mathf.Lerp(startT, targetT, u);
            ApplyFrame(displayT);
            yield return null;
        }

        displayT = targetT;
        ApplyFrame(displayT);
        if (targetT < 0.5f)
            SetRenderersEnabled(false);
        tweenRoutine = null;
    }

    private void ApplyFrame(float t)
    {
        float s = Mathf.Lerp(1f, maxScale, t);
        if (visualScaleHub != null)
            visualScaleHub.localScale = Vector3.one * s;
        ApplyLabelTransform(s, t);
    }

    private void ApplyLabelTransform(float currentScale, float alphaT)
    {
        if (label == null) return;
        float rOuter = outerRadius * currentScale;
        float r = Mathf.Lerp(outerRadius, rOuter, labelRadialT) + radialRevealPop * alphaT;
        float z = -(halfThickness + 0.0005f);
        label.transform.localPosition = new Vector3(0f, 0f, z);
        label.transform.localRotation = Quaternion.identity;
        var c = labelBaseColor;
        label.color = new Color(c.r, c.g, c.b, c.a * alphaT);

        if (alphaT > 0.001f)
            BendLabelAlongArc(r, z);
        else
            label.ForceMeshUpdate(true);
    }

    private void BendLabelAlongArc(float radialDistance, float zPlane)
    {
        label.ForceMeshUpdate(true);
        TMP_TextInfo info = label.textInfo;
        if (info == null || info.characterCount == 0)
            return;

        float minCx = float.MaxValue;
        float maxCx = float.MinValue;
        for (int i = 0; i < info.characterCount; i++)
        {
            ref TMP_CharacterInfo ci = ref info.characterInfo[i];
            if (!ci.isVisible)
                continue;
            Vector3 bl = ci.bottomLeft;
            Vector3 tl = ci.topLeft;
            Vector3 tr = ci.topRight;
            Vector3 br = ci.bottomRight;
            float cx = (bl.x + tl.x + tr.x + br.x) * 0.25f;
            if (cx < minCx) minCx = cx;
            if (cx > maxCx) maxCx = cx;
        }

        if (minCx > maxCx)
            return;

        float spanCx = maxCx - minCx;
        float wedgeStart = startAngleRad + arcMarginRad;
        float wedgeEnd = endAngleRad - arcMarginRad;
        if (wedgeEnd <= wedgeStart)
        {
            wedgeStart = startAngleRad;
            wedgeEnd = endAngleRad;
        }

        float wedgeSpan = wedgeEnd - wedgeStart;
        float midAngle = (wedgeStart + wedgeEnd) * 0.5f;
        const float hemisphereEpsilon = 1e-3f;
        bool upperHalf = Mathf.Sin(midAngle) > hemisphereEpsilon;
        bool reverseAlongArc = invertArc ^ upperHalf;

        float rSafe = Mathf.Max(1e-5f, radialDistance);
        float wordSpanRad = spanCx / rSafe;
        wordSpanRad = Mathf.Min(wordSpanRad, wedgeSpan);
        float halfWordSpan = wordSpanRad * 0.5f;

        for (int i = 0; i < info.characterCount; i++)
        {
            ref TMP_CharacterInfo ci = ref info.characterInfo[i];
            if (!ci.isVisible)
                continue;

            int matIndex = ci.materialReferenceIndex;
            int vertIndex = ci.vertexIndex;
            Vector3[] verts = info.meshInfo[matIndex].vertices;

            Vector3 bl = verts[vertIndex + 0];
            Vector3 tl = verts[vertIndex + 1];
            Vector3 tr = verts[vertIndex + 2];
            Vector3 br = verts[vertIndex + 3];
            Vector3 center = (bl + tl + tr + br) * 0.25f;

            float cx = (bl.x + tl.x + tr.x + br.x) * 0.25f;
            float u = spanCx > 1e-6f ? Mathf.InverseLerp(minCx, maxCx, cx) : 0.5f;
            float uTheta = reverseAlongArc ? (1f - u) : u;
            float theta = Mathf.Lerp(midAngle - halfWordSpan, midAngle + halfWordSpan, uTheta);
            Vector3 intrinsicTangent = new Vector3(-Mathf.Sin(theta), Mathf.Cos(theta), 0f);
            Vector3 radial = new Vector3(Mathf.Cos(theta), Mathf.Sin(theta), 0f);
            Vector3 tangentAlong = reverseAlongArc ? -intrinsicTangent : intrinsicTangent;
            Vector3 inwardAlong = reverseAlongArc ? radial : -radial;
            Vector3 arcBase = new Vector3(Mathf.Cos(theta) * radialDistance, Mathf.Sin(theta) * radialDistance, zPlane);

            for (int j = 0; j < 4; j++)
            {
                Vector3 v = verts[vertIndex + j];
                Vector3 delta = v - center;
                verts[vertIndex + j] = arcBase + delta.x * tangentAlong + delta.y * inwardAlong;
            }
        }

        label.UpdateVertexData(TMP_VertexDataUpdateFlags.Vertices);
    }

    private void SetRenderersEnabled(bool on)
    {
        if (extensionRenderers == null) return;
        foreach (var r in extensionRenderers)
        {
            if (r != null)
                r.enabled = on;
        }
    }
}
