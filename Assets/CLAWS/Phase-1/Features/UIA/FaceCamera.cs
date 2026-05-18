using UnityEngine;

[DisallowMultipleComponent]
public class FaceCamera : MonoBehaviour
{
    [Tooltip("Optional. Defaults to Camera.main at runtime.")]
    public Transform target;

    [Tooltip("If true, lock the up-axis so the prefab does not tilt when the user looks up/down.")]
    public bool lockVertical = true;

    [Tooltip("If true, the prefab's +Z faces the camera (typical for UI slates). If false, the back faces the camera.")]
    public bool faceForwardToCamera = true;

    private void LateUpdate()
    {
        if (target == null)
        {
            var cam = Camera.main;
            if (cam == null) return;
            target = cam.transform;
        }

        Vector3 toCam = target.position - transform.position;
        if (lockVertical) toCam.y = 0f;
        if (toCam.sqrMagnitude < 1e-6f) return;

        Vector3 forward = faceForwardToCamera ? toCam : -toCam;
        transform.rotation = Quaternion.LookRotation(forward, Vector3.up);
    }
}
