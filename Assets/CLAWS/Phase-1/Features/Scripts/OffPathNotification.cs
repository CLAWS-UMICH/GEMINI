using UnityEngine;

public class OffPathNotification : MonoBehaviour
{
    public GameObject notificationBar;
    // Start is called once before the first execution of Update after the MonoBehaviour is created
    void Start()
    {
        notificationBar.SetActive(false);
    }

    public void OnTriggerShow()
    {
        notificationBar.SetActive(true);
    }

    public void OnTriggerHide()
    {
        notificationBar.SetActive(false);
    }
    // Update is called once per frame
    void Update()
    {
        
    }
}
