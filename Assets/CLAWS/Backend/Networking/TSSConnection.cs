using System.Collections;
using UnityEngine; 
using UnityEngine.Networking;
using UnityEngine.UI;
using System;
using TMPro;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading.Tasks;

public class TSSConnection : MonoBehaviour
{
    [SerializeField] private GameObject minimap;
    [Tooltip("TSS team id used in /json_data/teams/{team}/TELEMETRY.json. Override per scene; default is 0 for single-team dev stacks.")]
    [SerializeField] private int tssTeamNumber = 0;
    [SerializeField] private int tssPort = 14141;
    private string IPaddr;
    private string tssHost;
    int team_number;
    bool connected;
    float time_since_last_update;
    public Action<bool> OnTSSConnectionResult;
    private bool imuInitialized = false;
    private bool telemetryErrorLogged = false;
    private bool telemetryRequestInFlight = false;

    private const int UdpEvaTelemetryCommand = 1;
    private const int UdpTimeoutMs = 2000;


    // Database Jsons
    string UIAJsonString;
    string DCUJsonString;
    string ErrorJsonString;
    string ROVERJsonString;
    string SPECJsonString;
    string TELEMETRYJsonString;
    string COMMJsonString;
    string IMUJsonString;


    // Connect to TSS
    public void ConnectToHost(string IP_host, int _team_number)
    {
        DisconnectFromHost();
        team_number = _team_number;
        tssHost = IP_host;
        AstronautInstance.User.TSSurl = "http://" + IP_host + ":" + tssPort;
        Debug.Log("Connecting to TSS UDP telemetry at: " + tssHost + ":" + tssPort);
        StartCoroutine(TryConnectUdpTelemetry());
    }

    public void LookForConnection()
    {
        if (!connected && IPaddr.Length > 0 && !IPaddr.Contains("/"))
        {
            ConnectToHost(IPaddr, tssTeamNumber);
        }
    }


    // called from main connection
    public void TSSConnect(string ip)
    {
        IPaddr = ip;
        Debug.Log("IPAddr: " + IPaddr);
        LookForConnection();
    }


    // attach to final screen disconnect button
    public void DisconnectFromHost()
    {
        connected = false;
        telemetryErrorLogged = false;
        telemetryRequestInFlight = false;
    }


    private string GetTelemetryUrl()
    {
        return AstronautInstance.User.TSSurl + "/json_data/teams/" + this.team_number + "/TELEMETRY.json";
    }


    void Start()
    {
        connected = false;
    }


    void OnDisable()
    {
        Debug.LogWarning("[TSS] TSSConnection.OnDisable -- any in-flight coroutines are stopping. connected=" + connected);
    }


    void OnDestroy()
    {
        Debug.LogWarning("[TSS] TSSConnection.OnDestroy -- component is being destroyed. connected=" + connected);
    }


    void Update()
    {
        // If you are connected to TSS
        if (connected)
        {
            // Each Second
            time_since_last_update += Time.deltaTime;
            if (time_since_last_update > 1.0f)
            {
                // Pull EVA telemetry over the UDP TSS protocol used by the local simulator.
                StartCoroutine(GetUdpTelemetryState());
                time_since_last_update = 0.0f;
            }
        }
    }


    private IEnumerator TryConnectUdpTelemetry()
    {
        yield return FetchAndApplyUdpTelemetry(true);
    }


    private IEnumerator GetUdpTelemetryState()
    {
        yield return FetchAndApplyUdpTelemetry(false);
    }


