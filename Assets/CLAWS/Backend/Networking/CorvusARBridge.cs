// CorvusARBridge: routes intents from the AIA pipeline (CorvusController) to real
// Unity actions in the GEMINI scene (vitals readouts, menus, procedures, tasks,
// navigation, waypoints) and produces the spoken response.
//
// Unsupported intents in this scene/build (each logs [CORVUS][NotImplemented]):
//   open_menu_messaging                  - ScreenManager forces messaging off every frame
//   open_menu_voice_assistant            - no dedicated screen; CORVUS UI is the dialogue bubble
//   open_menu_geosamples                 - no Geosamples screen exists in this scene
//   start_procedure_physical_repair_task - no matching TaskGroup in TaskDetailScreen
//   start_procedure_final_system_checks  - no matching TaskGroup in TaskDetailScreen
//   undo                                 - no undo stack
//
// Notes:
//   - Dynamic task groups created via Add_task are reachable by voice only; the
//     task main menu in the scene uses fixed buttons.
//   - Named-target resolution searches NavigationController waypoint lists first,
//     then falls back to scene-aliased anchors (LTV/rover -> ROVER, EV2 -> EV2_PlayerIcon).

using System;
using System.Collections.Generic;
using UnityEngine;
using CLAWS.Networking;

public class CorvusARBridge : MonoBehaviour
{
    [Header("Networking")]
    [SerializeField] private CorvusController _corvusController;
    [SerializeField] private DialogueManager _dialogueManager;
    [SerializeField] private CorvusTTS _tts;

    [Header("Scene Systems")]
    [SerializeField] private ScreenManager _screenManager;
    [SerializeField] private Pathfinding _pathfinding;
    [SerializeField] private TaskDetailScreen _taskDetailScreen;
    [SerializeField] private UIAController _uiaController;
    [SerializeField] private NavigationController _navigationController;

    [Tooltip("Optional EV1/player transform used by Add_waypoint to drop a marker at the current position. Falls back to AstronautInstance.User.current if not set.")]
    [SerializeField] private Transform _playerTransform;

    // Cached state for reroute_navigation
    private Vector3? _lastNavTarget;
    private string _lastNavTargetName;

    private void Start()
    {
        if(_corvusController == null)
        {
            Debug.LogError("CorvusController not found in Scene!");
            return;
        }
        _corvusController.OnIntentResponseReceived += OnIntentResponseReceived;
    }

    private void OnDestroy()
    {
        if(_corvusController != null)
            _corvusController.OnIntentResponseReceived -= OnIntentResponseReceived;
    }

    // -----------------------------------------------------------------------
    // Dispatcher
    // -----------------------------------------------------------------------

    /// <summary>
    /// Run an intent through the same path as a live NLU response (no mic / Python required).
    /// Use from editor keyboard tests or other local harnesses.
    /// </summary>
    public void SimulateIntent(string intent, IntentParameters parameters = null, string responseText = null)
    {
        var raw = new IntentResponse
        {
            intent = intent,
            confidence = 1f,
            status = "ok",
            response = responseText ?? "",
            parameters = parameters,
        };
        OnIntentResponseReceived(raw, new CorvusLatency());
    }

    private void OnIntentResponseReceived(IntentResponse raw, CorvusLatency latency)
    {
        if (raw == null) return;
        IntentParameters p = raw.parameters; // may be null

        string spoken;
        try
        {
            spoken = Dispatch(raw.intent, p, raw.response);
        }
        catch (Exception ex)
        {
            Debug.LogError($"[CORVUS] Dispatch error for intent '{raw.intent}': {ex}");
            spoken = "Something went wrong while handling that.";
        }

        if (string.IsNullOrEmpty(spoken))
            spoken = string.IsNullOrEmpty(raw.response) ? (raw.intent ?? "").Replace("_", " ") : raw.response;

        DisplayResponse(raw.intent, spoken);
        _ = _tts?.Speak(spoken);
    }

