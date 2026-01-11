using UnityEngine;

public class MainMenu : MonoBehaviour
{
    // Start is called once before the first execution of Update after the MonoBehaviour is created
    [SerializeField] private GameObject buttonGroup;
    [SerializeField] private GameObject screen1;
    [SerializeField] private GameObject screen2;
    [SerializeField] private GameObject welcomeScreen;
    [SerializeField] private GameObject vitals1;
    //[SerializeField] private GameObject vitals2;
    [SerializeField] private GameObject vitalsButton1;
    //[SerializeField] private GameObject vitalsButton2;
    [SerializeField] private GameObject miniMap;

    bool vitalsState = false;
    int screenState = 0;

    void Start()
    {
        AstronautInstance.User = new Astronaut();
        AstronautInstance.User.TSSurl = "http://127.0.0.1:14141/";
        AstronautInstance.User.id = 1;

        welcomeScreen.SetActive(true);
        buttonGroup.SetActive(false);
        screen1.SetActive(false);
        screen2.SetActive(false);
        vitals1.SetActive(false);
        //vitals2.SetActive(false);
        vitalsButton1.SetActive(false);
        //vitalsButton2.SetActive(false);
        miniMap.SetActive(false);
    }

    public void Done()
    {
        welcomeScreen.SetActive(false);
        screen1.SetActive(true);
        
        buttonGroup.SetActive(true);
        vitalsButton1.SetActive(true);
        //vitalsButton2.SetActive(true);
        miniMap.SetActive(true);
    }

    public void astronautID_1()
    {
        AstronautInstance.User.id = 1;
    }

    public void astronautID_2()
    {
        AstronautInstance.User.id = 2;
    }

    public void SwitchToScreen1()
    {
        screen1.SetActive(true);
        screen2.SetActive(false);
        closeVitals();
        screenState = 0;
    }

    public void SwitchToScreen2()
    {
        screen1.SetActive(false);
        screen2.SetActive(true);
        closeVitals();
        screenState = 1;
    }

    public void toggleVitals()
    {
        if (vitalsState)
        {
            if (screenState == 0)
            {
                screen1.SetActive(true);
                screen2.SetActive(false);
            }
            else if (screenState == 1)
            {
                screen1.SetActive(false);
                screen2.SetActive(true);
            }
            closeVitals();
        }
        else
        {
            screen1.SetActive(false);
            screen2.SetActive(false);
            vitals1.SetActive(true);
            vitalsState = true;
        }
    }
    
    public void closeVitals()
    {
        vitals1.SetActive(false);
        vitalsState = false;
    }
}