    private IEnumerator FetchAndApplyUdpTelemetry(bool connectionAttempt)
    {
        if (telemetryRequestInFlight)
            yield break;

        telemetryRequestInFlight = true;
        Task<string> telemetryTask = FetchUdpTelemetryJsonAsync();
        yield return new WaitUntil(() => telemetryTask.IsCompleted);
        telemetryRequestInFlight = false;

        if (telemetryTask.IsFaulted || telemetryTask.IsCanceled)
        {
            Exception error = telemetryTask.Exception?.GetBaseException();
            HandleUdpTelemetryFailure(connectionAttempt, error != null ? error.Message : "UDP telemetry request was canceled.");
            yield break;
        }

        if (!ApplyUdpTelemetryJson(telemetryTask.Result, connectionAttempt))
        {
            HandleUdpTelemetryFailure(connectionAttempt, "UDP telemetry JSON was empty or did not include telemetry.eva1/eva2.");
            yield break;
        }

        telemetryErrorLogged = false;
        if (connectionAttempt)
        {
            connected = true;
            OnTSSConnectionResult?.Invoke(true);
            Debug.Log("[TSS] UDP telemetry connected: " + tssHost + ":" + tssPort);
        }
    }


    private Task<string> FetchUdpTelemetryJsonAsync()
    {
        string host = tssHost;
        int port = tssPort;
        return Task.Run(() =>
        {
            using (UdpClient client = new UdpClient())
            {
                client.Client.ReceiveTimeout = UdpTimeoutMs;
                byte[] request = BuildUdpCommandPacket(UdpEvaTelemetryCommand);
                client.Send(request, request.Length, host, port);
                IPEndPoint remoteEndPoint = new IPEndPoint(IPAddress.Any, 0);
                byte[] response = client.Receive(ref remoteEndPoint);
                return ExtractJsonPayload(response);
            }
        });
    }


    private byte[] BuildUdpCommandPacket(int command)
    {
        byte[] packet = new byte[8];
        int unixTime = (int)(DateTime.UtcNow - new DateTime(1970, 1, 1, 0, 0, 0, DateTimeKind.Utc)).TotalSeconds;
        Buffer.BlockCopy(BitConverter.GetBytes(IPAddress.HostToNetworkOrder(unixTime)), 0, packet, 0, 4);
        Buffer.BlockCopy(BitConverter.GetBytes(IPAddress.HostToNetworkOrder(command)), 0, packet, 4, 4);
        return packet;
    }


    private string ExtractJsonPayload(byte[] response)
    {
        int start = Array.IndexOf(response, (byte)'{');
        int end = Array.LastIndexOf(response, (byte)'}');
        if (start < 0 || end <= start)
            throw new InvalidOperationException("UDP telemetry response did not contain a JSON object.");

        return Encoding.UTF8.GetString(response, start, end - start + 1);
    }


    private bool ApplyUdpTelemetryJson(string json, bool forcePublish)
    {
        if (string.IsNullOrEmpty(json))
            return false;

        UdpTssPayload payload = JsonUtility.FromJson<UdpTssPayload>(json);
        if (payload?.telemetry?.eva1 == null || payload.telemetry.eva2 == null)
            return false;

        bool changed = TELEMETRYJsonString != json;
        TELEMETRYJsonString = json;

        TELEMETRY telemetry = new TELEMETRY
        {
            telemetry = new TelemetryDetails
            {
                eva_time = Mathf.RoundToInt((float)Math.Max(payload.telemetry.eva1.eva_elapsed_time, payload.telemetry.eva2.eva_elapsed_time)),
                eva1 = MapUdpEvaTelemetry(payload.telemetry.eva1, AstronautInstance.User.telemetry?.telemetry?.eva1),
                eva2 = MapUdpEvaTelemetry(payload.telemetry.eva2, AstronautInstance.User.telemetry?.telemetry?.eva2)
            }
        };

        AstronautInstance.User.telemetry = telemetry;
        if (changed || forcePublish)
        {
            Debug.Log("Telemetry" + json);
            PublishTelemetryVitals(telemetry);
        }

        return true;
    }


