using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Networking;
using UnityEngine.UI;
using System;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;

public class TSSConnection : MonoBehaviour
{
    ////////////////////////////  CONFIG  /////////////////////////////
    [SerializeField] private GameObject minimap;
    [SerializeField] private int tssPort = 14141;
    [SerializeField] private bool pollRoverPosition = true;
    [SerializeField] private bool pollLtvLocation = true;
    [SerializeField] private bool pollLtvErrors = true;
    [SerializeField] private bool logLtvErrorsParseDiagnostics;
    [SerializeField] private float ermClearPollMaxSeconds = 25f;
    [SerializeField] private float ermClearPollIntervalSeconds = 0.2f;

    /// <summary>GET 3 interval while any LTV error still has needs_resolved (keeps task list in sync until all cleared).</summary>
    [SerializeField] private float ltvErrorsPollWhileUnresolvedSeconds = 1f;

    private string IPaddr;
    private string tssHost;
    bool connected;
    float time_since_last_update;
    float time_since_last_optional_update;
    public Action<bool> OnTSSConnectionResult;
    private bool imuInitialized = false;
    private bool evaPollInFlight = false;
    private bool optionalPollInFlight = false;
    private bool telemetryErrorLogged = false;
    private float lastOptionalPayloadWarningTime = -100f;
    private float timeSinceLtvUnresolvedPoll;
    private bool ltvUnresolvedPollInFlight;

    private const int UdpRoverCommand = 0;
    private const int UdpEvaCommand = 1;
    private const int UdpLtvCommand = 2;
    private const int UdpLtvErrorsCommand = 3;
    private const int UdpTimeoutMs = 2000;
    private const float EvaPollIntervalSeconds = 1.0f;
    private const float OptionalPollIntervalSeconds = 5.0f;
    private const float OptionalPayloadWarningIntervalSeconds = 10f;

    /// <summary>
    /// Serialize UDP GET command 3 so optional polling and post-POST refreshes cannot apply out-of-order
    /// responses (a stale snapshot would e.g. bring back ERM 4800 after it was cleared on the server).
    /// </summary>
    private readonly object ltvErrorsUdpSync = new object();

    /// <summary>After any LTV mutation, poll GET 3 at least this many times (spaced) so dependency updates can land.</summary>
    private const int MinLtvErrorsPollsAfterMutation = 3;

    private const int MaxLtvErrorsMutationPollAttempts = 24;
    private const float LtvErrorsMutationPollDelaySeconds = 0.05f;

    /// <summary>Set after ERM POST (index 0, needs_resolved false) until full LTV_ERRORS GET 3 is applied.</summary>
    private bool ermClearPostPending;

    ////////////////////////////  ROVER / LTV CACHE  /////////////////////////////
    private Vector3 latestRoverPosition;
    private bool hasRoverPosition;
    private Vector2 latestLtvLocation;
    private bool hasLtvLocation;
    private LtvErrorProcedure[] latestLtvErrorProcedures = EmptyLtvErrorProcedures;
    private bool hasLtvErrorProcedures;

    private static readonly LtvErrorProcedure[] EmptyLtvErrorProcedures = new LtvErrorProcedure[0];

    public bool HasRoverPosition => hasRoverPosition;
    public Vector3 LatestRoverPosition => latestRoverPosition;
    public bool HasLtvLocation => hasLtvLocation;
    public Vector2 LatestLtvLocation => latestLtvLocation;
    public bool HasLtvErrorProcedures => hasLtvErrorProcedures;
    public LtvErrorProcedure[] LatestLtvErrorProcedures => latestLtvErrorProcedures ?? EmptyLtvErrorProcedures;


    ////////////////////////////  CACHED PAYLOADS  /////////////////////////////
    // Cached payloads for change detection and downstream reads.
    string UIAJsonString;
    string ErrorJsonString;
    string ROVERJsonString;
    string TELEMETRYJsonString;
    string IMUJsonString;
    string LTVJsonString;
    string LTVErrorsJsonString;


    ////////////////////////////  CONNECTION  /////////////////////////////
    // Connect to TSS
    public void ConnectToHost(string IP_host, int _team_number)
    {
        DisconnectFromHost();
        tssHost = IP_host;
        AstronautInstance.User.TSSurl = "http://" + IP_host + ":" + tssPort;
        EnsureLocalAstronautEvaSlot();
        Debug.Log("Connecting to TSS2026 UDP telemetry at: " + tssHost + ":" + tssPort + " (EV1 / eva1 telemetry)");
        StartCoroutine(FetchEvaPayload(true));
    }


    /// <summary>
    /// GEMINI targets EV1 only: always use TSS telemetry.eva1 for vitals and UI.
    /// </summary>
    private void EnsureLocalAstronautEvaSlot()
    {
        if (AstronautInstance.User.id != 1)
        {
            Debug.LogWarning("[TSS] Astronaut id was " + AstronautInstance.User.id +
                             "; forcing EV1 (id=1) for TSS telemetry mapping.");
            AstronautInstance.User.id = 1;
        }
    }

