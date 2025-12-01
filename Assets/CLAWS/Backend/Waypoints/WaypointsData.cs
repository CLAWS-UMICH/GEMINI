public enum WaypointType
{
    Custom,
    Station,
    POI,
    Geo,
    Danger,
    Companion,
    LTV
}

public enum WaypointAuthor
{
    Unknown,
    EV1,
    EV2,
    PR
}

[System.Serializable]
public class WaypointData
{
    public string Id;
    public string Name;
    public WaypointType Type;
    public WaypointAuthor Author;
    public Vector3 WorldPosition;
    public bool IsActive;
}