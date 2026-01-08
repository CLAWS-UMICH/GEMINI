using UnityEngine;

public class OffPathNotification : MonoBehaviour
{
    public GameObject notificationBarOffCourse;
    public GameObject notificationBarOnCourse;
    void Start()
    {
        notificationBarOffCourse.SetActive(false);
        notificationBarOnCourse.SetActive(false);
    }

    // to make the notification bar visible
    public void OffCourseTrigger()
    {
        notificationBarOffCourse.SetActive(true);
        notificationBarOnCourse.SetActive(false);
    }

    // to hide the notification bar after back on path
    public void OnCourseTrigger()
    {
        notificationBarOffCourse.SetActive(false);
        notificationBarOnCourse.SetActive(true);
        // add fading effect?
    }
}
