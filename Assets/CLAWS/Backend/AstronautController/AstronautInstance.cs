using UnityEngine;

// Last Updated:
//     Molly M. -- 9/30/2025


public class AstronautInstance : MonoBehaviour
{
    public static AstronautInstance instance { get; private set; }
    private Astronaut _user;

    void Awake()
    {
        if (instance == null)
    {
        instance = this;
        
        if (_user == null)
        {
            _user = new Astronaut
            {
                TSSurl = "http://127.0.0.1:14141",
                id = 1
            };
            Debug.Log($"SET TSSurl to: '{_user.TSSurl}'");  // Add this
        }
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
