using UnityEngine;

public class PathArrowAnimation : MonoBehaviour
{
    [SerializeField] private float scrollSpeed = 0.5f;
    
    private Material arrowMaterial;
    private float offset;

    void Start()
    {
        // Get the material from the Line Renderer
        var lineRenderer = GetComponent<LineRenderer>();
        arrowMaterial = lineRenderer.material;
    }

    void Update()
    {
        offset -= scrollSpeed * Time.deltaTime;
        arrowMaterial.mainTextureOffset = new Vector2(offset, 0f);
    }
}