    private EvaTelemetryDetails MapUdpEvaTelemetry(UdpEvaTelemetry udp, EvaTelemetryDetails previous)
    {
        return new EvaTelemetryDetails
        {
            batt_time_left = previous != null ? previous.batt_time_left : 0,
            oxy_pri_storage = udp.oxy_pri_storage,
            oxy_sec_storage = udp.oxy_sec_storage,
            oxy_pri_pressure = udp.oxy_pri_pressure,
            oxy_sec_pressure = udp.oxy_sec_pressure,
            oxy_time_left = previous != null ? previous.oxy_time_left : 0,
            heart_rate = udp.heart_rate,
            oxy_consumption = udp.oxy_consumption,
            co2_production = udp.co2_production,
            suit_pressure_oxy = udp.suit_pressure_oxy,
            suit_pressure_co2 = udp.suit_pressure_co2,
            suit_pressure_other = udp.suit_pressure_other,
            suit_pressure_total = udp.suit_pressure_total,
            fan_pri_rpm = udp.fan_pri_rpm,
            fan_sec_rpm = udp.fan_sec_rpm,
            helmet_pressure_co2 = udp.helmet_pressure_co2,
            scrubber_a_co2_storage = udp.scrubber_a_co2_storage,
            scrubber_b_co2_storage = udp.scrubber_b_co2_storage,
            temperature = udp.temperature,
            coolant_m = udp.coolant_storage,
            coolant_gas_pressure = udp.coolant_gas_pressure,
            coolant_liquid_pressure = udp.coolant_liquid_pressure
        };
    }


    private void PublishTelemetryVitals(TELEMETRY telemetry)
    {
        if (AstronautInstance.User.id == 1)
        {
            CopyVitals(AstronautInstance.User.vitals, telemetry.telemetry.eva1);
            CopyVitals(AstronautInstance.User.fellowAstronaut.vitals, telemetry.telemetry.eva2);
        }
        else
        {
            CopyVitals(AstronautInstance.User.vitals, telemetry.telemetry.eva2);
            CopyVitals(AstronautInstance.User.fellowAstronaut.vitals, telemetry.telemetry.eva1);
        }

        AstronautInstance.User.vitals.eva_time = telemetry.telemetry.eva_time;
        EventBus.Publish<UpdatedVitalsEvent>(new UpdatedVitalsEvent(AstronautInstance.User.vitals));
        EventBus.Publish<UpdatedFellowAstronautVitalsEvent>(new UpdatedFellowAstronautVitalsEvent(AstronautInstance.User.fellowAstronaut.vitals));
    }


    private void HandleUdpTelemetryFailure(bool connectionAttempt, string message)
    {
        connected = false;
        if (!telemetryErrorLogged)
        {
            telemetryErrorLogged = true;
            Debug.LogError("[TSS] UDP telemetry " + (connectionAttempt ? "connection" : "poll") +
                           " failed for " + tssHost + ":" + tssPort +
                           " command=" + UdpEvaTelemetryCommand + ". " + message);
        }

        OnTSSConnectionResult?.Invoke(false);
    }


