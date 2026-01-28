using UnityEngine;
using UnityEngine.UI;
using System;

public class clock : MonoBehaviour
{
    bool clockActive = true;
    float currentTime;
    public Text currentTimeText;

    void Start()
    {
        currentTime = 0;
    }

    void Update()
    {
        if (clockActive == true)
        {
            currentTime = currentTime + Time.deltaTime;
            TimeSpan time = TimeSpan.FromSeconds(currentTime);
            currentTimeText.text = string.Format("{0:00}:{1:00}:{2:00}", time.Hours, time.Minutes, time.Seconds);
        }
    }

    public void StopTime()
    {
        clockActive = false;
    }
}
