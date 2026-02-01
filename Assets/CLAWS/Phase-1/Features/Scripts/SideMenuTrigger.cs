using UnityEngine;
using System.Collections;

public class SideMenuTrigger : MonoBehaviour
{
    [Header("Settings")]
    public Transform objectToMove;
    public float shiftAmount = 3f; // Set this to 3
    public float speed = 3f;       // How fast it moves, moves linearly

    private BoxCollider btnCollider; 

    private bool isMoving = false;

    void Start()
    {
        btnCollider = GetComponent<BoxCollider>();
    }

    // This is the function you select in the Button OnClick() list
    public void ShiftMenu()
    {
        // Prevent clicking while already moving to avoid glitches
        if (objectToMove != null && !isMoving)
        {
            StartCoroutine(SlideObject(shiftAmount));
        }
    }

    public void ShiftMenuBack()
    {
        // Prevent clicking while already moving to avoid glitches
        if (objectToMove != null && !isMoving)
        {
            StartCoroutine(SlideObject(-shiftAmount));
        }
    }

    IEnumerator SlideObject(float shift)
    {
        isMoving = true;

        // 1. We use localPosition to avoid "flying off" the screen
        Vector3 startPos = objectToMove.localPosition;

        // 2. We calculate the end position by ONLY adding to the X axis
        Vector3 endPos = new Vector3(startPos.x + shift, startPos.y, startPos.z);
        
        float t = 0; // t represents the percentage of the journey (0 to 1)
        
        while (t < 1f)
        {
            t += Time.deltaTime * speed;
            
            // Lerp finds the point between start and end based on 't'
            objectToMove.localPosition = Vector3.Lerp(startPos, endPos, t);
            
            yield return null; // Wait for next frame
        }

        // 3. Ensure it ends exactly on the target
        objectToMove.localPosition = endPos;
        isMoving = false;
    }
}