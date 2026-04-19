using System;
using UnityEngine;
using SocketIOClient;
using Newtonsoft.Json;

public class SocketIOTelemetryClient : MonoBehaviour
{
    [Header("Connection")]
    [Tooltip("Socket.IO server URL (e.g., http://localhost:5001)")]
    public string serverUrl = "http://localhost:5001";

    private SocketIOClient.SocketIO socket;
    private TelemetryData currentData;

    public event Action<TelemetryData> OnTelemetryReceived;

    void Start()
    {
        Connect();
    }

    void OnDestroy()
    {
        Disconnect();
    }

    void OnApplicationQuit()
    {
        Disconnect();
    }

    private async void Connect()
    {
        try
        {
            socket = new SocketIOClient.SocketIO(serverUrl, new SocketIOOptions
            {
                Reconnection = true,
                ReconnectionDelay = 1000,
                ReconnectionAttempts = 5
            });

            socket.OnConnected += (sender, e) =>
            {
                Debug.Log("[SocketIO] Connected");
            };

            socket.OnDisconnected += (sender, e) =>
            {
                Debug.Log("[SocketIO] Disconnected");
            };

            socket.On("eva-telemetry", response =>
            {
                try
                {
                    string json = response.GetValue<string>();
                    currentData = JsonConvert.DeserializeObject<TelemetryData>(json);

                    if (currentData?.telemetry != null)
                    {
                        OnTelemetryReceived?.Invoke(currentData);
                        var e1 = currentData.telemetry.eva1;
                        var e2 = currentData.telemetry.eva2;
                        Debug.Log(
                            $"[SocketIO] eva-telemetry eva1 elapsed={e1?.eva_elapsed_time ?? -1f} eva2 elapsed={e2?.eva_elapsed_time ?? -1f}");
                    }
                }
                catch (Exception ex)
                {
                    Debug.LogError($"[SocketIO] Parse error: {ex.Message}");
                }
            });

            socket.On("error", response =>
            {
                try
                {
                    var errorData = response.GetValue<ErrorData>();
                    if (errorData != null)
                        Debug.LogError($"[SocketIO] Error: {errorData.error}");
                    else
                        Debug.LogError("[SocketIO] Error (no payload)");
                }
                catch (Exception ex)
                {
                    Debug.LogError($"[SocketIO] Error event parse: {ex.Message}");
                }
            });

            await socket.ConnectAsync();
        }
        catch (Exception ex)
        {
            Debug.LogError($"[SocketIO] Connection error: {ex.Message}");
        }
    }

    private async void Disconnect()
    {
        if (socket != null)
        {
            await socket.DisconnectAsync();
            socket.Dispose();
            socket = null;
        }
    }

    public async void SendPingToServer()
    {
        if(socket != null && socket.Connected)
        {
            await socket.EmitAsync("unity-ping", "Hello server, Unity is here!");
            Debug.Log("[SocketIO] Sent ping to server");
        }
    }

    public async void SendPositionData(Vector3 playerPosition)
    {
        if (socket != null && socket.Connected)
        {
            var positionData = new
            {
                x = playerPosition.x,
                y = playerPosition.y,
                z = playerPosition.z
            };
            await socket.EmitAsync("player-moved", positionData);
        }
    }

    public TelemetryData GetCurrentData()
    {
        return currentData;
    }
}

[Serializable]
public class TelemetryData
{
    public TelemetryInfo telemetry;
    public StatusData status;
    public DcuData dcu;
    public EvaTelemetryError error;
    public ImuData imu;
    public UiaDataWeb uia;
    public string local_timestamp;
}

[Serializable]
public class TelemetryInfo
{
    public EvaDataWeb eva1;
    public EvaDataWeb eva2;
}

[Serializable]
public class EvaDataWeb
{
    public float primary_battery_level;
    public float secondary_battery_level;
    public float battery_level;
    public float oxy_pri_storage;
    public float oxy_sec_storage;
    public float oxy_pri_pressure;
    public float oxy_sec_pressure;
    public float suit_pressure_oxy;
    public float suit_pressure_co2;
    public float suit_pressure_other;
    public float suit_pressure_total;
    public float helmet_pressure_co2;
    public float fan_pri_rpm;
    public float fan_sec_rpm;
    public float scrubber_a_co2_storage;
    public float scrubber_b_co2_storage;
    public float temperature;
    public float coolant_storage;
    public float coolant_gas_pressure;
    public float coolant_liquid_pressure;
    public float heart_rate;
    public float oxy_consumption;
    public float co2_production;
    public float eva_elapsed_time;
}

[Serializable]
public class StatusData
{
    public bool started;
}

[Serializable]
public class DcuData
{
    public DcuEva1 eva1;
    public DcuEva2 eva2;
}

[Serializable]
public class DcuEva1
{
    public bool oxy;
    public bool fan;
    public bool pump;
    public bool co2;
    public DcuEva1Batt batt;
}

[Serializable]
public class DcuEva1Batt
{
    public bool lu;
    public bool ps;
}

[Serializable]
public class DcuEva2
{
    public bool batt;
    public bool oxy;
    public bool comm;
    public bool fan;
    public bool pump;
    public bool co2;
}

[Serializable]
public class EvaTelemetryError
{
    public bool fan_error;
    public bool oxy_error;
    public bool power_error;
    public bool scrubber_error;
}

[Serializable]
public class ImuData
{
    public ImuEva eva1;
    public ImuEva eva2;
}

[Serializable]
public class ImuEva
{
    public float posx;
    public float posy;
    public float heading;
}

[Serializable]
public class UiaDataWeb
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

[Serializable]
public class ErrorData
{
    public string error;
    public string local_timestamp;
}