    public void LookForConnection()
    {
        if (!connected && !string.IsNullOrEmpty(IPaddr) && !IPaddr.Contains("/"))
        {
            ConnectToHost(IPaddr, 0);
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
        evaPollInFlight = false;
        optionalPollInFlight = false;
        timeSinceLtvUnresolvedPoll = 0f;
        ltvUnresolvedPollInFlight = false;
    }


    void Start()
    {
        connected = false;
    }


    void Update()
    {
        // If you are connected to TSS
        if (connected)
        {
            // Each Second
            time_since_last_update += Time.deltaTime;
            if (time_since_last_update > EvaPollIntervalSeconds)
            {
                StartCoroutine(FetchEvaPayload(false));
                time_since_last_update = 0.0f;
            }

            time_since_last_optional_update += Time.deltaTime;
            if (time_since_last_optional_update > OptionalPollIntervalSeconds)
            {
                StartCoroutine(FetchOptionalPayloads());
                time_since_last_optional_update = 0.0f;
            }

            if (pollLtvErrors)
                TickLtvErrorsPollWhileUnresolved(Time.deltaTime);
        }
    }

    private void TickLtvErrorsPollWhileUnresolved(float deltaTime)
    {
        if (!connected || !pollLtvErrors || ltvUnresolvedPollInFlight)
            return;

        if (!LtvErrorTaskSupport.ShouldKeepPollingLtvErrors(latestLtvErrorProcedures))
        {
            timeSinceLtvUnresolvedPoll = 0f;
            return;
        }

        timeSinceLtvUnresolvedPoll += deltaTime;
        if (timeSinceLtvUnresolvedPoll < ltvErrorsPollWhileUnresolvedSeconds)
            return;

        timeSinceLtvUnresolvedPoll = 0f;
        StartCoroutine(LtvErrorsFastPollTick());
    }

    private IEnumerator LtvErrorsFastPollTick()
    {
        ltvUnresolvedPollInFlight = true;
        yield return RefreshLtvErrorsOnce();
        ltvUnresolvedPollInFlight = false;
    }


    ////////////////////////////  CACHED READ ACCESS  /////////////////////////////
    public bool TryGetRoverPosition(out Vector3 roverPosition)
    {
        roverPosition = latestRoverPosition;
        return hasRoverPosition;
    }


    public bool TryGetLtvLocation(out Vector2 ltvLocation)
    {
        ltvLocation = latestLtvLocation;
        return hasLtvLocation;
    }


    public bool TryGetLtvErrorProcedures(out LtvErrorProcedure[] procedures)
    {
        procedures = LatestLtvErrorProcedures;
        return hasLtvErrorProcedures;
    }


    public bool TryGetActiveLtvErrorProcedures(out LtvErrorProcedure[] active)
    {
        active = LtvErrorTaskSupport.FilterActive(latestLtvErrorProcedures).ToArray();
        return hasLtvErrorProcedures;
    }


    ////////////////////////////  EVA POLLING (COMMAND 1)  /////////////////////////////
    private IEnumerator FetchEvaPayload(bool connectionAttempt)
    {
        if (evaPollInFlight)
            yield break;

        evaPollInFlight = true;

        // UDP command 1 — EVA.json (required)
        CommandFetchResult evaResult = new CommandFetchResult(UdpEvaCommand, "EVA.json");
        yield return FetchCommandJson(evaResult);

        if (!evaResult.Success)
        {
            evaPollInFlight = false;
            HandleRequiredPayloadFailure(connectionAttempt, evaResult.ErrorMessage);
            yield break;
        }

        if (!ApplyEvaJson(evaResult.Json, connectionAttempt))
        {
            evaPollInFlight = false;
            HandleRequiredPayloadFailure(connectionAttempt, "EVA.json was empty or missing telemetry.eva1/eva2.");
            yield break;
        }

        evaPollInFlight = false;
        telemetryErrorLogged = false;
        if (connectionAttempt)
        {
            connected = true;
            OnTSSConnectionResult?.Invoke(true);
            Debug.Log("[TSS] TSS2026 UDP connected: " + tssHost + ":" + tssPort);
            if (pollLtvErrors)
                StartCoroutine(RefreshLtvErrorsOnce());
        }
    }


    ////////////////////////////  OPTIONAL POLLING (COMMANDS 0, 2, 3)  /////////////////////////////
    private IEnumerator FetchOptionalPayloads()
    {
        if (optionalPollInFlight)
            yield break;

        optionalPollInFlight = true;

        // UDP command 0 — ROVER.json (optional: position only)
        if (pollRoverPosition)
            yield return FetchOptionalPayload(UdpRoverCommand, "ROVER.json", ApplyRoverJson);

        // UDP command 2 — LTV.json (optional: last known location)
        if (pollLtvLocation)
            yield return FetchOptionalPayload(UdpLtvCommand, "LTV.json", ApplyLtvJson);

        // UDP command 3 — LTV_ERRORS.json (optional: task-board procedures)
        if (pollLtvErrors)
            yield return FetchOptionalPayload(UdpLtvErrorsCommand, "LTV_ERRORS.json", ApplyLtvErrorsJson);

        optionalPollInFlight = false;
    }


    ////////////////////////////  UDP TRANSPORT  /////////////////////////////
    private IEnumerator FetchOptionalPayload(int command, string label, Func<string, bool> applyJson)
    {
        CommandFetchResult result = new CommandFetchResult(command, label);
        yield return FetchCommandJson(result);

        if (!result.Success)
        {
            LogOptionalPayloadFailure(label, result.ErrorMessage);
            yield break;
        }

        if (!applyJson(result.Json))
        {
            LogOptionalPayloadFailure(label, label + " was empty or did not match the expected TSS2026 schema.");
        }
    }


    private IEnumerator FetchCommandJson(CommandFetchResult result)
    {
        if (result.Command == UdpLtvErrorsCommand)
        {
            Task<string> httpTask = Task.Run(async () => {
                using (var client = new System.Net.Http.HttpClient()) {
                    client.Timeout = TimeSpan.FromSeconds(3);
                    return await client.GetStringAsync("http://" + tssHost + ":" + tssPort + "/data/LTV_ERRORS.json");
                }
            });

            yield return new WaitUntil(() => httpTask.IsCompleted);

            if (httpTask.IsFaulted || httpTask.IsCanceled)
            {
                Exception error = httpTask.Exception?.GetBaseException();
                result.Fail(error != null ? error.Message : "HTTP request failed.");
            }
            else
            {
                result.Succeed(httpTask.Result);
            }
            yield break;
        }

        Task<string> fetchTask = FetchUdpJsonAsync(result.Command);
        yield return new WaitUntil(() => fetchTask.IsCompleted);

        if (fetchTask.IsFaulted || fetchTask.IsCanceled)
        {
            Exception error = fetchTask.Exception?.GetBaseException();
            result.Fail(error != null ? error.Message : "UDP request was canceled.");
            yield break;
        }

        result.Succeed(fetchTask.Result);
    }


    private Task<string> FetchUdpJsonAsync(int command)
    {
        string host = tssHost;
        int port = tssPort;
        return Task.Run(() =>
        {
            if (command == UdpLtvErrorsCommand)
            {
                lock (ltvErrorsUdpSync)
                {
                    return FetchUdpJsonStringInner(host, port, command);
                }
            }

            return FetchUdpJsonStringInner(host, port, command);
        });
    }

    private string FetchUdpJsonStringInner(string host, int port, int command)
    {
        using (UdpClient client = new UdpClient())
        {
            client.Client.ReceiveBufferSize = 65536;
            client.Client.ReceiveTimeout = UdpTimeoutMs;
            byte[] request = BuildUdpCommandPacket(command);
            client.Send(request, request.Length, host, port);
            IPEndPoint remoteEndPoint = new IPEndPoint(IPAddress.Any, 0);
            byte[] response = client.Receive(ref remoteEndPoint);
            return ExtractJsonPayload(response);
        }
    }


    private byte[] BuildUdpCommandPacket(int command)
    {
        byte[] packet = new byte[8];
        int unixTime = (int)(DateTime.UtcNow - new DateTime(1970, 1, 1, 0, 0, 0, DateTimeKind.Utc)).TotalSeconds;
        Buffer.BlockCopy(BitConverter.GetBytes(IPAddress.HostToNetworkOrder(unixTime)), 0, packet, 0, 4);
        Buffer.BlockCopy(BitConverter.GetBytes(IPAddress.HostToNetworkOrder(command)), 0, packet, 4, 4);
        return packet;
    }

    /// <summary>12-byte UDP packet: time (BE), command (BE), float payload (BE). Used for TSS POST commands (e.g. LTV error needs_resolved).</summary>
    private byte[] BuildUdpPostPacket(int command, float payload)
    {
        byte[] packet = new byte[12];
        int unixTime = (int)(DateTime.UtcNow - new DateTime(1970, 1, 1, 0, 0, 0, DateTimeKind.Utc)).TotalSeconds;
        Buffer.BlockCopy(BitConverter.GetBytes(IPAddress.HostToNetworkOrder(unixTime)), 0, packet, 0, 4);
        Buffer.BlockCopy(BitConverter.GetBytes(IPAddress.HostToNetworkOrder(command)), 0, packet, 4, 4);
        byte[] floatBytes = BitConverter.GetBytes(payload);
        if (BitConverter.IsLittleEndian)
            Array.Reverse(floatBytes);
        Buffer.BlockCopy(floatBytes, 0, packet, 8, 4);
        return packet;
    }

    /// <summary>
    /// Notify TSS2026 that <c>ltv_errors.error_procedures[i].needs_resolved</c> should be set (UDP command 2023+i, bool as float).
    /// Server-side <c>update_ltv_error_dependencies</c> runs on the simulation tick; if EVA/sim is paused, dependency changes may lag until the server advances.
    /// We poll UDP GET 3 repeatedly after a successful POST so the UI tracks the latest <c>needs_resolved</c> flags and new errors that appear as others are cleared.
    /// </summary>
    public IEnumerator PostLtvProcedureNeedsResolved(int procedureIndex, bool needsResolved)
    {
        if (procedureIndex < 0 || procedureIndex > LtvErrorTaskSupport.MaxLtvProcedureIndex)
        {
            Debug.LogWarning("[TSS] LTV procedure index out of range: " + procedureIndex);
            yield break;
        }

        if (string.IsNullOrEmpty(tssHost))
        {
            Debug.LogWarning("[TSS] Cannot POST LTV resolution: host not set (connect to TSS first).");
            yield break;
        }

        if (!LtvErrorTaskSupport.TryGetUdpCommandForProcedureIndex(procedureIndex, out int command))
        {
            Debug.LogWarning("[TSS] Could not resolve UDP command for LTV procedure index " + procedureIndex);
            yield break;
        }

        float payload = needsResolved ? 1f : 0f;
        Task<bool> postTask = SendUdpPostAsync(command, payload);
        yield return new WaitUntil(() => postTask.IsCompleted);

        if (postTask.IsFaulted)
        {
            Exception ex = postTask.Exception?.GetBaseException();
            Debug.LogWarning("[TSS] LTV UDP POST exception: " + (ex != null ? ex.Message : "unknown"));
            yield break;
        }

        if (!postTask.Result)
        {
            Debug.LogWarning("[TSS] LTV UDP POST rejected or failed (command=" + command +
                             ", needsResolved=" + needsResolved + ").");
            yield break;
        }

        Debug.Log("[TSS] LTV procedure index " + procedureIndex + " needs_resolved=" + needsResolved + " sent (command=" + command + ").");

        bool clearingErm = procedureIndex == 0 && !needsResolved;
        if (clearingErm)
            ermClearPostPending = true;

        PatchLtvProcedureNeedsResolvedInCache(procedureIndex, needsResolved);
        PublishLtvErrorsFromCache();

        yield return RefreshLtvErrorsAfterMutation(procedureIndex, needsResolved);

        if (clearingErm)
            ermClearPostPending = false;
    }

    private IEnumerator RefreshLtvErrorsOnce()
    {
        yield return FetchAndApplyLtvErrorsJson();
    }

    /// <summary>
    /// Poll LTV_ERRORS (GET 3) until we are past the recovery-only single-entry snapshot (after ERM clears),
    /// and at least <see cref="MinLtvErrorsPollsAfterMutation"/> times so dependency-driven procedures can appear.
    /// </summary>
    private IEnumerator RefreshLtvErrorsAfterMutation(int resolvedProcedureIndex, bool needsResolvedValueWritten)
    {
        bool clearedErm =
            resolvedProcedureIndex == 0 && !needsResolvedValueWritten;

        if (clearedErm)
        {
            float deadline = Time.realtimeSinceStartup + ermClearPollMaxSeconds;
            int attempt = 0;

            while (Time.realtimeSinceStartup < deadline)
            {
                attempt++;
                yield return FetchAndApplyLtvErrorsJson();

                bool ermStillActive = LtvErrorTaskSupport.IsRecoveryModeActive(latestLtvErrorProcedures);
                bool stillRecoveryOnly = LtvErrorTaskSupport.IsRecoveryOnlyUdpSnapshot(latestLtvErrorProcedures);

                if (!ermStillActive && LtvErrorTaskSupport.HasFullLtvErrorsSnapshot(latestLtvErrorProcedures))
                    break;

                yield return new WaitForSecondsRealtime(ermClearPollIntervalSeconds);
            }

            if (LtvErrorTaskSupport.IsRecoveryOnlyUdpSnapshot(latestLtvErrorProcedures))
            {
                Debug.LogWarning("[TSS] LTV_ERRORS after ERM clear: still recovery-only after " + attempt +
                                 " polls over " + ermClearPollMaxSeconds + "s (total_procedures=" +
                                 latestLtvErrorProcedures.Length + "); downstream errors may lag until next GET 3.");
            }
        }
        else
        {
            for (int attempt = 1; attempt <= MaxLtvErrorsMutationPollAttempts; attempt++)
            {
                yield return FetchAndApplyLtvErrorsJson();

                if (attempt >= MinLtvErrorsPollsAfterMutation)
                    break;

                yield return new WaitForSecondsRealtime(LtvErrorsMutationPollDelaySeconds);
            }
        }
    }

    private IEnumerator FetchAndApplyLtvErrorsJson()
    {
        CommandFetchResult result = new CommandFetchResult(UdpLtvErrorsCommand, "LTV_ERRORS.json");
        yield return FetchCommandJson(result);

        if (!result.Success)
        {
            LogOptionalPayloadFailure("LTV_ERRORS.json", result.ErrorMessage);
            yield break;
        }

        if (!ApplyLtvErrorsJson(result.Json))
        {
            LogOptionalPayloadFailure("LTV_ERRORS.json",
                "LTV_ERRORS.json was empty or did not match the expected TSS2026 schema.");
        }
    }

    private void PatchLtvProcedureNeedsResolvedInCache(int procedureIndex, bool needsResolved)
    {
        if (procedureIndex < 0 || latestLtvErrorProcedures == null ||
            procedureIndex >= latestLtvErrorProcedures.Length)
            return;

        LtvErrorProcedure[] copy = new LtvErrorProcedure[latestLtvErrorProcedures.Length];
        for (int i = 0; i < latestLtvErrorProcedures.Length; i++)
        {
            LtvErrorProcedure src = latestLtvErrorProcedures[i];
            if (src == null)
                continue;
            copy[i] = new LtvErrorProcedure
            {
                code = src.code,
                description = src.description,
                needs_resolved = i == procedureIndex ? needsResolved : src.needs_resolved,
                procedures = src.procedures
            };
        }

        latestLtvErrorProcedures = copy;
        hasLtvErrorProcedures = copy.Length > 0;
    }

    private void PublishLtvErrorsFromCache()
    {
        List<LtvErrorProcedure> active = LtvErrorTaskSupport.FilterActive(latestLtvErrorProcedures);
        if (logLtvErrorsParseDiagnostics)
        {
            var codes = new List<string>(active.Count);
            foreach (LtvErrorProcedure p in active)
                codes.Add(string.IsNullOrEmpty(p.code) ? "?" : p.code.Trim());
            bool slim = LtvErrorTaskSupport.IsRecoveryOnlyUdpSnapshot(latestLtvErrorProcedures);
            bool keepPolling = LtvErrorTaskSupport.ShouldKeepPollingLtvErrors(latestLtvErrorProcedures);
            Debug.Log("[TSS] LTV_ERRORS cache publish: total_procedures=" + latestLtvErrorProcedures.Length +
                      " active_needs_resolved=" + active.Count + " codes=[" + string.Join(", ", codes) + "]" +
                      " slim_snapshot=" + slim + " should_keep_polling_ltv=" + keepPolling);
        }

        EventBus.Publish(new LtvErrorsUpdatedEvent(active.ToArray()));
    }

    private Task<bool> SendUdpPostAsync(int command, float payloadValue)
    {
        string host = tssHost;
        int port = tssPort;
        return Task.Run(() =>
        {
            try
            {
                using (UdpClient client = new UdpClient())
                {
                    client.Client.ReceiveTimeout = UdpTimeoutMs;
                    byte[] request = BuildUdpPostPacket(command, payloadValue);
                    client.Send(request, request.Length, host, port);
                    IPEndPoint remoteEndPoint = new IPEndPoint(IPAddress.Any, 0);
                    byte[] response = client.Receive(ref remoteEndPoint);
                    if (response == null || response.Length < 4)
                        return false;
                    uint status = BitConverter.ToUInt32(response, 0);
                    return status != 0;
                }
            }
            catch (Exception ex)
            {
                Debug.LogWarning("[TSS] SendUdpPostAsync: " + ex.Message);
                return false;
            }
        });
    }


    private string ExtractJsonPayload(byte[] response)
    {
        int start = Array.IndexOf(response, (byte)'{');
        int end = Array.LastIndexOf(response, (byte)'}');
        if (start < 0 || end <= start)
            throw new InvalidOperationException("UDP response did not contain a JSON object.");

        return Encoding.UTF8.GetString(response, start, end - start + 1);
    }


    private void HandleRequiredPayloadFailure(bool connectionAttempt, string message)
    {
        connected = false;
        if (!telemetryErrorLogged)
        {
            telemetryErrorLogged = true;
            Debug.LogError("[TSS] TSS2026 EVA " + (connectionAttempt ? "connection" : "poll") +
                           " failed for " + tssHost + ":" + tssPort +
                           " command=" + UdpEvaCommand + ". " + message);
        }

        OnTSSConnectionResult?.Invoke(false);
    }


    private void LogOptionalPayloadFailure(string label, string message)
    {
        if (Time.realtimeSinceStartup - lastOptionalPayloadWarningTime < OptionalPayloadWarningIntervalSeconds)
            return;

        lastOptionalPayloadWarningTime = Time.realtimeSinceStartup;
        Debug.LogWarning("[TSS] Optional TSS2026 payload " + label + " failed: " + message);
    }


    ////////////////////////////  EVA (UDP COMMAND 1)  /////////////////////////////
    private bool ApplyEvaJson(string json, bool forcePublish)
    {
        if (string.IsNullOrEmpty(json))
            return false;

        TssEvaPayload payload = JsonUtility.FromJson<TssEvaPayload>(json);
        if (payload?.telemetry?.eva1 == null)
            return false;

        bool jsonChanged = TELEMETRYJsonString != json;
        TELEMETRYJsonString = json;

        EvaTelemetryDetails eva1Telemetry = MapTssEvaTelemetry(
            payload.telemetry.eva1,
            AstronautInstance.User.telemetry?.telemetry?.eva1);
        int evaTime = Mathf.RoundToInt((float)payload.telemetry.eva1.eva_elapsed_time);

        TELEMETRY telemetry = AstronautInstance.User.telemetry ?? new TELEMETRY();
        if (telemetry.telemetry == null)
            telemetry.telemetry = new TelemetryDetails();

        telemetry.telemetry.eva_time = evaTime;
        telemetry.telemetry.eva1 = eva1Telemetry;
        if (payload.telemetry.eva2 != null)
        {
            telemetry.telemetry.eva2 = MapTssEvaTelemetry(
                payload.telemetry.eva2,
                telemetry.telemetry.eva2);
        }

        AstronautInstance.User.telemetry = telemetry;

        // Always refresh EV1 vitals UI on every successful poll (not gated on full JSON string).
        PublishEv1Vitals(eva1Telemetry, evaTime);

        if (!jsonChanged && !forcePublish)
            return true;

        PublishDcu(payload.dcu);
        PublishDcuError(payload.error);
        PublishImu(payload.imu);
        PublishUia(payload.uia);

        return true;
    }


    ////////////////////////////  ROVER (UDP COMMAND 0)  /////////////////////////////
    private bool ApplyRoverJson(string json)
    {
        if (string.IsNullOrEmpty(json))
            return false;

        TssRoverPayload payload = JsonUtility.FromJson<TssRoverPayload>(json);
        if (payload?.pr_telemetry == null)
            return false;

        ROVERJsonString = json;
        latestRoverPosition = new Vector3(
            (float)payload.pr_telemetry.rover_pos_x,
            (float)payload.pr_telemetry.rover_pos_y,
            (float)payload.pr_telemetry.rover_pos_z);
        hasRoverPosition = true;

        if (AstronautInstance.User.rover == null)
            AstronautInstance.User.rover = new ROVER();

        if (AstronautInstance.User.rover.rover == null)
            AstronautInstance.User.rover.rover = new RoverDetails();

        AstronautInstance.User.rover.rover.posx = payload.pr_telemetry.rover_pos_x;
        AstronautInstance.User.rover.rover.posy = payload.pr_telemetry.rover_pos_y;

        return true;
    }


    ////////////////////////////  LTV (UDP COMMAND 2)  /////////////////////////////
    private bool ApplyLtvJson(string json)
    {
        if (string.IsNullOrEmpty(json))
            return false;

        TssLtvPayload payload = JsonUtility.FromJson<TssLtvPayload>(json);
        if (payload?.location == null)
            return false;

        LTVJsonString = json;
        latestLtvLocation = new Vector2((float)payload.location.last_known_x, (float)payload.location.last_known_y);
        hasLtvLocation = true;

        return true;
    }


    ////////////////////////////  LTV_ERRORS (UDP COMMAND 3)  /////////////////////////////
    private bool ApplyLtvErrorsJson(string json)
    {
        if (string.IsNullOrEmpty(json))
            return false;

        try
        {
            JObject root = JObject.Parse(json);
            JArray arr = root["error_procedures"] as JArray;
            if (arr == null)
                return false;

            var parsed = new List<LtvErrorProcedure>(arr.Count);
            foreach (JToken token in arr)
            {
                if (!(token is JObject o))
                    continue;

                string code = o["code"]?.Type == JTokenType.String ? (o["code"].Value<string>() ?? string.Empty).Trim() : null;
                string description = o["description"]?.Type == JTokenType.String
                    ? (o["description"].Value<string>() ?? string.Empty).Trim()
                    : null;

                bool needsResolved = ReadNeedsResolved(o["needs_resolved"]);
                if (ermClearPostPending && string.Equals(code, "4800", StringComparison.Ordinal))
                    needsResolved = false;

                parsed.Add(new LtvErrorProcedure
                {
                    code = code,
                    description = description,
                    needs_resolved = needsResolved,
                    procedures = ReadLtvProcedureSteps(o["procedures"])
                });
            }

            LTVErrorsJsonString = json;
            var fullProcedures = parsed.Count > 0 ? parsed.ToArray() : EmptyLtvErrorProcedures;

            // Apply our custom client-side minimized instructions instead of NASA's long text
            LtvErrorTaskSupport.ApplyMinimizedProcedures(fullProcedures);

            if (LtvErrorTaskSupport.IsRecoveryModeActive(fullProcedures))
            {
                var ermOnly = new List<LtvErrorProcedure>();
                foreach (var p in fullProcedures)
                {
                    if (p.code == "4800")
                        ermOnly.Add(p);
                }
                latestLtvErrorProcedures = ermOnly.ToArray();
            }
            else
            {
                latestLtvErrorProcedures = fullProcedures;
            }

            hasLtvErrorProcedures = latestLtvErrorProcedures.Length > 0;

            if (ermClearPostPending && LtvErrorTaskSupport.HasFullLtvErrorsSnapshot(latestLtvErrorProcedures))
                ermClearPostPending = false;

            if (logLtvErrorsParseDiagnostics)
            {
                List<LtvErrorProcedure> active = LtvErrorTaskSupport.FilterActive(latestLtvErrorProcedures);
                var codes = new List<string>(active.Count);
                foreach (LtvErrorProcedure p in active)
                    codes.Add(string.IsNullOrEmpty(p.code) ? "?" : p.code.Trim());
                bool slim = LtvErrorTaskSupport.IsRecoveryOnlyUdpSnapshot(latestLtvErrorProcedures);
                bool keepPolling = LtvErrorTaskSupport.ShouldKeepPollingLtvErrors(latestLtvErrorProcedures);
                Debug.Log("[TSS] LTV_ERRORS Newtonsoft parse: total_procedures=" + latestLtvErrorProcedures.Length +
                          " active_needs_resolved=" + active.Count + " codes=[" + string.Join(", ", codes) + "]" +
                          " slim_snapshot=" + slim + " should_keep_polling_ltv=" + keepPolling);
            }

            PublishLtvErrorsFromCache();
            return true;
        }
        catch (Exception ex)
        {
            Debug.LogWarning("[TSS] LTV_ERRORS JSON parse failed: " + ex.Message);
            return false;
        }
    }

    private static bool ReadNeedsResolved(JToken token)
    {
        if (token == null || token.Type == JTokenType.Null)
            return false;

        switch (token.Type)
        {
            case JTokenType.Boolean:
                return token.Value<bool>();
            case JTokenType.Integer:
                return token.Value<long>() != 0;
            case JTokenType.Float:
                return Math.Abs(token.Value<double>()) > double.Epsilon;
            case JTokenType.String:
                string s = token.Value<string>();
                return string.Equals((s ?? string.Empty).Trim(), "true", StringComparison.OrdinalIgnoreCase);
            default:
                return false;
        }
    }

    private static string[] ReadLtvProcedureSteps(JToken proceduresToken)
    {
        if (proceduresToken == null || proceduresToken.Type == JTokenType.Null)
            return Array.Empty<string>();

        JArray arr = proceduresToken as JArray;
        if (arr == null || arr.Count == 0)
            return Array.Empty<string>();

        var steps = new List<string>(arr.Count);
        foreach (JToken step in arr)
        {
            if (step.Type == JTokenType.String)
            {
                string s = step.Value<string>();
                if (!string.IsNullOrEmpty(s))
                    steps.Add(s);
            }
            else if (step.Type != JTokenType.Null)
                steps.Add(step.ToString());
        }

        return steps.Count > 0 ? steps.ToArray() : Array.Empty<string>();
    }


    ////////////////////////////  EVA VITALS  /////////////////////////////
    private EvaTelemetryDetails MapTssEvaTelemetry(TssEvaTelemetry tss, EvaTelemetryDetails previous)
    {
        return new EvaTelemetryDetails
        {
            primary_battery_level = tss.primary_battery_level,
            secondary_battery_level = tss.secondary_battery_level,
            batt_time_left = previous != null ? previous.batt_time_left : 0,
            oxy_pri_storage = tss.oxy_pri_storage,
            oxy_sec_storage = tss.oxy_sec_storage,
            oxy_pri_pressure = tss.oxy_pri_pressure,
            oxy_sec_pressure = tss.oxy_sec_pressure,
            oxy_time_left = previous != null ? previous.oxy_time_left : 0,
            heart_rate = tss.heart_rate,
            oxy_consumption = tss.oxy_consumption,
            co2_production = tss.co2_production,
            suit_pressure_oxy = tss.suit_pressure_oxy,
            suit_pressure_co2 = tss.suit_pressure_co2,
            suit_pressure_other = tss.suit_pressure_other,
            suit_pressure_total = tss.suit_pressure_total,
            fan_pri_rpm = tss.fan_pri_rpm,
            fan_sec_rpm = tss.fan_sec_rpm,
            helmet_pressure_co2 = tss.helmet_pressure_co2,
            scrubber_a_co2_storage = tss.scrubber_a_co2_storage,
            scrubber_b_co2_storage = tss.scrubber_b_co2_storage,
            temperature = tss.temperature,
            coolant_m = tss.coolant_storage,
            coolant_gas_pressure = tss.coolant_gas_pressure,
            coolant_liquid_pressure = tss.coolant_liquid_pressure
        };
    }


    private void PublishEv1Vitals(EvaTelemetryDetails eva1Telemetry, int evaTime)
    {
        CopyVitals(AstronautInstance.User.vitals, eva1Telemetry);
        AstronautInstance.User.vitals.eva_time = evaTime;
        EventBus.Publish<UpdatedVitalsEvent>(new UpdatedVitalsEvent(AstronautInstance.User.vitals));
    }


    ////////////////////////////  DCU  /////////////////////////////
    private void PublishDcu(TssDcuPayload dcuPayload)
    {
        if (dcuPayload == null)
            return;

        DCU dcu = new DCU
        {
            dcu = new DCUData
            {
                eva1 = MapEva1Dcu(dcuPayload.eva1),
                eva2 = MapEva2Dcu(dcuPayload.eva2)
            }
        };

        AstronautInstance.User.dcu = dcu;
        EventBus.Publish(new DCUChangedEvent(dcu.dcu.eva1));
    }


    private EvaDetails MapEva1Dcu(TssEva1Dcu dcu)
    {
        return new EvaDetails
        {
            batt = dcu?.batt != null && dcu.batt.ps,
            oxy = dcu != null && dcu.oxy,
            comm = false,
            fan = dcu != null && dcu.fan,
            pump = dcu != null && dcu.pump,
            co2 = dcu != null && dcu.co2
        };
    }


    private EvaDetails MapEva2Dcu(TssEva2Dcu dcu)
    {
        return new EvaDetails
        {
            batt = dcu != null && dcu.batt,
            oxy = dcu != null && dcu.oxy,
            comm = dcu != null && dcu.comm,
            fan = dcu != null && dcu.fan,
            pump = dcu != null && dcu.pump,
            co2 = dcu != null && dcu.co2
        };
    }


    ////////////////////////////  DCU ERROR  /////////////////////////////
    private void PublishDcuError(TssEvaError error)
    {
        if (error == null)
            return;

        ErrorMsg mappedError = new ErrorMsg
        {
            fan = error.fan_error,
            oxy = error.oxy_error,
            pump = error.power_error || error.scrubber_error
        };

        ErrorJsonString = JsonUtility.ToJson(error);
        EventBus.Publish(new DCUErrorEvent(mappedError));
    }


    ////////////////////////////  UIA  /////////////////////////////
    private void PublishUia(UiDetails uiaDetails)
    {
        if (uiaDetails == null)
            return;

        UIA uia = new UIA { uia = uiaDetails };
        AstronautInstance.User.uia = uia;
        UIAJsonString = JsonUtility.ToJson(uia);
        EventBus.Publish(new UIAUpdatedEvent(uia));
    }


    ////////////////////////////  IMU / GPS  /////////////////////////////
    private void PublishImu(IMUEVAs imu)
    {
        if (imu?.eva1 == null)
            return;

        AstronautInstance.User.imu = new IMU { imu = imu };
        IMUJsonString = JsonUtility.ToJson(AstronautInstance.User.imu);

        IMUData eva1Imu = imu.eva1;
        float posX = (float)eva1Imu.posx;
        float posY = (float)eva1Imu.posy;

        if (!imuInitialized && (posX != 0 || posY != 0))
            imuInitialized = true;

        AstronautInstance.User.current = new Location(
            posX - AstronautInstance.User.origin.posX,
            0,
            posY - AstronautInstance.User.origin.posZ,
            eva1Imu.heading);
    }


    private void CopyVitals(Vitals vital, EvaTelemetryDetails t)
    {
        vital.primary_battery_level = t.primary_battery_level;
        vital.secondary_battery_level = t.secondary_battery_level;
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


    ////////////////////////////  TSS2026 JSON MODELS  /////////////////////////////
    private class CommandFetchResult
    {
        public int Command { get; private set; }
        public string Label { get; private set; }
        public bool Success { get; private set; }
        public string Json { get; private set; }
        public string ErrorMessage { get; private set; }

        public CommandFetchResult(int command, string label)
        {
            Command = command;
            Label = label;
        }

        public void Succeed(string json)
        {
            Success = true;
            Json = json;
            ErrorMessage = null;
        }

        public void Fail(string errorMessage)
        {
            Success = false;
            Json = null;
            ErrorMessage = Label + " command " + Command + ": " + errorMessage;
        }
    }


    ////////////////////////////  EVA.JSON (COMMAND 1)  /////////////////////////////
    [Serializable]
    private class TssEvaPayload
    {
        public TssTelemetryPayload telemetry;
        public TssDcuPayload dcu;
        public TssEvaError error;
        public IMUEVAs imu;
        public UiDetails uia;
    }


    [Serializable]
    private class TssTelemetryPayload
    {
        public TssEvaTelemetry eva1;
        public TssEvaTelemetry eva2;
    }


    [Serializable]
    private class TssEvaTelemetry
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


    [Serializable]
    private class TssDcuPayload
    {
        public TssEva1Dcu eva1;
        public TssEva2Dcu eva2;
    }


    [Serializable]
    private class TssEva1Dcu
    {
        public TssDcuBattery batt;
        public bool oxy;
        public bool fan;
        public bool pump;
        public bool co2;
    }


    [Serializable]
    private class TssEva2Dcu
    {
        public bool batt;
        public bool oxy;
        public bool comm;
        public bool fan;
        public bool pump;
        public bool co2;
    }


    [Serializable]
    private class TssDcuBattery
    {
        public bool lu;
        public bool ps;
    }


    [Serializable]
    private class TssEvaError
    {
        public bool fan_error;
        public bool oxy_error;
        public bool power_error;
        public bool scrubber_error;
    }


    ////////////////////////////  ROVER.JSON (COMMAND 0)  /////////////////////////////
    [Serializable]
    private class TssRoverPayload
    {
        public TssRoverTelemetry pr_telemetry;
    }


    [Serializable]
    private class TssRoverTelemetry
    {
        public double rover_pos_x;
        public double rover_pos_y;
        public double rover_pos_z;
    }


    ////////////////////////////  LTV.JSON (COMMAND 2)  /////////////////////////////
    [Serializable]
    private class TssLtvPayload
    {
        public TssLtvLocation location;
    }


    [Serializable]
    private class TssLtvLocation
    {
        public double last_known_x;
        public double last_known_y;
    }
}
