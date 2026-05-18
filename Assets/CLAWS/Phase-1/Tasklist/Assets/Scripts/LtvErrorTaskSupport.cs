using System;
using System.Collections.Generic;
using System.Text.RegularExpressions;

[Serializable]
public class LtvErrorProcedure
{
    public string code;
    public string description;
    public bool needs_resolved;
    public string[] procedures;
}

public static class LtvErrorTaskSupport
{
    public const int MaxTaskCount = 5;

    /// <summary>TSS2026 UDP POST mapping: command = BaseLtvErrorUdpCommand + procedureIndex (see TSS2026 src/data.h udp_command_mappings).</summary>
    public const int BaseLtvErrorUdpCommand = 2023;

    /// <summary>Valid procedure indices for UDP POST are 0 through this value (inclusive).</summary>
    public const int MaxLtvProcedureIndex = 7;

    private const string RecoveryModeCode = "4800";

    /// <summary>
    /// Order matches <c>TSS2026/data/LTV_ERRORS.json</c> <c>error_procedures</c> array and partial GET responses
    /// (recovery-only still returns index 0 / 4800).
    /// </summary>
    private static readonly string[] LtvErrorCodesByServerIndex =
    {
        "4800", "4509", "1969", "3452", "4968", "2441", "2235", "4280"
    };

    public static readonly Dictionary<string, string[]> MinimizedProceduresByCode = new Dictionary<string, string[]>
    {
        { "4800", new string[] {
            "Inspect for physical damage",
            "Locate PDD (PDD9900xxxx)",
            "Verify recovery mode on PDD",
            "Fix other errors first",
            "Turn OFF MPS, GNC, CDH via POPS",
            "Locate SFA button",
            "Press and release SFA",
            "Turn POM OFF, verify blue light",
            "Open EBD switch cover",
            "Press and hold CSR",
            "Turn EBD ON while holding CSR",
            "Release CSR",
            "Locate SMC, wait for green light",
            "Turn EBD OFF",
            "Close EBD cover",
            "Verify blinking red SMC light",
            "Turn ON MPS, GNC, CDH via POPS",
            "Open SMC CTRL cover",
            "Hold ALT, turn CTRL ON",
            "Verify red SMC light is off",
            "Release ALT",
            "Push SMC TEST up and hold PDD CSR",
            "Release CSR when green SMC light blinks",
            "Hold ALT, turn CTRL OFF",
            "Verify solid green light",
            "Release ALT, close CTRL cover",
            "Open RECO cover on PDD",
            "Turn RECO OFF, close cover",
            "Verify exit from recovery mode",
            "Announce ERM success"
        }},
        { "4509", new string[] {
            "Locate NAV (NAV5500xxxx)",
            "Set to HAND mode, verify blue light",
            "Locate LIDAR RESET",
            "Hold LIDAR RESET 5s until red",
            "Release LIDAR RESET when SMC green",
            "Locate NAV RESET",
            "Hold NAV RESET 5s until red",
            "Release NAV RESET when SMC red",
            "Set NAV control OFF for 5s",
            "Set control to HAND",
            "Verify blue mode light",
            "Locate ASITS switch",
            "Turn ASITS ON",
            "Verify yellow light",
            "Locate ANAV BLOCK",
            "Turn ANAV BLOCK ON, verify blue light",
            "Locate ANAV RTH",
            "Turn ANAV RTH ON, verify blue light",
            "Locate ACA dial",
            "Turn ACA counterclockwise until red",
            "Turn ANAV BLOCK OFF",
            "Turn ASITS OFF",
            "Locate COMM switch",
            "Set COMM to SEC, verify blue light",
            "Verify SMC lights off",
            "Set control AUTO, verify green light",
            "Announce successful NAV Restart"
        }},
        { "1969", new string[] {
            "Locate Backup Fuse Housing",
            "Lock open enclosure lid",
            "Beware of hazards, steady enclosure",
            "Remove fuse disconnect",
            "Remove protective barrier",
            "Remove and discard old fuses",
            "Get replacement fuses",
            "Load new fuse in tool",
            "Insert new fuse",
            "Repeat for second fuse",
            "Replace protective barrier",
            "Reinsert fuse disconnect",
            "Close enclosure lid",
            "Announce Backup Fuse Error resolved"
        }},
        { "3452", new string[] {
            "Locate ACM component",
            "Optimize PHS knob",
            "Optimize MOD knob",
            "Optimize AMP knob",
            "Tune until green indicator lights",
            "Verify blinking red SMC light",
            "Open SMC CTRL cover",
            "Hold ALT, turn CTRL ON",
            "Verify red light off, release ALT",
            "Hold ALT and RESET",
            "Verify red and green lights",
            "Release both buttons",
            "Push TEST down until green blinks",
            "Hold ALT, turn CTRL OFF",
            "Release ALT, close CTRL cover",
            "Verify green SMC light",
            "Announce Poor Comms RSSI resolved"
        }},
        { "4968", new string[] {
            "Turn OFF MPS, GNC, VSI, CDH via POPS",
            "Check for loose cables",
            "Remove loose cables fully",
            "Reinsert cables firmly",
            "Reseat all cables if none loose",
            "Turn ON MPS, GNC, VSI, CDH via POPS",
            "Wait 5-10s for error clear",
            "Announce Subsystem Power Bus error resolved"
        }},
        { "2441", new string[] {
            "Turn CDH OFF via POPS",
            "Wait 5 seconds",
            "Turn CDH ON",
            "Locate comms control component",
            "Proceed if RSSI not maximum",
            "Optimize PHS knob",
            "Optimize MOD knob",
            "Optimize AMP knob",
            "Tune until green indicator lights",
            "Verify blinking red SMC light",
            "Hold ALT, turn CTRL ON",
            "Release ALT when red light off",
            "Hold ALT and RESET",
            "Verify red and green lights",
            "Release both buttons",
            "Push TEST down until green blinks",
            "Hold ALT, turn CTRL OFF",
            "Release ALT, close CTRL cover",
            "Verify green SMC light",
            "Announce Comms Reboot steps complete"
        }},
        { "2235", new string[] {
            "Locate dust sensor",
            "Unscrew sensor counterclockwise",
            "Set aside old sensor",
            "Remove cap from replacement sensor",
            "Screw in new sensor clockwise",
            "Announce Dust Sensor error resolved"
        }},
        { "4280", new string[] {
            "Locate SMPD (SMPD2200xxxx)",
            "Verify green SMPD light",
            "Locate SPR (SPR2200xxxx)",
            "Note illuminated red SPR lights",
            "Turn OFF MPS via POPS",
            "Remove power bus from socket",
            "Remove fuse for lit indicator",
            "Insert replacement fuse",
            "Reinsert power bus",
            "Turn ON MPS",
            "Verify green SMPD, no red SPR lights",
            "Announce Small Fuse Box steps complete"
        }}
    };

