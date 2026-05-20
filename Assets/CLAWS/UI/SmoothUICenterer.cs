using UnityEngine;
using MixedReality.Toolkit.SpatialManipulation;

public class SmoothUICenterer : MonoBehaviour
{
    [Header("Solver References")]
    [Tooltip("The Follow solver component to control.")]
    [SerializeField] private Follow followSolver;

    [Header("Dead Zone Settings")]
    [Tooltip("The normal horizontal dead zone angle (in degrees) when looking around.")]
    [SerializeField] private float normalDeadZone = 55f;

    [Header("Recenter Timing")]
    [Tooltip("Time in seconds that the head must remain still before the UI starts to center.")]
    [SerializeField] private float stillTimeThreshold = 1.0f;

    [Tooltip("Head yaw angular speed (degrees/sec) below which the head is considered still.")]
    [SerializeField] private float rotationSpeedThreshold = 8f;

    [Tooltip("Speed multiplier at which the dead zone angle shrinks during recentering.")]
    [SerializeField] private float returnLerpSpeed = 1.5f;

    [Header("State (For Debugging)")]
    [SerializeField] private float stillTimer;
    [SerializeField] private bool isRecentering;
    [SerializeField] private float currentHeadSpeed;

    private Transform cameraTransform;
    private float lastRotationY;

    private void Start()
    {
        if (followSolver == null)
        {
            followSolver = GetComponent<Follow>();
        }

        cameraTransform = Camera.main != null ? Camera.main.transform : null;
        if (cameraTransform != null)
        {
            lastRotationY = cameraTransform.eulerAngles.y;
        }
    }

    private void Update()
    {
        if (cameraTransform == null)
        {
            if (Camera.main != null)
            {
                cameraTransform = Camera.main.transform;
                lastRotationY = cameraTransform.eulerAngles.y;
            }
            return;
        }

        if (followSolver == null) return;

        // Calculate angular velocity of head yaw (Y-rotation)
        float currentRotationY = cameraTransform.eulerAngles.y;
        float deltaRotation = Mathf.Abs(Mathf.DeltaAngle(currentRotationY, lastRotationY));
        currentHeadSpeed = deltaRotation / Time.deltaTime;
        lastRotationY = currentRotationY;

        // If the user starts rotating head fast, abort centering and restore dead zone immediately
        if (currentHeadSpeed > rotationSpeedThreshold)
        {
            stillTimer = 0f;
            if (isRecentering || followSolver.MaxViewHorizontalDegrees < normalDeadZone)
            {
                isRecentering = false;
                followSolver.MaxViewHorizontalDegrees = normalDeadZone;
            }
        }
        else
        {
            stillTimer += Time.deltaTime;
        }

        // Trigger recentering when head has been still for stillTimeThreshold seconds
        if (stillTimer >= stillTimeThreshold && !isRecentering)
        {
            isRecentering = true;
        }

        if (isRecentering)
        {
            // Smoothly collapse the dead zone threshold to 0.
            // As the dead zone reaches 0, the Follow component naturally glides the UI to the center.
            followSolver.MaxViewHorizontalDegrees = Mathf.MoveTowards(
                followSolver.MaxViewHorizontalDegrees,
                0f,
                Time.deltaTime * returnLerpSpeed * normalDeadZone
            );

            // Compute angle between camera forward and UI's position relative to camera
            Vector3 directionToUI = transform.position - cameraTransform.position;
            float angleToCenter = Vector3.Angle(cameraTransform.forward, directionToUI);

            // Once the UI is close to the center, restore normal dead zone and complete recenter
            if (angleToCenter < 3f)
            {
                followSolver.MaxViewHorizontalDegrees = normalDeadZone;
                isRecentering = false;
                stillTimer = 0f;
            }
        }
    }
}
