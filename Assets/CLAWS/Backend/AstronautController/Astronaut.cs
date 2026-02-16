// LSast Updated:
//     Molly M. -- 9/30/2025

[System.Serializable]
public class Astronaut
{
    public int id;
    public string name;
    public string color;
    public FellowAstronaut fellowAstronaut;
    public Location origin;
    public Location current;
    public string TSSurl;
    public Telemetry telemetry;

}