    private string Dispatch(string intent, IntentParameters p, string fallbackResponse)
    {
        switch (intent)
        {
            // ---------- Vitals (read-only readouts) ----------
            case "vitals_batt_time_left":         return FormatHm(GetVitalsSeconds(v => v.batt_time_left), "battery time remaining");
            case "vitals_oxy_pri_storage":        return ReadVital(v => v.oxy_pri_storage, "primary oxygen storage", "%", "F0");
            case "vitals_oxy_sec_storage":        return ReadVital(v => v.oxy_sec_storage, "secondary oxygen storage", "%", "F0");
            case "vitals_oxy_pri_pressure":      return ReadVital(v => v.oxy_pri_pressure, "primary oxygen pressure", "psi", "F0");
            case "vitals_oxy_sec_pressure":      return ReadVital(v => v.oxy_sec_pressure, "secondary oxygen pressure", "psi", "F0");
            case "vitals_oxy_time_left":         return FormatHm(GetVitalsSeconds(v => v.oxy_time_left), "oxygen time remaining");
            case "vitals_coolant_storage":       return ReadVital(v => v.coolant_m, "coolant storage", "%", "F0");
            case "vitals_heart_rate":            return ReadVital(v => v.heart_rate, "heart rate", "BPM", "F0");
            case "vitals_oxy_consumption":       return ReadVital(v => v.oxy_consumption, "oxygen consumption", "liters per minute", "F2");
            case "vitals_co2_production":        return ReadVital(v => v.co2_production, "CO2 production", "liters per minute", "F2");
            case "vitals_suit_pressure_oxy":     return ReadVital(v => v.suit_pressure_oxy, "suit oxygen pressure", "psi", "F2");
            case "vitals_suit_pressure_co2":     return ReadVital(v => v.suit_pressure_co2, "suit CO2 pressure", "psi", "F2");
            case "vitals_suit_pressure_other":   return ReadVital(v => v.suit_pressure_other, "other gas pressure in the suit", "psi", "F2");
            case "vitals_suit_pressure_total":   return ReadVital(v => v.suit_pressure_total, "total suit pressure", "psi", "F2");
            case "vitals_helmet_pressure_co2":   return ReadVital(v => v.helmet_pressure_co2, "helmet CO2 pressure", "psi", "F2");
            case "vitals_fan_pri_rpm":           return ReadVital(v => v.fan_pri_rpm, "primary fan speed", "RPM", "F0");
            case "vitals_fan_sec_rpm":           return ReadVital(v => v.fan_sec_rpm, "secondary fan speed", "RPM", "F0");
            case "vitals_scrubber_a_co2_storage": return ReadVital(v => v.scrubber_a_co2_storage, "scrubber A CO2 storage", "%", "F0");
            case "vitals_scrubber_b_co2_storage": return ReadVital(v => v.scrubber_b_co2_storage, "scrubber B CO2 storage", "%", "F0");
            case "vitals_temperature":           return ReadVital(v => v.temperature, "suit temperature", "degrees", "F1");
            case "vitals_coolant_liquid_pressure": return ReadVital(v => v.coolant_liquid_pressure, "coolant liquid pressure", "psi", "F0");
            case "vitals_coolant_gas_pressure":  return ReadVital(v => v.coolant_gas_pressure, "coolant gas pressure", "psi", "F0");

            case "get_warnings":                 return BuildWarningsSpoken();

            // ---------- Menus ----------
            case "open_menu_vitals":             return OpenScreen(4, "vitals");
            case "open_menu_navigation":         return OpenScreen(1, "navigation");
            case "open_menu_tasks":              return OpenScreen(2, "task list");
            case "open_menu_uia":                return OpenScreen(0, "UIA controls");
            case "open_menu_rover":              return OpenScreen(5, "rover dashboard");
            case "open_menu_messaging":          return Unsupported("messaging menu");
            case "open_menu_voice_assistant":    return Unsupported("voice assistant menu");
            case "open_menu_geosamples":         return Unsupported("geosamples menu");
            case "close_menu":                   return CloseAllMenus();

            // ---------- Procedures ----------
            case "start_procedure_erm":              return StartTaskProcedure(0, "Exit Recovery Mode");
            case "start_procedure_system_diagnosis": return StartTaskProcedure(1, "System Diagnosis");
            case "start_procedure_system_restart":   return StartTaskProcedure(2, "System Restart");
            case "start_procedure_uia_ingress":  return StartUIAProcedure(ingress: true);
            case "start_procedure_uia_egress":   return StartUIAProcedure(ingress: false);
            case "start_procedure_physical_repair_task": return Unsupported("physical repair procedure");
            case "start_procedure_final_system_checks":  return Unsupported("final system checks procedure");

            // ---------- Navigation ----------
            case "Get_coordinates":              return GetCoordinates(p?.COORDINATE_TARGET_NAME);
            case "Set_navigation_target":        return SetNavTarget(p?.NAVIGATION_TARGET_NAME);
            case "reroute_navigation":           return Reroute();

            // ---------- Waypoints ----------
            case "Add_waypoint":                 return AddWaypoint(p?.WAYPOINT_NAME);
            case "Delete_waypoint":              return DeleteWaypoint(p?.WAYPOINT_NAME);

            // ---------- Tasks ----------
            case "Add_task":                     return AddTask(p?.TASK_NAME);
            case "Delete_task":                  return DeleteTask(p?.TASK_NAME);
            case "Complete_task":                return CompleteTask(p?.TASK_NAME);

            // ---------- Meta ----------
            case "undo":                         return Unsupported("undo");
            case "unhandled":                    return "Sorry, I can't help with that.";

            // ---------- Legacy aliases ----------
            case "check_vitals":                 return OpenScreen(4, "vitals");
            case "close_vitals":                 return CloseAllMenus();

            default:                             return DefaultDialogue(intent, fallbackResponse);
        }
    }

