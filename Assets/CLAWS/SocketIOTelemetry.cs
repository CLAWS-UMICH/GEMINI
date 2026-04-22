using System;
using Newtonsoft.Json;
using SocketIO.Core;
using SocketIOClient;
using SocketIOClient.Transport;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine;

public class SocketIOTelemetry : MonoBehaviour
{
    [Header("Connection")]
    [Tooltip("Socket.IO server URL (e.g., http://localhost:5001)")]
    public string serverUrl = "http://localhost:5001";

    [Header("Task Emit")]
    [Tooltip("How often to emit the 'task' payload (seconds).")]
    public float taskEmitIntervalSeconds = 1.0f;

    [Tooltip("1D 5-box task array payload sent to backend 'task' event.")]
    public string[] taskPayload = new string[5] { "box1", "box2", "box3", "box4", "box5" };

    private SocketIOClient.SocketIO socket;
    private EvaTelemetryMessage currentEvaData;
    private RoverTelemetryMessage currentRoverData;
    private CancellationTokenSource taskEmitCts;

    // events
    public event Action<EvaTelemetryMessage> OnEvaTelemetryReceived;
    public event Action<RoverTelemetryMessage> OnRoverTelemetryReceived;

    void Start()
    {
        Connect();
        StartTaskEmitLoop();
        Debug.Log("[Socket] Start called");
    }

    void OnDestroy()
    {
        StopTaskEmitLoop();
        Disconnect();
    }

    void OnApplicationQuit()
    {
        StopTaskEmitLoop();
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
                ReconnectionAttempts = 5,
                EIO = EngineIO.V4,
                Transport = SocketIOClient.Transport.TransportProtocol.WebSocket
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
                    Debug.Log($"[SocketIO] Raw EVA telemetry: {response}");

                    currentEvaData = response.GetValue<EvaTelemetryMessage>();

                    if (currentEvaData != null && currentEvaData.telemetry != null)
                    {
                        OnEvaTelemetryReceived?.Invoke(currentEvaData);
                        var eva1 = currentEvaData.telemetry.eva1;
                        var eva2 = currentEvaData.telemetry.eva2;
                        Debug.Log(
                            $"[SocketIO] EVA telemetry @ {currentEvaData.local_timestamp} | " +
                            $"EVA1 HR: {eva1.heart_rate}, O2: {eva1.oxy_pri_storage}/{eva1.oxy_sec_storage}, Temp: {eva1.temperature} | " +
                            $"EVA2 HR: {eva2.heart_rate}, O2: {eva2.oxy_pri_storage}/{eva2.oxy_sec_storage}, Temp: {eva2.temperature}"
                        );
                    }
                    else
                    {
                        Debug.LogWarning("[SocketIO] EVA telemetry payload was null or malformed");
                    }
                }
                catch (Exception ex)
                {
                    Debug.LogError($"[SocketIO] EVA parse error: {ex.Message}\nRaw: {response}");
                }
            });

            socket.On("rover-telemetry", response =>
            {
                try
                {
                    Debug.Log($"[SocketIO] Raw rover telemetry: {response}");

                    currentRoverData = response.GetValue<RoverTelemetryMessage>();

                    if (currentRoverData != null && currentRoverData.pr_telemetry != null)
                    {
                        OnRoverTelemetryReceived?.Invoke(currentRoverData);
                        var rover = currentRoverData.pr_telemetry;
                        Debug.Log(
                            $"[SocketIO] Rover telemetry @ {currentRoverData.local_timestamp} | " +
                            $"Pos: ({rover.rover_pos_x}, {rover.rover_pos_y}, {rover.rover_pos_z}), Speed: {rover.speed}, " +
                            $"Heading: {rover.heading}, Battery: {rover.battery_level}, O2 Tank: {rover.oxygen_tank}"
                        );
                    }
                    else
                    {
                        Debug.LogWarning("[SocketIO] Rover telemetry payload was null or malformed");
                    }
                }
                catch (Exception ex)
                {
                    Debug.LogError($"[SocketIO] Rover parse error: {ex.Message}\nRaw: {response}");
                }
            });



            socket.On("error", response =>
            {
                var errorData = response.GetValue<ErrorData>();
                Debug.LogError($"[SocketIO] Error: {errorData.error}");
            });

            await socket.ConnectAsync();
        }
        catch (Exception ex)
        {
            Debug.LogError($"[SocketIO] Connection error: {ex.Message}");
        }
    }

    private bool isDisconnecting = false;

    private void StartTaskEmitLoop()
    {
        StopTaskEmitLoop();
        taskEmitCts = new CancellationTokenSource();
        _ = TaskEmitLoopAsync(taskEmitCts.Token);
    }

    private void StopTaskEmitLoop()
    {
        if (taskEmitCts == null) return;
        taskEmitCts.Cancel();
        taskEmitCts.Dispose();
        taskEmitCts = null;
    }

    private async Task TaskEmitLoopAsync(CancellationToken cancellationToken)
    {
        try
        {
            while (!cancellationToken.IsCancellationRequested)
            {
                try
                {
                    if (socket != null && socket.Connected)
                    {
                        string[] payload = BuildTaskPayload();
                        await socket.EmitAsync("task", payload);
                        Debug.Log($"[SocketIO] Emitted task payload: {JsonConvert.SerializeObject(payload)}");
                    }
                }
                catch (Exception ex)
                {
                    Debug.LogWarning($"[SocketIO] Task emit warning: {ex.Message}");
                }

                int delayMs = Mathf.Max(100, Mathf.RoundToInt(taskEmitIntervalSeconds * 1000f));
                await Task.Delay(delayMs, cancellationToken);
            }
        }
        catch (OperationCanceledException)
        {
            // expected during shutdown
        }
    }

    private string[] BuildTaskPayload()
    {
        string[] payload = new string[5] { "", "", "", "", "" };

        if (taskPayload == null)
        {
            return payload;
        }

        int copyCount = Mathf.Min(5, taskPayload.Length);
        for (int i = 0; i < copyCount; i++)
        {
            payload[i] = taskPayload[i] ?? "";
        }

        return payload;
    }

    private async void Disconnect()
    {
        if (isDisconnecting) return;
        isDisconnecting = true;

        var s = socket;
        socket = null;

        if (s != null)
        {
            try
            {
                await s.DisconnectAsync();
                s.Dispose();
            }
            catch (Exception ex)
            {
                Debug.LogWarning($"[SocketIO] Disconnect warning: {ex.Message}");
            }
        }

        isDisconnecting = false;
    }

    public EvaTelemetryMessage GetCurrentEvaData()
    {
        return currentEvaData;
    }

    public RoverTelemetryMessage GetCurrentRoverData()
    {
        return currentRoverData;
    }
}

