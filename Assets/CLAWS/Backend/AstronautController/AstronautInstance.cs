using UnityEngine;

// Last Updated:
//     Molly M. -- 9/30/2025


public class AstronautInstance : MonoBehaviour
{
    public static AstronautInstance instance { get; private set; }
    [SerializeField] private Astronaut _user;

    void Awake()
    {
        if (instance == null)
        {
            instance = this;
        }

    }

    // STATIC INTERFACE
    public static Astronaut User
    {
        get
        {
            return instance._user;
        }
        set
        {
            instance._user = value;
        }
    }

    void Start()
    {

    }

}