    // -----------------------------------------------------------------------
    // Output helpers
    // -----------------------------------------------------------------------

    private void DisplayResponse(string intent, string responseText)
    {
        if (_dialogueManager == null) return;

        string displayText = string.IsNullOrEmpty(responseText)
            ? (intent ?? "").Replace("_", " ")
            : responseText;

        Dialogue response = new Dialogue();
        response.name = "CORVUS";
        response.sentences = new string[] { displayText };
        _dialogueManager.StartDialogue(response);
        _dialogueManager.DisplayNextSentence();
    }

    private string DefaultDialogue(string intent, string fallbackResponse)
    {
        if (!string.IsNullOrEmpty(fallbackResponse)) return fallbackResponse;
        if (string.IsNullOrEmpty(intent)) return "I didn't catch that.";
        return $"Processing {intent.Replace("_", " ")}.";
    }

    private string Unsupported(string what)
    {
        Debug.LogWarning($"[CORVUS][NotImplemented] {what}");
        return $"Sorry, {what} isn't supported in this build yet.";
    }

    // -----------------------------------------------------------------------
    // Vitals helpers
    // -----------------------------------------------------------------------

    private static Vitals V()
    {
        try { return AstronautInstance.User?.vitals; }
        catch { return null; }
    }

    private string ReadVital(Func<Vitals, double> getter, string label, string unit, string fmt = "F1")
    {
        var v = V();
        if (v == null) return $"I don't have a current reading for {label} yet.";
        double x = getter(v);
        string unitPart = string.IsNullOrEmpty(unit) ? "" : $" {unit}";
        return $"Your {label} is {x.ToString(fmt)}{unitPart}.";
    }

    private double GetVitalsSeconds(Func<Vitals, double> getter)
    {
        var v = V();
        return v == null ? double.NaN : getter(v);
    }

    private string FormatHm(double seconds, string label)
    {
        if (double.IsNaN(seconds)) return $"I don't have a current reading for {label} yet.";
        int total = Mathf.Max(0, Mathf.RoundToInt((float)seconds));
        int hours = total / 3600;
        int minutes = (total % 3600) / 60;
        if (hours <= 0 && minutes <= 0) return $"Your {label} is essentially zero.";
        if (hours <= 0) return $"Your {label} is {minutes} minute{(minutes == 1 ? "" : "s")}.";
        if (minutes <= 0) return $"Your {label} is {hours} hour{(hours == 1 ? "" : "s")}.";
        return $"Your {label} is {hours} hour{(hours == 1 ? "" : "s")} and {minutes} minute{(minutes == 1 ? "" : "s")}.";
    }

    // -----------------------------------------------------------------------
    // get_warnings: compare every vital against VitalsNominalLimits
    // -----------------------------------------------------------------------

