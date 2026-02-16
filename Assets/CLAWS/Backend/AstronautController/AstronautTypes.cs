using System.Collections.Generic;
using System.Linq;


[System.Serializable]
public class Data
{
    public string client; // Target client (e.g., "hololens_1", "hololens_2", "pr_client")
    public string type;   // case type (e.g., "VITALS", "WAYPOINTS", "MESSAGES")
    public Dictionary<string, object> data; // The message to send, dependent on what the room is
}

public class Location /// UNITY LOCATION ///
{
    public double posX; // X AXIS
    public double posY;
    public double posZ; // Y AXIS
    public double Heading;

    public Location() { }

    public Location(double posx, double posy, double posz, double heading)
    {
        this.posX = posx;
        this.posY = posy;
        this.posZ = posz;
        this.Heading = heading;
    }

    public override int GetHashCode()
    {
        return (posX, posY, posZ, Heading).GetHashCode();
    }


    public override bool Equals(object obj)
    {
        if (obj == null || GetType() != obj.GetType())
        {
            return false;
        }

        Location otherLoc = (Location)obj;
        return posX == otherLoc.posX &&
               posY == otherLoc.posY &&
               posZ == otherLoc.posZ &&
               Heading == otherLoc.Heading;
    }

}


[System.Serializable]
public class Telemetry
{
    public TelemetryDetails telemetry;
}

[System.Serializable]
public class TelemetryDetails
{
    public int eva_time;
    public VitalsDetails eva1;
    public VitalsDetails eva2;
}

[System.Serializable]
public class VitalsDetails
{
    public double batt_time_left; // ORA
    public double oxy_pri_storage; // ORA
    public double oxy_sec_storage; // ORA
    public double oxy_pri_pressure;
    public double oxy_sec_pressure;
    public int oxy_time_left; // ORA
    public double heart_rate; // ORA
    public double oxy_consumption; 
    public double co2_production;
    public double suit_pressure_oxy;
    public double suit_pressure_co2;
    public double suit_pressure_other;
    public double suit_pressure_total;
    public double fan_pri_rpm;
    public double fan_sec_rpm;
    public double helmet_pressure_co2;
    public double scrubber_a_co2_storage;
    public double scrubber_b_co2_storage;
    public double temperature; // ORA
    public double coolant_m;
    public double coolant_gas_pressure;
    public double coolant_liquid_pressure;
}