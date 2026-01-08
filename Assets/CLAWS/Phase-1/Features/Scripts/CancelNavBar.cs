using UnityEngine;
using TMPro;

public class CancelNavBar : MonoBehaviour
{
    public GameObject cancelNavBar;
    public TMP_Text text;
    void Start()
    {
        cancelNavBar.SetActive(false);
    }

    public void OnNavigationStart(string stationName)
    {
        cancelNavBar.SetActive(true);
        text.text = "Cancel navigation to " + stationName; 
    }

    public void OnNavigationEnd()
    {
        cancelNavBar.SetActive(false);
    }
}