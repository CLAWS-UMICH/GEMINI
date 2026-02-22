using UnityEngine;

[ExecuteAlways]
public class WorldVerticalLayoutTopDown : MonoBehaviour
{
    [Header("Stacking")]
    public float spacing = 0.02f;
    public float topPadding = 0.02f;

    [Header("Behavior")]
    public bool useLocalPosition = true;
    public bool includeInactive = false;

    [Header("Child Height")]
    public bool autoDetectHeight = true;
    public float fallbackHeight = 0.1f;

    [Header("Parent Bounds Source (optional)")]
    [Tooltip("If null, uses this GameObject's Renderer. For MRTK backplates, drag the actual backplate mesh here.")]
    public Renderer parentRenderer;

    void OnEnable() => Arrange();
    void OnValidate() => Arrange();
    void Update()
    {
        // If your list changes at runtime (items added/removed), keep this.
        // Otherwise you can delete Update() for efficiency.
        Arrange();
    }

    public void Arrange()
    {
        Renderer pr = parentRenderer != null ? parentRenderer : GetComponentInChildren<Renderer>();
        if (pr == null) return;

        // Parent top edge in world space
        float parentTopYWorld = pr.bounds.max.y;

        // Start placing just under the top edge
        float cursorYWorld = parentTopYWorld - topPadding;

        for (int i = 0; i < transform.childCount; i++)
        {
            Transform child = transform.GetChild(i);
            if (!includeInactive && !child.gameObject.activeInHierarchy) continue;

            float h = GetHeightWorld(child);

            // Child center should be half height below cursor
            float childCenterYWorld = cursorYWorld - (h * 0.5f);

            if (useLocalPosition)
            {
                // Convert target world position to local (preserve x/z)
                Vector3 worldPos = child.position;
                worldPos.y = childCenterYWorld;

                Vector3 localPos = transform.InverseTransformPoint(worldPos);

                Vector3 lp = child.localPosition;
                lp.y = localPos.y;
                child.localPosition = lp;
            }
            else
            {
                Vector3 p = child.position;
                p.y = childCenterYWorld;
                child.position = p;
            }

            // Move cursor down for next item
            cursorYWorld -= (h + spacing);
        }
    }

    float GetHeightWorld(Transform t)
    {
        if (!autoDetectHeight) return fallbackHeight;

        Renderer r = t.GetComponentInChildren<Renderer>();
        if (r != null) return r.bounds.size.y;

        return fallbackHeight;
    }
}