    public static void ApplyMinimizedProcedures(LtvErrorProcedure[] procedures)
    {
        if (procedures == null) return;
        foreach (var p in procedures)
        {
            if (p != null && MinimizedProceduresByCode.TryGetValue(p.code, out string[] minimized))
            {
                p.procedures = minimized;
            }
        }
    }

    private static readonly Regex StepStartPattern = new Regex(
        @"(?<![\d.])(\d{1,2})\.\s*(?=[A-Za-z(])",
        RegexOptions.Compiled);

    public static List<LtvErrorProcedure> FilterActive(IEnumerable<LtvErrorProcedure> procedures)
    {
        var active = new List<LtvErrorProcedure>();
        if (procedures == null)
            return active;

        foreach (LtvErrorProcedure procedure in procedures)
        {
            if (procedure == null)
                continue;
            if (!procedure.needs_resolved)
                continue;
            if (string.IsNullOrWhiteSpace(procedure.code))
                continue;

            active.Add(procedure);
        }

        return active;
    }

    /// <summary>True if recovery mode (4800) is still marked as needing resolution.</summary>
    public static bool IsRecoveryModeActive(IEnumerable<LtvErrorProcedure> procedures)
    {
        if (procedures == null)
            return false;

        foreach (LtvErrorProcedure procedure in procedures)
        {
            if (procedure == null)
                continue;
            if (IsRecoveryMode(procedure) && procedure.needs_resolved)
                return true;
        }

        return false;
    }

    /// <summary>True when UDP GET 3 returned only the first error_procedures entry (TSS recovery-only response).</summary>
    public static bool IsRecoveryOnlyUdpSnapshot(LtvErrorProcedure[] procedures)
    {
        return procedures != null && procedures.Length <= 1;
    }

    /// <summary>True when UDP GET 3 returned the full multi-entry LTV_ERRORS list (post-recovery).</summary>
    public static bool HasFullLtvErrorsSnapshot(LtvErrorProcedure[] procedures)
    {
        return !IsRecoveryOnlyUdpSnapshot(procedures);
    }

    /// <summary>True if any entry in the full LTV_ERRORS snapshot still has needs_resolved (work remaining).</summary>
    public static bool HasAnyProcedureNeedsResolved(LtvErrorProcedure[] procedures)
    {
        if (procedures == null)
            return false;

        foreach (LtvErrorProcedure procedure in procedures)
        {
            if (procedure != null && procedure.needs_resolved)
                return true;
        }

        return false;
    }

    /// <summary>
    /// Use for GET 3 cadence: keep polling while work remains or the UDP snapshot may still be recovery-only (length le 1),
    /// so we have not yet seen the full multi-row LTV_ERRORS list. A legitimately single-row mission file would keep polling until optional polls; see plan notes.
    /// </summary>
    public static bool ShouldKeepPollingLtvErrors(LtvErrorProcedure[] procedures)
    {
        return HasAnyProcedureNeedsResolved(procedures) || IsRecoveryOnlyUdpSnapshot(procedures);
    }

