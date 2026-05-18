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