    private string BuildWarningsSpoken()
    {
        var v = V();
        if (v == null) return "I don't have any vitals data right now.";

        var warnings = new List<string>();

        void Check(bool bad, string msg) { if (bad) warnings.Add(msg); }

        Check(v.batt_time_left < VitalsNominalLimits.BattTimeMin, "battery time remaining is low");
        Check(v.primary_battery_level < VitalsNominalLimits.BattLevelMin, "primary battery level is low");
        Check(v.secondary_battery_level < VitalsNominalLimits.BattLevelMin, "secondary battery level is low");
        Check(v.oxy_pri_storage < VitalsNominalLimits.OxyStorMin, "primary oxygen storage is low");
        Check(v.oxy_sec_storage < VitalsNominalLimits.OxyStorMin, "secondary oxygen storage is low");

        Check(v.oxy_pri_pressure < VitalsNominalLimits.OxyPresMin || v.oxy_pri_pressure > VitalsNominalLimits.OxyPresMax,
            "primary oxygen pressure is out of range");
        Check(v.oxy_sec_pressure < VitalsNominalLimits.OxyPresMin || v.oxy_sec_pressure > VitalsNominalLimits.OxyPresMax,
            "secondary oxygen pressure is out of range");

        Check(v.oxy_time_left < VitalsNominalLimits.OxyTimeMin, "oxygen time remaining is dangerously low");
        Check(v.coolant_m < VitalsNominalLimits.CoolStorMin, "coolant storage is low");

        Check(v.heart_rate < VitalsNominalLimits.HeartRateMin || v.heart_rate > VitalsNominalLimits.HeartRateMax,
            "heart rate is out of nominal range");

        Check(v.oxy_consumption < VitalsNominalLimits.OxyConsumMin || v.oxy_consumption > VitalsNominalLimits.OxyConsumMax,
            "oxygen consumption is out of nominal range");
        Check(v.co2_production < VitalsNominalLimits.Co2ProdMin || v.co2_production > VitalsNominalLimits.Co2ProdMax,
            "CO2 production is out of nominal range");

        Check(v.suit_pressure_oxy < VitalsNominalLimits.SuitPresOxyMin || v.suit_pressure_oxy > VitalsNominalLimits.SuitPresOxyMax,
            "suit oxygen pressure is out of nominal range");
        Check(v.suit_pressure_co2 > VitalsNominalLimits.SuitPresCo2Max, "suit CO2 pressure is high");
        Check(v.suit_pressure_other > VitalsNominalLimits.SuitPresOtherMax, "other suit gas pressure is high");
        Check(v.suit_pressure_total < VitalsNominalLimits.SuitPresTotalMin || v.suit_pressure_total > VitalsNominalLimits.SuitPresTotalMax,
            "total suit pressure is out of nominal range");

        Check(v.helmet_pressure_co2 > VitalsNominalLimits.HelmetPresCo2Max, "helmet CO2 pressure is high");

        Check(v.fan_pri_rpm < VitalsNominalLimits.FanSpeedMin || v.fan_pri_rpm > VitalsNominalLimits.FanSpeedMax,
            "primary fan speed is out of nominal range");
        Check(v.fan_sec_rpm < VitalsNominalLimits.FanSpeedMin || v.fan_sec_rpm > VitalsNominalLimits.FanSpeedMax,
            "secondary fan speed is out of nominal range");

        Check(v.scrubber_a_co2_storage > VitalsNominalLimits.ScrubberCo2StorMax, "scrubber A is nearing capacity");
        Check(v.scrubber_b_co2_storage > VitalsNominalLimits.ScrubberCo2StorMax, "scrubber B is nearing capacity");

        Check(v.temperature < VitalsNominalLimits.TempMin || v.temperature > VitalsNominalLimits.TempMax,
            "suit temperature is out of nominal range");

        Check(v.coolant_liquid_pressure < VitalsNominalLimits.CoolLiqMin || v.coolant_liquid_pressure > VitalsNominalLimits.CoolLiqMax,
            "coolant liquid pressure is out of nominal range");
        Check(v.coolant_gas_pressure > VitalsNominalLimits.CoolGasMax, "coolant gas pressure is high");

        if (warnings.Count == 0) return "All vitals are nominal.";
        if (warnings.Count == 1) return $"Warning: {warnings[0]}.";
        return $"Warnings: {string.Join("; ", warnings)}.";
    }

    // -----------------------------------------------------------------------
    // Menus
    // -----------------------------------------------------------------------

    private string OpenScreen(int index, string label)
    {
        if (_screenManager == null)
        {
            Debug.LogWarning("[CORVUS] ScreenManager not assigned on CorvusARBridge.");
            return $"I can't open the {label} screen right now.";
        }
        _screenManager.openScreen(index);
        return $"Opening {label}.";
    }

    private string CloseAllMenus()
    {
        if (_screenManager == null)
        {
            Debug.LogWarning("[CORVUS] ScreenManager not assigned on CorvusARBridge.");
            return "I can't close menus right now.";
        }
        _screenManager.DeactivateAllScreens();
        return "Menus closed.";
    }

    // -----------------------------------------------------------------------
    // Procedures
    // -----------------------------------------------------------------------

    private string StartTaskProcedure(int groupIndex, string label)
    {
        if (_screenManager == null || _taskDetailScreen == null)
        {
            Debug.LogWarning("[CORVUS] ScreenManager or TaskDetailScreen missing - cannot start procedure.");
            return $"I can't start the {label} procedure right now.";
        }
        _screenManager.openScreen(2);
        _taskDetailScreen.ShowTaskDetailMenu(groupIndex);
        return $"Starting the {label} procedure.";
    }

