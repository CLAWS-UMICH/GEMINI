using System.Collections.Generic;

// Last Updated:
//    Molly M. -- 9/30/2025


// Example Event Type:
public class Event 
{
    public string message { get; private set; }

    public Event(string msg)
    {
        message = msg;
    }
}

// Add event types here as needed...
// TODO:
// - Add a vitals update event type for EV1

public class VitalsUpdateEvent
{
    public VitalsDetails Data { get; private set; }

    public VitalsUpdateEvent(VitalsDetails vitals)
    {
        Data = vitals;
    }
}
// - Add a vitals update event type for EV2


