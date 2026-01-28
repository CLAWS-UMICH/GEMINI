using UnityEngine;
using UnityEngine.UI;
using TMPro; // only if using TextMeshPro

public class Waypoint : MonoBehaviour
{
    [Header("World visuals")]
    public Transform[] visuals;

    [Header("Distance text")]
    public TextMeshProUGUI distanceText;
    //public Transform distanceTextTransform;

    //[Header("Arrow UI")]
    //public Image leftArrow;
    //public Image rightArrow;

    void LateUpdate()
    {
        if (Camera.main == null) return;

        Transform cam = Camera.main.transform;

        // --- Check if waypoint is in front and on screen ---
        Vector3 viewportPos = Camera.main.WorldToViewportPoint(transform.position);
        const float margin = 0.15f;
        bool inFront = viewportPos.z > 0 
            && viewportPos.x >= -margin && viewportPos.x <= 1f + margin 
            && viewportPos.y >= -margin && viewportPos.y <= 1f + margin;

        // --- World visuals ---
        foreach (Transform v in visuals)
        {
            v.gameObject.SetActive(inFront);
            if (inFront)
            {
                Vector3 dir = v.position - cam.position;
                dir.y = 0f;
                if(dir.sqrMagnitude > 0.001f)
                {
                    v.rotation = Quaternion.LookRotation(dir);

                    //potentially can be used for multiple waypoints
                    //to ensure that they are perpendicular to their individual ground
                    //Quaternion surfaceRotation = Quaternion.FromToRotation(Vector3.up, hit.normal);
                    //v.rotation = surfaceRotation * Quaternion.LookRotation(dir);
                }
            }
        }

        // --- Distance text ---
        if (distanceText != null)
        {

            if (inFront)
            {         
                // Update distance
                float distance = Vector3.Distance(cam.position, transform.position);
                distanceText.text = $"{distance:F1}m"; // e.g., 2.3m
            }
        }

        // --- Arrow UI ---
        //bool arrowVisible = !inFront;
        //leftArrow.gameObject.SetActive(arrowVisible);
        //rightArrow.gameObject.SetActive(arrowVisible);

        //if (arrowVisible)
        //{
        //    // Determine side
        //    if (viewportPos.z < 0)
        //    {
        //        // Waypoint behind camera → choose arbitrary side
        //        leftArrow.transform.SetAsLastSibling();
        //        rightArrow.transform.SetAsLastSibling();
        //        leftArrow.gameObject.SetActive(true);
        //        rightArrow.gameObject.SetActive(false);
        //    }
        //    else
        //    {
        //        // Offscreen to left/right
        //        if (viewportPos.x < 0)
        //        {
        //            leftArrow.gameObject.SetActive(true);
        //            rightArrow.gameObject.SetActive(false);
        //        }
        //        else
        //        {
        //            leftArrow.gameObject.SetActive(false);
        //            rightArrow.gameObject.SetActive(true);
        //        }
        //    }
        //}
    }
}