    public static List<LtvErrorProcedure> SelectTopTasks(IEnumerable<LtvErrorProcedure> procedures)
    {
        List<LtvErrorProcedure> active = FilterActive(procedures);
        active.Sort(ComparePriority);

        if (active.Count > MaxTaskCount)
            active.RemoveRange(MaxTaskCount, active.Count - MaxTaskCount);

        return active;
    }

    public static string BuildTaskTitle(LtvErrorProcedure procedure)
    {
        if (procedure == null)
            return string.Empty;

        string code = string.IsNullOrWhiteSpace(procedure.code)
            ? "LTV"
            : procedure.code.Trim();
        string description = string.IsNullOrWhiteSpace(procedure.description)
            ? "LTV Error"
            : procedure.description.Trim();

        return $"{code} - {description}";
    }

    public static string[] ParseProcedureSteps(string[] procedures)
    {
        var steps = new List<string>();
        if (procedures != null)
        {
            foreach (string procedure in procedures)
                AddParsedSteps(procedure, steps);
        }

        if (steps.Count == 0)
            steps.Add("No procedure steps available from TSS.");

        return steps.ToArray();
    }

    /// <summary>Returns the zero-based index in <c>LTV_ERRORS.json</c> used by <c>ltv_errors.error_procedures.&lt;index&gt;.needs_resolved</c>.</summary>
    public static bool TryGetProcedureIndex(string code, out int procedureIndex)
    {
        procedureIndex = -1;
        if (string.IsNullOrWhiteSpace(code))
            return false;

        string needle = code.Trim();
        for (int i = 0; i < LtvErrorCodesByServerIndex.Length; i++)
        {
            if (string.Equals(LtvErrorCodesByServerIndex[i], needle, StringComparison.Ordinal))
            {
                procedureIndex = i;
                return true;
            }
        }

        return false;
    }

    /// <summary>TSS2026 UDP POST command for updating <c>needs_resolved</c> at <paramref name="procedureIndex"/>.</summary>
    public static bool TryGetUdpCommandForProcedureIndex(int procedureIndex, out int udpCommand)
    {
        udpCommand = 0;
        if (procedureIndex < 0 || procedureIndex > MaxLtvProcedureIndex)
            return false;
        udpCommand = BaseLtvErrorUdpCommand + procedureIndex;
        return true;
    }

    public static bool TryGetUdpCommandForCode(string code, out int udpCommand)
    {
        udpCommand = 0;
        return TryGetProcedureIndex(code, out int idx) && TryGetUdpCommandForProcedureIndex(idx, out udpCommand);
    }

    private static void AddParsedSteps(string procedure, List<string> steps)
    {
        if (string.IsNullOrWhiteSpace(procedure))
            return;

        string normalized = Regex.Replace(procedure.Trim(), @"\s+", " ");
        MatchCollection matches = StepStartPattern.Matches(normalized);
        if (matches.Count == 0)
        {
            steps.Add(normalized);
            return;
        }

        for (int i = 0; i < matches.Count; i++)
        {
            int start = matches[i].Index;
            int end = i + 1 < matches.Count ? matches[i + 1].Index : normalized.Length;
            string step = normalized.Substring(start, end - start).Trim();
            if (!string.IsNullOrEmpty(step))
                steps.Add(step);
        }
    }

    private static int ComparePriority(LtvErrorProcedure a, LtvErrorProcedure b)
    {
        bool aRecovery = IsRecoveryMode(a);
        bool bRecovery = IsRecoveryMode(b);
        if (aRecovery != bRecovery)
            return aRecovery ? -1 : 1;

        int aCriticality = GetDigit(a?.code, 0);
        int bCriticality = GetDigit(b?.code, 0);
        int criticalityCompare = bCriticality.CompareTo(aCriticality);
        if (criticalityCompare != 0)
            return criticalityCompare;

        int aSubsystem = GetDigit(a?.code, 1);
        int bSubsystem = GetDigit(b?.code, 1);
        int subsystemCompare = bSubsystem.CompareTo(aSubsystem);
        if (subsystemCompare != 0)
            return subsystemCompare;

        int codeCompare = string.Compare(a?.code, b?.code, StringComparison.Ordinal);
        if (codeCompare != 0)
            return codeCompare;

        return string.Compare(a?.description, b?.description, StringComparison.Ordinal);
    }

    private static bool IsRecoveryMode(LtvErrorProcedure procedure)
    {
        return string.Equals(
            procedure?.code?.Trim(),
            RecoveryModeCode,
            StringComparison.Ordinal);
    }

    private static int GetDigit(string code, int index)
    {
        if (string.IsNullOrEmpty(code) || code.Length <= index)
            return -1;

        char c = code[index];
        return c >= '0' && c <= '9' ? c - '0' : -1;
    }
}
