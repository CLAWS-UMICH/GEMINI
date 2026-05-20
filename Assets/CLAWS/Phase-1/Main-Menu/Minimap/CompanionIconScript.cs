using UnityEngine;

public class CompanionIconScript : MonoBehaviour
{
    public enum IconMode { PR, LTV }

    [Tooltip("Which companion this icon represents.")]
    public IconMode mode = IconMode.PR;

    // Quad center = map origin in Unity world space
    private static readonly Vector3 QuadCenter = new Vector3(13.1f, 0f, 1.4f);

    // PR (UIA Egress/Ingress) coordinates
    private static readonly Vector2 PR_OFFSET = new Vector2(-15f, -25f);
    // LTV Task Board coordinates
    private static readonly Vector2 LTV_OFFSET = new Vector2(40f, 10f);

    void Start()
    {
        Vector2 offset = (mode == IconMode.PR) ? PR_OFFSET : LTV_OFFSET;

        transform.position = new Vector3(
            QuadCenter.x + offset.x,
            transform.position.y,
            QuadCenter.z + offset.y
        );
    }
}