    IEnumerator GetRequest(string uri)
    {
        const float HardTimeoutSeconds = 8f;
        const float ProgressLogIntervalSeconds = 1f;

        Debug.Log("[TSS] GetRequest start: " + uri + " (gameObject.active=" + gameObject.activeInHierarchy +
                  ", component.enabled=" + enabled + ", time=" + Time.realtimeSinceStartup.ToString("F2") + ")");

        using (UnityWebRequest webRequest = UnityWebRequest.Get(uri))
        {
            webRequest.timeout = 5;
            float startTime = Time.realtimeSinceStartup;
            UnityWebRequestAsyncOperation op = webRequest.SendWebRequest();

            float lastLog = startTime;
            while (!op.isDone)
            {
                float now = Time.realtimeSinceStartup;
                float elapsed = now - startTime;
                if (now - lastLog >= ProgressLogIntervalSeconds)
                {
                    Debug.Log("[TSS] GetRequest waiting: " + uri +
                              " elapsed=" + elapsed.ToString("F1") +
                              "s downloadProgress=" + webRequest.downloadProgress.ToString("F2") +
                              " bytes=" + webRequest.downloadedBytes +
                              " result=" + webRequest.result);
                    lastLog = now;
                }

                if (elapsed > HardTimeoutSeconds)
                {
                    Debug.LogError("[TSS] GetRequest HARD TIMEOUT after " + elapsed.ToString("F1") +
                                   "s on " + uri + " -- aborting. result=" + webRequest.result +
                                   " err=" + webRequest.error);
                    webRequest.Abort();
                    break;
                }

                yield return null;
            }

            float totalElapsed = Time.realtimeSinceStartup - startTime;
            string[] pages = uri.Split('/');
            int page = pages.Length - 1;
            Debug.Log("[TSS] GetRequest complete: result=" + webRequest.result +
                      " code=" + webRequest.responseCode +
                      " err=" + (string.IsNullOrEmpty(webRequest.error) ? "<none>" : webRequest.error) +
                      " elapsed=" + totalElapsed.ToString("F2") + "s" +
                      " uri=" + uri);
            switch (webRequest.result)
            {
                case UnityWebRequest.Result.ConnectionError:
                    Debug.LogError("[TSS] ConnectionError on " + uri + ": " + webRequest.error);
                    OnTSSConnectionResult?.Invoke(false);
                    break;
                case UnityWebRequest.Result.DataProcessingError:
                    OnTSSConnectionResult?.Invoke(false);
                    Debug.LogError(pages[page] + ": Error: " + webRequest.error);
                    break;
                case UnityWebRequest.Result.ProtocolError:
                    OnTSSConnectionResult?.Invoke(false);
                    Debug.LogError(pages[page] + ": HTTP Error: " + webRequest.error +
                                   " (code " + webRequest.responseCode + ")");
                    break;
                case UnityWebRequest.Result.Success:
                    Debug.Log("EXECUTED");
                    OnTSSConnectionResult?.Invoke(true);
                    Debug.Log(pages[page] + ":\nReceived: " + webRequest.downloadHandler.text);
                    connected = true;
                    break;
                default:
                    Debug.LogError("[TSS] Unexpected UnityWebRequest result: " + webRequest.result +
                                   " code=" + webRequest.responseCode +
                                   " err=" + webRequest.error);
                    OnTSSConnectionResult?.Invoke(false);
                    break;
            }

        }
    }

    ////////////////////////////  UIA  /////////////////////////////
    IEnumerator GetUIAState()
    {
        using (UnityWebRequest webRequest = UnityWebRequest.Get(AstronautInstance.User.TSSurl + "/json_data/UIA.json"))
        {
            yield return webRequest.SendWebRequest();

            switch (webRequest.result)
            {
                case UnityWebRequest.Result.Success:
                    if (UIAJsonString != webRequest.downloadHandler.text)
                    {
                        UIAJsonString = webRequest.downloadHandler.text;

                        AstronautInstance.User.uia = JsonUtility.FromJson<UIA>(UIAJsonString);

                        EventBus.Publish(new UIAUpdatedEvent(AstronautInstance.User.uia));
                    }
                    break;
            }

        }
    }



    ////////////////////////////  DCU  /////////////////////////////
    IEnumerator GetDCUState()
    {
        using (UnityWebRequest webRequest = UnityWebRequest.Get(AstronautInstance.User.TSSurl + "/json_data/DCU.json"))
        {
            // Request and wait for the desired page.
            yield return webRequest.SendWebRequest();
            switch (webRequest.result)
            {
                case UnityWebRequest.Result.Success:
                    if (DCUJsonString != webRequest.downloadHandler.text)
                    {
                        DCUJsonString = webRequest.downloadHandler.text;
                        AstronautInstance.User.dcu = JsonUtility.FromJson<DCU>(DCUJsonString);
                        Debug.Log("DCU STATE" + DCUJsonString);
                        EventBus.Publish(new DCUChangedEvent(AstronautInstance.User.dcu.dcu.eva1));
                        EventBus.Publish(new FellowDCUChangedEvent(AstronautInstance.User.dcu.dcu.eva2));
                    }
                    break;
            }

        }
    }

