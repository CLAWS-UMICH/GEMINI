/// <summary>Shared POI default names for radial minimap placement and legacy flows.</summary>
public static class WaypointNamingHelper
{
    private const string Alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";

    public static string DefaultPoiName(int existingPoiCount)
    {
        return DefaultAddName(WaypointType.POI, existingPoiCount);
    }

    /// <summary>Default name for a newly added waypoint; uses per-type list index for the letter suffix.</summary>
    public static string DefaultAddName(WaypointType waypointType, int indexInType)
    {
        char letter = indexInType < Alphabet.Length ? Alphabet[indexInType] : '*';
        return "Waypoint " + letter;
    }
}
