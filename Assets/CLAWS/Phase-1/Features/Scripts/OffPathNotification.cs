using UnityEngine;

public class OffPathNotification : MonoBehaviour
{
    public GameObject notificationBar;
    void Start()
    {
        notificationBar.SetActive(false);
    }

    // to make the notification bar visible
    public void OnTriggerShow()
    {
        notificationBar.SetActive(true);
    }

    // to hide the notification bar after back on path
    public void OnTriggerHide()
    {
        notificationBar.SetActive(false);
        // add fading effect?
    }
}