    IEnumerator GetDCUError()
    {
        using (UnityWebRequest webRequest = UnityWebRequest.Get(AstronautInstance.User.TSSurl + "/json_data/ERROR.json"))
        {
            // Request and wait for the desired page.
            yield return webRequest.SendWebRequest();
            switch (webRequest.result)
            {
                case UnityWebRequest.Result.Success:
                    if (ErrorJsonString != webRequest.downloadHandler.text)
                    {
                        ErrorJsonString = webRequest.downloadHandler.text;
                        ErrorMsg e;
                        e = JsonUtility.FromJson<ErrorMsg>(ErrorJsonString);
                        EventBus.Publish(new DCUErrorEvent(e));
                    }
                    break;
            }

        }
    }


    ////////////////////////////  SPEC  /////////////////////////////
    IEnumerator GetSPECState()
    {



        using (UnityWebRequest webRequest = UnityWebRequest.Get(AstronautInstance.User.TSSurl + "/json_data/SPEC.json"))
        {
            // Request and wait for the desired page.
            yield return webRequest.SendWebRequest();
            switch (webRequest.result)
            {
                case UnityWebRequest.Result.Success:
                    if (SPECJsonString != webRequest.downloadHandler.text)
                    {
                        SPECJsonString = webRequest.downloadHandler.text;

                        AstronautInstance.User.spec = JsonUtility.FromJson<SPEC>(SPECJsonString);
                        if (AstronautInstance.User.id == 1)
                        {
                            EventBus.Publish<XRFScanEvent>(new XRFScanEvent(AstronautInstance.User.spec.spec.eva1.data));
                        } 
                        else
                        {
                            EventBus.Publish<XRFScanEvent>(new XRFScanEvent(AstronautInstance.User.spec.spec.eva2.data));
                        }
                            
                    }
                    break;
            }

        }
    }


    IEnumerator GetROVERState()
    {
        using (UnityWebRequest webRequest = UnityWebRequest.Get(AstronautInstance.User.TSSurl + "/json_data/ROVER.json"))
        {
            // Request and wait for the desired page.
            yield return webRequest.SendWebRequest();

            switch (webRequest.result)
            {
                case UnityWebRequest.Result.Success:
                    if (ROVERJsonString != webRequest.downloadHandler.text)
                    {
                        ROVERJsonString = webRequest.downloadHandler.text;
                        AstronautInstance.User.rover = JsonUtility.FromJson<ROVER>(ROVERJsonString);
                        EventBus.Publish(new RoverUpdatedEvent(AstronautInstance.User.rover.rover));
                    }
                    break;
            }

        }
    }


    ////////////////////////////  EVA VITALS /////////////////////////////
    IEnumerator GetTELEMETRYState()
    {
        string telemetryUrl = GetTelemetryUrl();
        using (UnityWebRequest webRequest = UnityWebRequest.Get(telemetryUrl))
        {

            // Request and wait for the desired page.
            yield return webRequest.SendWebRequest();
            switch (webRequest.result)
            {
                case UnityWebRequest.Result.Success:
                    telemetryErrorLogged = false;
                    if (TELEMETRYJsonString != webRequest.downloadHandler.text)
                    {
                        TELEMETRYJsonString = webRequest.downloadHandler.text;
                        AstronautInstance.User.telemetry = JsonUtility.FromJson<TELEMETRY>(this.TELEMETRYJsonString);
                        Debug.Log("Telemetry" + TELEMETRYJsonString);

                        if (AstronautInstance.User.id == 1)
                        {
                            CopyVitals(AstronautInstance.User.vitals, AstronautInstance.User.telemetry.telemetry.eva1);
                            CopyVitals(AstronautInstance.User.fellowAstronaut.vitals, AstronautInstance.User.telemetry.telemetry.eva2);
                        }
                        else
                        {
                            CopyVitals(AstronautInstance.User.vitals, AstronautInstance.User.telemetry.telemetry.eva2);
                            CopyVitals(AstronautInstance.User.fellowAstronaut.vitals, AstronautInstance.User.telemetry.telemetry.eva1);
                        }
                        AstronautInstance.User.vitals.eva_time = AstronautInstance.User.telemetry.telemetry.eva_time;
                        EventBus.Publish<UpdatedVitalsEvent>(new UpdatedVitalsEvent(AstronautInstance.User.vitals));
                        EventBus.Publish<UpdatedFellowAstronautVitalsEvent>(new UpdatedFellowAstronautVitalsEvent(AstronautInstance.User.fellowAstronaut.vitals));
                    }
                    break;
                case UnityWebRequest.Result.ConnectionError:
                    LogTelemetryFailure("Connection error", telemetryUrl, webRequest);
                    break;
                case UnityWebRequest.Result.DataProcessingError:
                    LogTelemetryFailure("Data processing error", telemetryUrl, webRequest);
                    break;
                case UnityWebRequest.Result.ProtocolError:
                    LogTelemetryFailure("HTTP error", telemetryUrl, webRequest);
                    break;
            }

        }
    }