[Serializable]
public class EvaTelemetryMessage
{
    public TelemetryInfo telemetry;
    public string local_timestamp;
}

[Serializable]
public class TelemetryInfo
{
    public EvaDatas eva1;
    public EvaDatas eva2;
}

[Serializable]
public class EvaDatas
{
    public float batt_time_left;
    public float oxy_pri_storage;
    public float oxy_sec_storage;
    public float oxy_pri_pressure;
    public float oxy_sec_pressure;
    public float oxy_time_left;
    public float heart_rate;
    public float oxy_consumption;
    public float co2_production;
    public float suit_pressure_oxy;
    public float suit_pressure_co2;
    public float suit_pressure_other;
    public float suit_pressure_total;
    public float fan_pri_rpm;
    public float fan_sec_rpm;
    public float helmet_pressure_co2;
    public float scrubber_a_co2_storage;
    public float scrubber_b_co2_storage;
    public float temperature;
    public float coolant_storage;
    public float coolant_gas_pressure;
    public float coolant_liquid_pressure;
}

[Serializable]
public class RoverTelemetryMessage
{
    public RoverTelemetry pr_telemetry;
    public string local_timestamp;
}

[Serializable]
public class RoverTelemetry
{
    public bool cabin_heating;
    public bool cabin_cooling;
    public bool lights_on;
    public bool brakes;
    public float throttle;
    public float steering;
    public float rover_pos_x;
    public float rover_pos_y;
    public float rover_pos_z;
    public float heading;
    public float pitch;
    public float roll;
    public float distance_traveled;
    public float speed;
    public float sunlight;
    public float surface_incline;
    public float[] lidar;
    public float oxygen_storage;
    public float oxygen_pressure;
    public float cabin_pressure;
    public float cabin_temperature;
    public float external_temp;
    public float coolant_pressure;
    public float coolant_storage;
    public float primary_battery_level;
    public float secondary_battery_level;
    public float rover_elapsed_time;
    public bool sim_running;
    public bool dust_connected;
    public float distance_from_base;
    public float oxygen_tank;
    public float battery_level;
    public float fan_pri_rpm;
    public float fan_sec_rpm;
    public float scrubber_a_co2_storage;
    public float scrubber_b_co2_storage;
    public float cabin_temperature_target;
}

[Serializable]
public class ErrorData
{
    public string error;
    public string local_timestamp;
}

