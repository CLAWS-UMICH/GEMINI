using System.Collections;
using UnityEngine; 
using UnityEngine.Networking;
using UnityEngine.UI;
using System;
using TMPro;
using System.IO;
using System.Runtime.CompilerServices;

// Last Updated:
//     Molly M. -- 10/15/2025

public class ConnectToTSS : MonoBehaviour
{

    private int team_number; // zero
    private bool connected = false;
    private float time_since_last_update;

    // TODO
    private string TELEMETRYJsonString;



    // Start is called once before the first execution of Update after the MonoBehaviour is created
    void Start()
    {
        Debug.Log("Connecting to TSS at: " + AstronautInstance.User.TSSurl);
        // Test connection to frontend
        StartCoroutine(GetRequest(AstronautInstance.User.TSSurl));
    }

    IEnumerator GetRequest(string uri)
    {

        using (UnityWebRequest webRequest = UnityWebRequest.Get(uri))
        {
            yield return webRequest.SendWebRequest();
            string[] pages = uri.Split('/');
            int page = pages.Length - 1;
            Debug.Log(webRequest.result);
            switch (webRequest.result)
            {
                case UnityWebRequest.Result.ConnectionError:
                    break;
                case UnityWebRequest.Result.DataProcessingError:
                    Debug.LogError(pages[page] + ": Error: " + webRequest.error);
                    break;
                case UnityWebRequest.Result.ProtocolError:
                    Debug.LogError(pages[page] + ": HTTP Error: " + webRequest.error);
                    break;
                case UnityWebRequest.Result.Success:
                    Debug.Log("EXECUTED");
                    Debug.Log(pages[page] + ":\nReceived: " + webRequest.downloadHandler.text);
                    connected = true;
                    break;
                default:
                    Debug.LogError("Unexpected UnityWebRequest result: " + webRequest.result);
                    break;
            }

        }
    }

    // Update is called once per frame
    void Update()
    {
        if (connected)
        {
            // Each Second
            time_since_last_update += Time.deltaTime;
            if (time_since_last_update > 1.0f)
            {
                // Pull TSS Updates
                StartCoroutine(GetTELEMETRYState());
                time_since_last_update = 0.0f;
            }
        }
    }


    IEnumerator GetTELEMETRYState()
    {
        // Debug.Log(AstronautInstance.User.TSSurl + "/json_data/teams/" + this.team_number + "/TELEMETRY.json");
        using (UnityWebRequest webRequest = UnityWebRequest.Get(AstronautInstance.User.TSSurl + "/json_data/teams/" + this.team_number + "/TELEMETRY.json"))
        {

            // Request and wait for the desired page.
            yield return webRequest.SendWebRequest();
            switch (webRequest.result)
            {
                case UnityWebRequest.Result.Success:
                    if (TELEMETRYJsonString != webRequest.downloadHandler.text)
                    {
                        TELEMETRYJsonString = webRequest.downloadHandler.text;
                        AstronautInstance.User.telemetry = JsonUtility.FromJson<Telemetry>(this.TELEMETRYJsonString);
                        Debug.Log("Telemetry" + TELEMETRYJsonString);
                        if (AstronautInstance.User.id == 1)
                        {
                             EventBus.Publish<VitalsUpdateEvent>(new VitalsUpdateEvent(AstronautInstance.User.telemetry.telemetry.eva1));
                        }
                        else
                        {
                            EventBus.Publish<VitalsUpdateEvent>(new VitalsUpdateEvent(AstronautInstance.User.telemetry.telemetry.eva2));
                        }
                    }
                    break;
                case UnityWebRequest.Result.ConnectionError:
                    Debug.LogError("Connection error: " + webRequest.error);
                    break;
                case UnityWebRequest.Result.DataProcessingError:
                    Debug.LogError("Data processing error: " + webRequest.error);
                    break;
                case UnityWebRequest.Result.ProtocolError:
                    Debug.LogError("HTTP error: " + webRequest.error);
                    break;
            }

        }
    }

}
