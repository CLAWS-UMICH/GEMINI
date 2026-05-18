using UnityEngine;

public class CompanionIconScript : MonoBehaviour
{
    public enum IconMode { PR, LTV }

    [Tooltip("Which companion this icon represents.")]
    public IconMode mode = IconMode.PR;

    [Tooltip("Reference to TSSConnection (required for LTV mode).")]
    public TSSConnection tssConnection;

    void Update()
    {
        if (AstronautInstance.User == null || AstronautInstance.User.origin == null)
            return;

        float originX = (float)AstronautInstance.User.origin.posX;
        float originZ = (float)AstronautInstance.User.origin.posZ;

        if (mode == IconMode.PR)
        {
            // Read raw TSS rover position and apply origin offset
            var rover = AstronautInstance.User.rover?.rover;
            if (rover == null) return;

            float unityX = (float)rover.posx - originX;
            float unityZ = (float)rover.posy - originZ; // TSS Y maps to Unity Z
            transform.position = new Vector3(unityX, transform.position.y, unityZ);
        }
        else if (mode == IconMode.LTV)
        {
            // Read raw TSS LTV last-known location and apply origin offset
            if (tssConnection == null || !tssConnection.HasLtvLocation) return;

            Vector2 ltv = tssConnection.LatestLtvLocation;
            float unityX = ltv.x - originX;
            float unityZ = ltv.y - originZ; // TSS Y maps to Unity Z
            transform.position = new Vector3(unityX, transform.position.y, unityZ);
        }
    }
}
