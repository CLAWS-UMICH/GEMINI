using UnityEngine;

/// <summary>
/// Optional: attach to the destination waypoint indicator GameObject to make it gently bob up and down.
/// Pathfinding sets this object's world position when the target changes; this script adds a small vertical oscillation.
/// </summary>
public class DestinationWaypointFloat : MonoBehaviour
{
    [Tooltip("Amplitude of the bobbing motion in meters.")]
    [SerializeField] private float amplitude = 0.2f;
    [Tooltip("Speed of the bobbing (cycles per second).")]
    [SerializeField] private float frequency = 1f;

    private float previousOffset;

    void LateUpdate()
    {
        float offset = amplitude * Mathf.Sin(2f * Mathf.PI * frequency * Time.time);
        Vector3 p = transform.position;
        // Remove previous frame's offset so we don't drift, then add new offset
        transform.position = new Vector3(p.x, p.y - previousOffset + offset, p.z);
        previousOffset = offset;
    }
}
