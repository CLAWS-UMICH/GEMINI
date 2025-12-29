using UnityEngine;

public class LineFollower : MonoBehaviour
{
    public Transform targetObject;     // Create the object
    public float minDistance = 0.1f;   // Only add a point if the object moved this much
    
    private LineRenderer lineRenderer;
    private Vector3 lastPosition;

    void Start()
    {
        lineRenderer = GetComponent<LineRenderer>();
        lineRenderer.positionCount = 0;
        
        if (targetObject != null)
        {
            AddPoint(targetObject.position);
            lastPosition = targetObject.position;
        }
    }

    void Update()
    {
        if (targetObject == null) return;

        // Check if the distance is feasible 
        float distance = Vector3.Distance(targetObject.position, lastPosition);
        
        if (distance > minDistance)
        {
            AddPoint(targetObject.position);
            lastPosition = targetObject.position;
        }
    }

    void AddPoint(Vector3 position)
    {
        RaycastHit hit;

        //apply ray casting to shift the line down and flatten it to the environemnt 
         if (Physics.Raycast(position, Vector3.down, out hit)){
                lineRenderer.positionCount++; //add another node so you dont max out
                lineRenderer.SetPosition(lineRenderer.positionCount - 1, new Vector3(position.x, targetObject.position.y - hit.distance + 1, position.z));
            }
    }
}