    private void LogTelemetryFailure(string failureType, string telemetryUrl, UnityWebRequest webRequest)
    {
        connected = false;
        if (telemetryErrorLogged)
            return;

        telemetryErrorLogged = true;
        Debug.LogError("[TSS] " + failureType + " while reading telemetry. " +
                       "Stopping TSS polling because vitals cannot stream. " +
                       "team=" + team_number +
                       " url=" + telemetryUrl +
                       " result=" + webRequest.result +
                       " code=" + webRequest.responseCode +
                       " error=" + webRequest.error +
                       ". Check that TSSurl points at the TSS JSON server, not CAPCOM, and that tssTeamNumber matches an existing /json_data/teams/{team}/TELEMETRY.json path.");
        OnTSSConnectionResult?.Invoke(false);
    }

    private void CopyVitals(Vitals vital, EvaTelemetryDetails t)
    {
        vital.batt_time_left = t.batt_time_left;
        vital.oxy_pri_storage = t.oxy_pri_storage;
        vital.oxy_sec_storage = t.oxy_sec_storage;
        vital.oxy_pri_pressure = t.oxy_pri_pressure;
        vital.oxy_sec_pressure = t.oxy_sec_pressure;
        vital.oxy_time_left = t.oxy_time_left;
        vital.heart_rate = t.heart_rate;
        vital.oxy_consumption = t.oxy_consumption;
        vital.co2_production = t.co2_production;
        vital.suit_pressure_oxy = t.suit_pressure_oxy;
        vital.suit_pressure_co2 = t.suit_pressure_co2;
        vital.suit_pressure_other = t.suit_pressure_other;
        vital.suit_pressure_total = t.suit_pressure_total;
        vital.fan_pri_rpm = t.fan_pri_rpm;
        vital.fan_sec_rpm = t.fan_sec_rpm;
        vital.helmet_pressure_co2 = t.helmet_pressure_co2;
        vital.scrubber_a_co2_storage = t.scrubber_a_co2_storage;
        vital.scrubber_b_co2_storage = t.scrubber_b_co2_storage;
        vital.temperature = t.temperature;
        vital.coolant_m = t.coolant_m;
        vital.coolant_gas_pressure = t.coolant_gas_pressure;
        vital.coolant_liquid_pressure = t.coolant_liquid_pressure;
    }


    ////////////////////////////  COMMS  /////////////////////////////
    IEnumerator GetCOMMState()
    {
        using (UnityWebRequest webRequest = UnityWebRequest.Get(AstronautInstance.User.TSSurl + "/json_data/COMM.json"))
        {
            // Request and wait for the desired page.
            yield return webRequest.SendWebRequest();
            switch (webRequest.result)
            {
                case UnityWebRequest.Result.Success:
                    if (COMMJsonString != webRequest.downloadHandler.text)
                    {
                        COMMJsonString = webRequest.downloadHandler.text;

                        AstronautInstance.User.comm = JsonUtility.FromJson<COMM>(this.COMMJsonString);

                        // EventBus.Publish(new CommChanged(AstronautInstance.User.comm.comm));
                    }
                    break;
            }

        }
    }


