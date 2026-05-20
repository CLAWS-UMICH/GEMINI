using UnityEngine;

[DisallowMultipleComponent]
public class VerticalizeQRPrefab : MonoBehaviour
{
    [Tooltip("Extra yaw rotation around world up, in degrees. Use to spin the prefab if it's facing the wrong direction.")]
    public float yawOffsetDegrees = 0f;

    [Tooltip("If true, ignore the QR marker's facing and lock the prefab to face this world direction instead.")]
    public bool useFixedFacingDirection = false;

    public Vector3 fixedFacingDirection = Vector3.forward;

    [Tooltip("If true, the prefab's authored local rotation is preserved as an offset on top of the verticalized base rotation. Use this when the prefab's visible face isn't on its local +Z axis (e.g. slates lying flat).")]
    public bool preserveAuthoredRotation = true;

    private Quaternion authoredLocalRotationOffset = Quaternion.identity;
    private Vector3 fallbackInitialForward = Vector3.forward;

    private void Awake()
    {
        authoredLocalRotationOffset = transform.localRotation;
        fallbackInitialForward = transform.forward;
    }

    private void LateUpdate()
    {
        Vector3 facing;

        if (useFixedFacingDirection)
        {
            facing = fixedFacingDirection;
        }
        else
        {
            // Read facing from the parent (the QR anchor) — never from our own transform.
            // We mutate transform.rotation below; using transform.forward here would feed
            // the offset back into the next frame's facing calculation and spin the prefab.
            Transform source = transform.parent;
            Vector3 sourceForward = source != null ? source.forward : fallbackInitialForward;
            Vector3 sourceRight = source != null ? source.right : transform.right;

            facing = Vector3.ProjectOnPlane(sourceForward, Vector3.up);
            if (facing.sqrMagnitude < 1e-6f)
            {
                facing = Vector3.ProjectOnPlane(sourceRight, Vector3.up);
            }
            if (facing.sqrMagnitude < 1e-6f)
            {
                facing = Vector3.forward;
            }
        }

        facing.Normalize();

        Quaternion baseRotation = Quaternion.LookRotation(facing, Vector3.up);
        Quaternion yaw = Quaternion.AngleAxis(yawOffsetDegrees, Vector3.up);
        Quaternion worldRotation = yaw * baseRotation;

        if (preserveAuthoredRotation)
        {
            // Treat the authored local rotation as a local-space correction applied AFTER the
            // verticalized base. Lets the inspector rotation fix prefabs whose visible face
            // isn't on local +Z (e.g. quads/slates lying flat).
            transform.rotation = worldRotation * authoredLocalRotationOffset;
        }
        else
        {
            transform.rotation = worldRotation;
        }
    }
}
