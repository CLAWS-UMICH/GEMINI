//in theory this could work? but I have no real way of testing it atm
//using Microsoft.MixedReality.Toolkit.Input;
//using UnityEngine;

//public class MRTKWaypointPlacer : MonoBehaviour, IMixedRealityPointerHandler
//{
//    public GameObject waypointPrefab;
//    private bool waypointPlaced = false;

//    public void OnPointerClicked(MixedRealityPointerEventData eventData)
//    {
//        if (waypointPlaced) return;

//        // Get the hit point in the world
//        Vector3 hitPosition = eventData.Pointer.Result.Details.Point;

//        // Spawn waypoint
//        GameObject waypoint = Instantiate(waypointPrefab, hitPosition, Quaternion.identity);

//        // Optional: hover offset
//        waypoint.transform.localPosition += Vector3.up * 0.2f;

//        waypointPlaced = true;
//    }

//    // These must be present but can be empty
//    public void OnPointerDown(MixedRealityPointerEventData eventData) { }
//    public void OnPointerDragged(MixedRealityPointerEventData eventData) { }
//    public void OnPointerUp(MixedRealityPointerEventData eventData) { }
//}