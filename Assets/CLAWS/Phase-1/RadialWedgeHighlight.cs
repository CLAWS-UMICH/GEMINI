using UnityEngine;
using MixedReality.Toolkit.UX;

/// <summary>
/// MRTK-style visual feedback for radial menu wedges and center disc:
/// white rim highlight on eye gaze when the face material supports <see cref="RimHighlightId"/> (CLAWS/RadialWedgeFace).
/// Custom materials without that property keep the previous full-surface tint behavior.
/// </summary>
[RequireComponent(typeof(PressableButton))]
[RequireComponent(typeof(MeshRenderer))]
public class RadialWedgeHighlight : MonoBehaviour
{
    [Header("Highlight colors")]
    [Tooltip("Rim color with CLAWS/RadialWedgeFace; full-face tint when using a custom material without _RimHighlight.")]
    [SerializeField] private Color gazeHighlightColor = Color.white;

    private PressableButton button;
    private MeshRenderer meshRenderer;
    private Material[] materialInstances;
    private Color[] originalFaceColors;
    private Color[] originalEdgeColors;
    private bool isGazeHovered;
    private bool usesRimHighlight;

    private static readonly int BaseColorId = Shader.PropertyToID("_Base_Color_");
    private static readonly int ColorId = Shader.PropertyToID("_Color");
    private static readonly int BaseColorUrpId = Shader.PropertyToID("_BaseColor");
    private static readonly int RimHighlightId = Shader.PropertyToID("_RimHighlight");
    private static readonly int RimColorId = Shader.PropertyToID("_RimColor");

    void Start()
    {
        button = GetComponent<PressableButton>();
        meshRenderer = GetComponent<MeshRenderer>();
        if (button == null || meshRenderer == null) return;

        DisableStateVisualizerOn(gameObject);

        Material[] mats = meshRenderer.materials;
        materialInstances = mats;
        originalFaceColors = new Color[] { GetMaterialColor(mats[0]) };
        originalEdgeColors = mats.Length > 1
            ? new Color[] { GetMaterialColor(mats[1]) }
            : new Color[] { originalFaceColors[0] };

        usesRimHighlight = mats[0] != null && mats[0].HasProperty(RimHighlightId);
        if (usesRimHighlight && mats[0].HasProperty(RimColorId))
            mats[0].SetColor(RimColorId, gazeHighlightColor);

        if (button.IsGazeHovered != null)
        {
            button.IsGazeHovered.OnEntered.AddListener(_ => OnGazeEnter());
            button.IsGazeHovered.OnExited.AddListener(_ => OnGazeExit());
        }
    }

    private Color GetMaterialColor(Material m)
    {
        if (m == null) return Color.white;
        if (m.HasProperty(BaseColorId)) return m.GetColor(BaseColorId);
        if (m.HasProperty(BaseColorUrpId)) return m.GetColor(BaseColorUrpId);
        if (m.HasProperty(ColorId)) return m.GetColor(ColorId);
        return Color.white;
    }

    private void OnGazeEnter()
    {
        isGazeHovered = true;
        ApplyHighlight();
    }

    private void OnGazeExit()
    {
        isGazeHovered = false;
        ApplyHighlight();
    }

    private void ApplyHighlight()
    {
        if (materialInstances == null || materialInstances.Length == 0) return;

        if (usesRimHighlight)
        {
            materialInstances[0].SetFloat(RimHighlightId, isGazeHovered ? 1f : 0f);
            return;
        }

        Color faceColor = isGazeHovered ? gazeHighlightColor : originalFaceColors[0];
        Color edgeColor = isGazeHovered
            ? Color.Lerp(originalEdgeColors[0], gazeHighlightColor, 0.7f)
            : (originalEdgeColors.Length > 0 ? originalEdgeColors[0] : originalFaceColors[0]);

        SetColor(materialInstances[0], faceColor);
        if (materialInstances.Length > 1)
            SetColor(materialInstances[1], edgeColor);
    }

    private void SetColor(Material mat, Color color)
    {
        if (mat == null) return;
        if (mat.HasProperty(BaseColorId)) mat.SetColor(BaseColorId, color);
        if (mat.HasProperty(BaseColorUrpId)) mat.SetColor(BaseColorUrpId, color);
        if (mat.HasProperty(ColorId)) mat.SetColor(ColorId, color);
    }

    private static void DisableStateVisualizerOn(GameObject target)
    {
        if (target == null) return;
        foreach (var c in target.GetComponents<MonoBehaviour>())
        {
            if (c != null && c.GetType().Name == "StateVisualizer")
            {
                c.enabled = false;
                return;
            }
        }
    }
}
