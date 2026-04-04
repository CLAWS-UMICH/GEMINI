using UnityEngine;
using TMPro;
using System;
using System.Net;
using System.Net.Sockets;
using System.Threading;
using System.Collections.Concurrent;
using System.Text;

// 1. The Nested UIA Class
// This matches the exact keys inside the "uia": { ... } block
[Serializable]
public class UiaData
{
    public bool eva1_power;
    public bool eva1_oxy;
    public bool eva1_water_supply;
    public bool eva1_water_waste;
    public bool eva2_power;
    public bool eva2_oxy;
    public bool eva2_water_supply;
    public bool eva2_water_waste;
    public bool oxy_vent;
    public bool depress;
}

// 2. The Root Class
// This catches the whole JSON file, but only extracts the "uia" part
[Serializable]
public class EvaRootData
{
    public UiaData uia;
}

public class EVATelemetryClient : MonoBehaviour
{
    [Header("TSS Server Settings")]
    public string serverIP = "127.0.0.1";
    public int serverPort = 8080;
    
    [Header("Telemetry Command")]
    [Tooltip("0 = ROVER, 1 = EVA, 2 = LTV, 3 = LTV_ERRORS")]
    public uint commandNumber = 1; // CHANGED TO 1 FOR EVA.JSON

    [Header("UI References")]
    public TextMeshProUGUI heartRateDisplay;
    public TextMeshProUGUI oxygenDisplay;

    private UdpClient udpClient;
    private Thread clientThread;
    private bool isRunning = false;
    
    // Change it to queue the root data object
    private ConcurrentQueue<EvaRootData> uiaDataQueue = new ConcurrentQueue<EvaRootData>();

    void Start()
    {
        isRunning = true;
        clientThread = new Thread(CommunicateWithTSS);
        clientThread.IsBackground = true;
        clientThread.Start();
    }

    private void CommunicateWithTSS()
    {
        udpClient = new UdpClient();
        IPEndPoint serverEndpoint = new IPEndPoint(IPAddress.Parse(serverIP), serverPort);

        while (isRunning)
        {
            try
            {
                uint timestamp = (uint)DateTimeOffset.UtcNow.ToUnixTimeSeconds();
                byte[] timeBytes = BitConverter.GetBytes(timestamp);
                byte[] cmdBytes = BitConverter.GetBytes(commandNumber);

                if (BitConverter.IsLittleEndian)
                {
                    Array.Reverse(timeBytes);
                    Array.Reverse(cmdBytes);
                }

                byte[] requestPacket = new byte[8];
                Buffer.BlockCopy(timeBytes, 0, requestPacket, 0, 4);
                Buffer.BlockCopy(cmdBytes, 0, requestPacket, 4, 4);

                udpClient.Send(requestPacket, requestPacket.Length, serverEndpoint);

                IPEndPoint remoteEndpoint = new IPEndPoint(IPAddress.Any, 0);
                byte[] responseBytes = udpClient.Receive(ref remoteEndpoint);
                string responseText = Encoding.UTF8.GetString(responseBytes);

                // When you receive the string, parse it into the Root class
                int jsonStartIndex = responseText.IndexOf('{');
                if (jsonStartIndex >= 0)
                {
                    string cleanJson = responseText.Substring(jsonStartIndex);
                    
                    // Parse into EvaRootData instead of UiaTelemetryData
                    EvaRootData parsedData = JsonUtility.FromJson<EvaRootData>(cleanJson);
                    
                    // Check if it successfully found the uia block
                    if (parsedData != null && parsedData.uia != null)
                    {
                        uiaDataQueue.Enqueue(parsedData);
                    }
                }

                Thread.Sleep(1000); // 1-second polling interval
            }
            catch (Exception e)
            {
                Debug.LogWarning("UDP Communication Error: " + e.Message);
                Thread.Sleep(1000); 
            }
        }
    }

    void Update()
    {
        // Pull the root object from the queue
        while (uiaDataQueue.TryDequeue(out EvaRootData currentData))
        {
            if (uiaPowerDisplay != null)
            {
                // Access the variables using currentData.uia.[variable_name]
                string powerState = currentData.uia.eva1_power ? "ON" : "OFF";
                uiaPowerDisplay.text = "EVA1 Power: " + powerState;
                uiaPowerDisplay.color = currentData.uia.eva1_power ? Color.green : Color.red;
            }
            
            if (uiaOxygenDisplay != null)
            {
                string o2State = currentData.uia.eva1_oxy ? "FLOWING" : "CLOSED";
                uiaOxygenDisplay.text = "EVA1 O2: " + o2State;
            }
        }
    }

    void OnApplicationQuit()
    {
        isRunning = false;
        if (udpClient != null) udpClient.Close();
        if (clientThread != null && clientThread.IsAlive) clientThread.Abort();
    }
}