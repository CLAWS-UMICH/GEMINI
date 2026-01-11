using MixedReality.Toolkit.UX;
using UnityEngine;
using TMPro;

public class VitalsUpdate : MonoBehaviour
{
    private Subscription<VitalsUpdateEvent> vitalsUpdateEvent;
    //private Subscription<VitalsUpdateEvent> fellowVitalsUpdateEvent;

    [SerializeField] private GameObject eva1Screen; // Handle UI for EV1
    //[SerializeField] private GameObject eva2Screen; // Handle UI for fellow astronaut

    // EVA1 VITALS
    [SerializeField] private GameObject eva1_heartRateText;
    [SerializeField] private GameObject eva1_radialProgress1;
    [SerializeField] private GameObject eva1_radialProgress2;
    [SerializeField] private GameObject eva1_oxygenTimeLeftText;
    [SerializeField] private GameObject eva1_oxySlider;
    [SerializeField] private GameObject eva1_suitTempText;
    [SerializeField] private GameObject eva1_batteryTimeLeftText;
    [SerializeField] private GameObject eva1_batterySlider;
    [SerializeField] private GameObject eva1_oxyPrimaryText;
    [SerializeField] private GameObject eva1_oxySecondaryText;

    // EVA2 VITALS
    // [SerializeField] private GameObject eva2_heartRateText;
    // private float eva2_oxygenTimeLeft;
    // [SerializeField] private GameObject eva2_oxygenTimeLeftText;
    // private float eva2_SuitTemp;
    // [SerializeField] private GameObject eva2_suitTempText;
    // private float eva2_batteryTimeLeft;
    // [SerializeField] private GameObject eva2_batteryTimeLeftText;
    // private float eva2_oxyPrimary;
    // [SerializeField] private GameObject eva2_oxyPrimaryText;
    // private float eva2_oxySecondary;
    // [SerializeField] private GameObject eva2_oxySecondaryText;



    // Start is called once before the first execution of Update after the MonoBehaviour is created
    void Start()
    {
        vitalsUpdateEvent = EventBus.Subscribe <VitalsUpdateEvent> (vitalsEventHandler);
        //fellowVitalsUpdateEvent = EventBus.Subscribe <VitalsUpdateEvent > (fellowVitalsEventHandler);
    }


    // the function that gets called when the event is fired
    private void vitalsEventHandler(VitalsUpdateEvent  e)
    {
        Debug.Log("Event received!");
        if (eva1_heartRateText == null) Debug.LogError("eva1_heartRateText is NULL!");
        if (e.Data == null) Debug.LogError("e.Data is NULL!");

        Debug.Log("Vitals event received! Heart rate: " + e.Data.heart_rate);
        // text
        eva1_heartRateText.GetComponent<TextMeshPro>().text = e.Data.heart_rate.ToString("F0");
        eva1_suitTempText.GetComponent<TextMeshPro>().text = e.Data.temperature.ToString("F1");

        // radial
        // Play around with the arc and angle values for the ringFull object
        float normalizedRate = ((float)e.Data.heart_rate - 40f) / (120f - 40f);
        float arcAngle1 = 304f - (normalizedRate * 304f);
        eva1_radialProgress1.GetComponent<SpriteRenderer>().material.SetFloat("_Arc2", arcAngle1);
        eva1_radialProgress1.GetComponent<SpriteRenderer>().color = Color.green;

        float normalizedTemp = ((float)e.Data.temperature - 60f) / (90f - 60f);
        float arcAngle2 = 304f - (normalizedTemp * 304f);
        eva1_radialProgress2.GetComponent<SpriteRenderer>().material.SetFloat("_Arc2", arcAngle2);
        eva1_radialProgress2.GetComponent<SpriteRenderer>().color = Color.orange;

        // progress bars
        // **Youll have to edit the slider in the inspector to set the max value**
        int oxyTimeLeftSeconds = e.Data.oxy_time_left;
        int oxyHours = oxyTimeLeftSeconds / 3600;
        int oxyMinutes = oxyTimeLeftSeconds % 3600 / 60;
        Debug.Log(oxyTimeLeftSeconds);
        eva1_oxygenTimeLeftText.GetComponent<TextMeshPro>().text = $"{oxyHours} hr {oxyMinutes} m";
        eva1_oxySlider.GetComponent<Slider>().Value = e.Data.oxy_time_left;
        // repeat for battery
        int battTimeLeftSeconds = e.Data.batt_time_left;
        int battHours = battTimeLeftSeconds / 3600;
        int battMinutes = battTimeLeftSeconds % 3600 / 60;
        eva1_batteryTimeLeftText.GetComponent<TextMeshPro>().text = $"{battHours} hr {battMinutes} m";
        eva1_batterySlider.GetComponent<Slider>().Value = e.Data.batt_time_left;

        //int oxyPrimaryStorage = e.Data.oxy_pri_storage;
        eva1_oxyPrimaryText.GetComponent<TextMeshPro>().text = e.Data.oxy_pri_storage.ToString("F2");
        eva1_oxySecondaryText.GetComponent<TextMeshPro>().text = e.Data.oxy_sec_storage.ToString("F2");

    }


    private void fellowVitalsEventHandler(VitalsUpdateEvent  e)
    {
        // repeat for fellow astronaut
        // ...
    }

}