    ////////////////////////////  IMU/GPS  /////////////////////////////
    IEnumerator GetIMUState()
    {
        using (UnityWebRequest webRequest = UnityWebRequest.Get(AstronautInstance.User.TSSurl + "/json_data/IMU.json"))
        {
            // Request and wait for the desired page.
            yield return webRequest.SendWebRequest();

            switch (webRequest.result)
            {
                case UnityWebRequest.Result.Success:
                    if (IMUJsonString != webRequest.downloadHandler.text)
                    {
                        IMUJsonString = webRequest.downloadHandler.text;

                        // Parse the IMU data
                        AstronautInstance.User.imu = JsonUtility.FromJson<IMU>(this.IMUJsonString);
                        float EV1_posX = (float)AstronautInstance.User.imu.imu.eva1.posx;
                        float EV1_posY = (float)AstronautInstance.User.imu.imu.eva1.posy;
                        float EV2_posX = (float)AstronautInstance.User.imu.imu.eva2.posx;
                        float EV2_posY = (float)AstronautInstance.User.imu.imu.eva2.posy;
                        // Check if this is the first IMU update -- should only enter condition once
                        if (!imuInitialized)
                        {
                            // If the IMU data is not (0, 0), initialize the minimap
                            if (EV1_posX != 0 || EV1_posY != 0)
                            {
                                imuInitialized = true;
                                if (AstronautInstance.User.id == 1)
                                {
                                    //AstronautInstance.User.origin.posX = EV1_posX;
                                    //AstronautInstance.User.origin.posY = EV1_posY;
                                }
                                else
                                {
                                    //AstronautInstance.User.origin.posX = EV2_posX;
                                    //AstronautInstance.User.origin.posY = EV2_posY;
                                }
                            }
                        }
                        if (AstronautInstance.User.id == 1)
                        {
                            Debug.Log("EV1: " + EV1_posX + " " + EV1_posY);
                            Debug.Log("EV2 " + EV2_posX + " " + EV2_posY);
                            Location newLocation = new Location(EV1_posX - AstronautInstance.User.origin.posX, 0, EV1_posY - AstronautInstance.User.origin.posZ, AstronautInstance.User.imu.imu.eva1.heading);
                            AstronautInstance.User.current = newLocation;
                            Location newEV2Location = new Location(EV2_posX - AstronautInstance.User.origin.posX, 0, EV2_posY - AstronautInstance.User.origin.posZ, AstronautInstance.User.imu.imu.eva2.heading);
                            EventBus.Publish(new EV2_LocationUpdatedEvent(newEV2Location));
                        }
                        else {
                            
                            Location newLocation = new Location(EV2_posX - AstronautInstance.User.origin.posX, 0, EV2_posY - AstronautInstance.User.origin.posZ, AstronautInstance.User.imu.imu.eva2.heading);
                            AstronautInstance.User.current = newLocation;
                            Location newEV2Location = new Location(EV1_posX - AstronautInstance.User.origin.posX, 0, EV1_posY - AstronautInstance.User.origin.posZ, AstronautInstance.User.imu.imu.eva1.heading);
                            EventBus.Publish(new EV2_LocationUpdatedEvent(newEV2Location));
                        }
                    }
                    break;
            }
        }
    }


    [Serializable]
    private class UdpTssPayload
    {
        public UdpTelemetry telemetry;
    }


    [Serializable]
    private class UdpTelemetry
    {
        public UdpEvaTelemetry eva1;
        public UdpEvaTelemetry eva2;
    }


    [Serializable]
    private class UdpEvaTelemetry
    {
        public double primary_battery_level;
        public double secondary_battery_level;
        public double battery_level;
        public double oxy_pri_storage;
        public double oxy_sec_storage;
        public double oxy_pri_pressure;
        public double oxy_sec_pressure;
        public double suit_pressure_oxy;
        public double suit_pressure_co2;
        public double suit_pressure_other;
        public double suit_pressure_total;
        public double helmet_pressure_co2;
        public double fan_pri_rpm;
        public double fan_sec_rpm;
        public double scrubber_a_co2_storage;
        public double scrubber_b_co2_storage;
        public double temperature;
        public double coolant_storage;
        public double coolant_gas_pressure;
        public double coolant_liquid_pressure;
        public double heart_rate;
        public double oxy_consumption;
        public double co2_production;
        public double eva_elapsed_time;
    }
}