    private string StartUIAProcedure(bool ingress)
    {
        string label = ingress ? "UIA ingress" : "UIA egress";
        if (_screenManager == null || _uiaController == null)
        {
            Debug.LogWarning("[CORVUS] ScreenManager or UIAController missing - cannot start UIA procedure.");
            return $"I can't start the {label} procedure right now.";
        }
        _screenManager.openScreen(0);
        if (ingress) _uiaController.IngressProcedure();
        else _uiaController.EgressProcedure();
        return $"Starting the {label} procedure.";
    }

    // -----------------------------------------------------------------------
    // Navigation
    // -----------------------------------------------------------------------

    private string GetCoordinates(string targetName)
    {
        if (string.IsNullOrWhiteSpace(targetName)) return "Which location did you want the coordinates for?";
        if (!TryResolveLocation(targetName, out Vector3 pos, out string resolvedName))
            return $"I don't know where {targetName} is.";
        return $"{resolvedName} is at X {pos.x:F0}, Z {pos.z:F0}.";
    }

    private string SetNavTarget(string targetName)
    {
        if (string.IsNullOrWhiteSpace(targetName)) return "Which destination did you want to navigate to?";
        if (!TryResolveLocation(targetName, out Vector3 pos, out string resolvedName))
            return $"I don't know where {targetName} is.";
        if (_pathfinding == null)
        {
            Debug.LogWarning("[CORVUS] Pathfinding not assigned on CorvusARBridge.");
            return $"I can't compute a route to {resolvedName} right now.";
        }
        _pathfinding.SetTarget(pos);
        _lastNavTarget = pos;
        _lastNavTargetName = resolvedName;
        return $"Setting destination to {resolvedName}.";
    }

    private string Reroute()
    {
        if (_pathfinding == null)
        {
            Debug.LogWarning("[CORVUS] Pathfinding not assigned on CorvusARBridge.");
            return "I can't reroute right now.";
        }
        if (!_lastNavTarget.HasValue) return "There is no active destination to reroute.";
        _pathfinding.SetTarget(_lastNavTarget.Value);
        return $"Rerouting to {_lastNavTargetName}.";
    }

    /// <summary>
    /// Resolve a free-text name to a world-space position. Order:
    ///   1. Hard-coded scene aliases (LTV/rover/PR, EV2/companion).
    ///   2. Case-insensitive substring match against NavigationController waypoint lists.
    /// </summary>
    private bool TryResolveLocation(string name, out Vector3 worldPos, out string resolvedName)
    {
        worldPos = Vector3.zero;
        resolvedName = null;
        if (string.IsNullOrWhiteSpace(name)) return false;

        string needle = name.Trim().ToLowerInvariant();

        // 1) Scene aliases
        if (needle.Contains("ltv") || needle.Contains("rover") || needle == "pr" ||
            needle.Contains("pressurized rover") || needle.Contains("pressurised rover"))
        {
            GameObject rover = GameObject.Find("PR_ICON") ?? GameObject.Find("ROVER");
            if (rover != null)
            {
                worldPos = rover.transform.position;
                resolvedName = needle.Contains("ltv") ? "LTV" : "the rover";
                return true;
            }
        }
        if (needle == "ev2" || needle.Contains("ev2") || needle.Contains("companion") || needle.Contains("crewmate"))
        {
            GameObject ltv = GameObject.Find("LTV_ICON");
            if (ltv != null)
            {
                worldPos = ltv.transform.position;
                resolvedName = "LTV";
                return true;
            }
        }

        // 2) Waypoint name lookup
        if (_navigationController != null)
        {
            List<List<Waypoint>> lists = new List<List<Waypoint>>
            {
                _navigationController.waypointList,
                _navigationController.StationWaypointList,
                _navigationController.POIWaypointList,
                _navigationController.DangerWaypointList,
                _navigationController.GeoWaypointList,
            };

            foreach (var list in lists)
            {
                if (list == null) continue;
                foreach (var wp in list)
                {
                    if (wp == null || string.IsNullOrEmpty(wp.Name)) continue;
                    string wpName = wp.Name.ToLowerInvariant();
                    if (wpName == needle || wpName.Contains(needle) || needle.Contains(wpName))
                    {
                        worldPos = new Vector3((float)wp.UNITYposX, 0f, (float)wp.UNITYposZ);
                        resolvedName = wp.Name;
                        return true;
                    }
                }
            }
        }

        return false;
    }

