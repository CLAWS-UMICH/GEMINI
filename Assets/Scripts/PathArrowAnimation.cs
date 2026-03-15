using UnityEngine;

/// <summary>
/// Scrolls the LineRenderer's main texture to create an animated moving-arrow effect along the path.
/// Add this to the same GameObject as the LineRenderer, or assign the Line Renderer in the inspector.
/// </summary>
public class PathArrowAnimation : MonoBehaviour
{
    [SerializeField] private float scrollSpeed = 0.5f;
    [Tooltip("Optional: assign if this script is not on the same GameObject as the LineRenderer (e.g. path from Pathfinding).")]
    [SerializeField] private LineRenderer lineRenderer;

    private Material arrowMaterial;
    private float offset;

    void Start()
    {
        if (lineRenderer == null)
            lineRenderer = GetComponent<LineRenderer>();

        if (lineRenderer == null)
        {
            Debug.LogWarning("PathArrowAnimation: No LineRenderer found.");
            return;
        }

        // Use .material so we animate an instance and don't change the shared asset
        arrowMaterial = lineRenderer.material;
    }

    void Update()
    {
        if (arrowMaterial == null) return;

        offset -= scrollSpeed * Time.deltaTime;
        arrowMaterial.mainTextureOffset = new Vector2(offset, 0f);
    }
}
