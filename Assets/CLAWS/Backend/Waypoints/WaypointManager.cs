using System;
using System.Collections.Generic;
using UnityEngine;
// MEI NOTE: single source of truth for all waypoints; replaces AURA’s EventBus + scattered lists.
// Questions: 
// 1. Move waypoints? if yes implement a UpdateWaypointPosition
public class WaypointManager : MonoBehaviour
{
    # region Public API
    public WaypointData CreateWaypoint(Vector3 worldPos, WaypointType type, string name, WaypointAuthor author)
    {
        
    }

    public void RemoveWaypoint(string id)
    {
        
    }

    public void SetActiveWaypoint(string id)
    {
        
    }


    // RETURNS ALL WAYPOINTS (READ-ONLY)
    public IReadOnlyCollection<WaypointData> GetAllWaypoints()
    {
        return _waypoints.Values;
    }

    public IEnumerable<WaypointData> GetWaypointsOfType(WaypointType type)
    {
        
    }   
    #endregion

    # region World Marker Management
    private void SpawnWorldMarker(WaypointData waypoint)
    {
        
    }

    private void DespawnWorldMarker(string id)
    {
        
    }

    private void UpdateMarkerTransform(string id)
    {
        // Update marker world position to match the waypoint data.
    }
    #endregion
}