    // -----------------------------------------------------------------------
    // Waypoints
    // -----------------------------------------------------------------------

    private string AddWaypoint(string waypointName)
    {
        if (string.IsNullOrWhiteSpace(waypointName)) return "What should I name the waypoint?";

        Vector3 pos;
        if (_playerTransform != null)
        {
            pos = _playerTransform.position;
        }
        else if (AstronautInstance.User?.current != null)
        {
            var c = AstronautInstance.User.current;
            pos = new Vector3((float)c.posX, 0f, (float)c.posZ);
        }
        else
        {
            return "I don't know your current position, so I can't drop a waypoint here.";
        }

        int nextId = (_navigationController?.waypointList?.Count ?? 0) + 1;

        AuthorType author = AuthorType.EV1;
        if (AstronautInstance.User != null)
            author = AstronautInstance.User.id == 1 ? AuthorType.EV1 : AuthorType.EV2;

        var wp = new Waypoint
        {
            Use = "ADD",
            Id = nextId,
            Name = waypointName.Trim(),
            UNITYposX = pos.x,
            UNITYposZ = pos.z,
            Type = WaypointType.POI,
            Author = author,
        };

        EventBus.Publish(new WaypointAddedEvent(wp));
        return $"Waypoint {wp.Name} added.";
    }

    private string DeleteWaypoint(string waypointName)
    {
        if (string.IsNullOrWhiteSpace(waypointName)) return "Which waypoint should I remove?";
        if (_navigationController == null)
        {
            Debug.LogWarning("[CORVUS] NavigationController not assigned on CorvusARBridge.");
            return "I can't access the waypoint list right now.";
        }

        string needle = waypointName.Trim().ToLowerInvariant();
        Waypoint found = null;

        List<List<Waypoint>> lists = new List<List<Waypoint>>
        {
            _navigationController.waypointList,
            _navigationController.StationWaypointList,
            _navigationController.POIWaypointList,
            _navigationController.DangerWaypointList,
            _navigationController.GeoWaypointList,
        };

        foreach (var list in lists)
        {
            if (list == null) continue;
            foreach (var wp in list)
            {
                if (wp == null || string.IsNullOrEmpty(wp.Name)) continue;
                string wpName = wp.Name.ToLowerInvariant();
                if (wpName == needle || wpName.Contains(needle) || needle.Contains(wpName))
                {
                    found = wp;
                    break;
                }
            }
            if (found != null) break;
        }

        if (found == null) return $"I don't see a waypoint called {waypointName}.";

        EventBus.Publish(new WaypointDeletedEvent(found));
        return $"Waypoint {found.Name} removed.";
    }

    // -----------------------------------------------------------------------
    // Tasks
    // -----------------------------------------------------------------------

    private string AddTask(string taskName)
    {
        if (string.IsNullOrWhiteSpace(taskName)) return "What should I call the new task?";
        if (_taskDetailScreen == null)
        {
            Debug.LogWarning("[CORVUS] TaskDetailScreen not assigned on CorvusARBridge.");
            return "I can't add a task right now.";
        }
        if (!_taskDetailScreen.AddTaskGroup(taskName))
            return $"I couldn't add the task {taskName}.";
        return $"Task {taskName.Trim()} added.";
    }

    private string DeleteTask(string taskName)
    {
        if (string.IsNullOrWhiteSpace(taskName)) return "Which task should I remove?";
        if (_taskDetailScreen == null)
        {
            Debug.LogWarning("[CORVUS] TaskDetailScreen not assigned on CorvusARBridge.");
            return "I can't modify tasks right now.";
        }
        if (!_taskDetailScreen.DeleteTaskGroupByName(taskName, out string resolved))
            return $"I don't see a task called {taskName}.";
        return $"Task {resolved} removed.";
    }

    private string CompleteTask(string taskName)
    {
        if (_taskDetailScreen == null)
        {
            Debug.LogWarning("[CORVUS] TaskDetailScreen not assigned on CorvusARBridge.");
            return "I can't update tasks right now.";
        }

        if (!string.IsNullOrWhiteSpace(taskName) &&
            _taskDetailScreen.CompleteByName(taskName, out string resolved))
        {
            return $"Marked {resolved} as complete.";
        }

        // Fallback: advance the currently active group's next step
        _taskDetailScreen.MarkStepDone();
        return "Marked the next step as complete.";
    }
}
