using UnityEngine;

[DisallowMultipleComponent]
public class VerticalizeQRPrefab : MonoBehaviour
{
    [Tooltip("Extra yaw rotation around world up, in degrees. Use to spin the prefab if it's facing the wrong direction.")]
    public float yawOffsetDegrees = 0f;

    [Tooltip("If true, ignore the QR marker's facing and lock the prefab to face this world direction instead.")]
    public bool useFixedFacingDirection = false;

    public Vector3 fixedFacingDirection = Vector3.forward;

    private void LateUpdate()
    {
        Vector3 facing;

        if (useFixedFacingDirection)
        {
            facing = fixedFacingDirection;
        }
        else
        {
            facing = Vector3.ProjectOnPlane(transform.forward, Vector3.up);
            if (facing.sqrMagnitude < 1e-6f)
            {
                facing = Vector3.ProjectOnPlane(transform.right, Vector3.up);
            }
            if (facing.sqrMagnitude < 1e-6f)
            {
                facing = Vector3.forward;
            }
        }

        facing.Normalize();

        Quaternion baseRotation = Quaternion.LookRotation(facing, Vector3.up);
        Quaternion yaw = Quaternion.AngleAxis(yawOffsetDegrees, Vector3.up);
        transform.rotation = yaw * baseRotation;
    }
}
