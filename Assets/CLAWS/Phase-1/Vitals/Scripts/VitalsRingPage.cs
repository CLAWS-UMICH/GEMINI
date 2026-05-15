using UnityEngine;
using TMPro;

/// <summary>
/// Drives one page of radial vitals widgets: writes the formatted value into
/// each ring's value TMP, fills the RingFull arc, and tints it red / yellow /
/// green against the thresholds in <see cref="VitalsNominalLimits"/>.
/// Subscribes to <see cref="UpdatedVitalsEvent"/> on enable.
/// </summary>
public class VitalsRingPage : MonoBehaviour
{
    public enum VitalsRingMetric
    {
        SuitPressureTotal,
        SuitPressureOxy,
        SuitPressureCo2,
        HelmetPressureCo2,
        SuitPressureOther,

        OxyPriStorage,
        OxySecStorage,
        OxyPriPressure,
        OxySecPressure,
        OxyTimeLeft,

        FanPriRpm,
        FanSecRpm,
        ScrubberACo2,
        ScrubberBCo2,

        HeartRate,
        Temperature,
        OxyConsumption,
        Co2Production,

        BattTimeLeft,
        CoolantStorage,
        CoolantLiquidPressure,
        CoolantGasPressure
    }

    [System.Serializable]
    public struct RingBinding
    {
        public VitalsRingMetric metric;
        public TextMeshPro valueText;
        public SpriteRenderer ringFull;
        [Tooltip("Value at which the radial ring is fully drawn. Use the metric's nominal max from eva-telemetry-ranges.pdf.")]
        public float arcMax;
        [Tooltip("C# numeric format string for the value text (e.g. F1, F0, N0). Ignored for time-based metrics.")]
        public string valueFormat;
    }

    [SerializeField] private RingBinding[] bindings;

    private const float ArcSpan = 302f;

    private Subscription<UpdatedVitalsEvent> vitalsSubscription;

    private void Awake()
    {
        ApplyDefaultColors();
    }

    private void OnEnable()
    {
        vitalsSubscription = EventBus.Subscribe<UpdatedVitalsEvent>(OnVitalsUpdated);
        if (AstronautInstance.instance != null && AstronautInstance.User != null && AstronautInstance.User.vitals != null)
        {
            ApplyVitals(AstronautInstance.User.vitals);
        }
    }

    private void OnDisable()
    {
        if (vitalsSubscription != null)
        {
            EventBus.Unsubscribe(vitalsSubscription);
            vitalsSubscription = null;
        }
    }

    private void OnVitalsUpdated(UpdatedVitalsEvent e)
    {
        if (e?.vitals != null)
            ApplyVitals(e.vitals);
    }

    private void ApplyDefaultColors()
    {
        if (bindings == null) return;
        foreach (RingBinding b in bindings)
        {
            if (b.ringFull != null)
                VitalsUiTrafficColors.ApplyRingColor(b.ringFull, VitalsUiTrafficColors.Good);
        }
    }

    private void ApplyVitals(Vitals v)
    {
        if (bindings == null || v == null) return;

        foreach (RingBinding b in bindings)
        {
            float value = GetValue(b.metric, v);

            if (b.valueText != null)
                b.valueText.text = FormatValue(b.metric, value, b.valueFormat);

            if (b.ringFull != null)
            {
                float arcMax = b.arcMax > 0f ? b.arcMax : 1f;
                float arc = (1f - Mathf.Clamp01(value / arcMax)) * ArcSpan;
                Material mat = b.ringFull.material;
                if (mat != null)
                    mat.SetFloat("_Arc1", arc);

                VitalsUiTrafficColors.ApplyRingColor(b.ringFull, Evaluate(b.metric, value));
            }
        }
    }

    private static float GetValue(VitalsRingMetric metric, Vitals v)
    {
        switch (metric)
        {
            case VitalsRingMetric.SuitPressureTotal:     return (float)v.suit_pressure_total;
            case VitalsRingMetric.SuitPressureOxy:       return (float)v.suit_pressure_oxy;
            case VitalsRingMetric.SuitPressureCo2:       return (float)v.suit_pressure_co2;
            case VitalsRingMetric.HelmetPressureCo2:     return (float)v.helmet_pressure_co2;
            case VitalsRingMetric.SuitPressureOther:     return (float)v.suit_pressure_other;

            case VitalsRingMetric.OxyPriStorage:         return (float)v.oxy_pri_storage;
            case VitalsRingMetric.OxySecStorage:         return (float)v.oxy_sec_storage;
            case VitalsRingMetric.OxyPriPressure:        return (float)v.oxy_pri_pressure;
            case VitalsRingMetric.OxySecPressure:        return (float)v.oxy_sec_pressure;
            case VitalsRingMetric.OxyTimeLeft:           return v.oxy_time_left;

            case VitalsRingMetric.FanPriRpm:             return (float)v.fan_pri_rpm;
            case VitalsRingMetric.FanSecRpm:             return (float)v.fan_sec_rpm;
            case VitalsRingMetric.ScrubberACo2:          return (float)v.scrubber_a_co2_storage;
            case VitalsRingMetric.ScrubberBCo2:          return (float)v.scrubber_b_co2_storage;

            case VitalsRingMetric.HeartRate:             return (float)v.heart_rate;
            case VitalsRingMetric.Temperature:           return (float)v.temperature;
            case VitalsRingMetric.OxyConsumption:        return (float)v.oxy_consumption;
            case VitalsRingMetric.Co2Production:         return (float)v.co2_production;

            case VitalsRingMetric.BattTimeLeft:          return (float)v.batt_time_left;
            case VitalsRingMetric.CoolantStorage:        return (float)v.coolant_m;
            case VitalsRingMetric.CoolantLiquidPressure: return (float)v.coolant_liquid_pressure;
            case VitalsRingMetric.CoolantGasPressure:    return (float)v.coolant_gas_pressure;

            default: return 0f;
        }
    }

    private static string FormatValue(VitalsRingMetric metric, float value, string fmt)
    {
        if (metric == VitalsRingMetric.OxyTimeLeft || metric == VitalsRingMetric.BattTimeLeft)
        {
            int seconds = Mathf.Max(0, Mathf.RoundToInt(value));
            int hours = seconds / 3600;
            int minutes = (seconds % 3600) / 60;
            return $"{hours} hr {minutes} m";
        }

        if (string.IsNullOrEmpty(fmt))
            fmt = "F1";
        return value.ToString(fmt);
    }

    private Color Evaluate(VitalsRingMetric metric, float value)
    {
        switch (metric)
        {
            // Band: both bounds matter (red outside, yellow near either edge).
            case VitalsRingMetric.SuitPressureTotal:
                return VitalsUiTrafficColors.EvaluateBand(value, VitalsNominalLimits.SuitPresTotalMin, VitalsNominalLimits.SuitPresTotalMax);
            case VitalsRingMetric.SuitPressureOxy:
                return VitalsUiTrafficColors.EvaluateBand(value, VitalsNominalLimits.SuitPresOxyMin, VitalsNominalLimits.SuitPresOxyMax);
            case VitalsRingMetric.OxyPriPressure:
            case VitalsRingMetric.OxySecPressure:
                return VitalsUiTrafficColors.EvaluateBand(value, VitalsNominalLimits.OxyPresMin, VitalsNominalLimits.OxyPresMax);
            case VitalsRingMetric.HeartRate:
                return VitalsUiTrafficColors.EvaluateBand(value, VitalsNominalLimits.HeartRateMin, VitalsNominalLimits.HeartRateMax);
            case VitalsRingMetric.Temperature:
                return VitalsUiTrafficColors.EvaluateBand(value, VitalsNominalLimits.TempMin, VitalsNominalLimits.TempMax);
            case VitalsRingMetric.OxyConsumption:
                return VitalsUiTrafficColors.EvaluateBand(value, VitalsNominalLimits.OxyConsumMin, VitalsNominalLimits.OxyConsumMax);
            case VitalsRingMetric.Co2Production:
                return VitalsUiTrafficColors.EvaluateBand(value, VitalsNominalLimits.Co2ProdMin, VitalsNominalLimits.Co2ProdMax);
            case VitalsRingMetric.FanPriRpm:
            case VitalsRingMetric.FanSecRpm:
                return VitalsUiTrafficColors.EvaluateBand(value, VitalsNominalLimits.FanSpeedMin, VitalsNominalLimits.FanSpeedMax);
            case VitalsRingMetric.CoolantLiquidPressure:
                return VitalsUiTrafficColors.EvaluateBand(value, VitalsNominalLimits.CoolLiqMin, VitalsNominalLimits.CoolLiqMax);

            case VitalsRingMetric.SuitPressureCo2:
                return VitalsUiTrafficColors.EvaluateCeiling(value, VitalsNominalLimits.SuitPresCo2Max);
            case VitalsRingMetric.HelmetPressureCo2:
                return VitalsUiTrafficColors.EvaluateCeiling(value, VitalsNominalLimits.HelmetPresCo2Max);
            case VitalsRingMetric.SuitPressureOther:
                return VitalsUiTrafficColors.EvaluateCeiling(value, VitalsNominalLimits.SuitPresOtherMax);
            case VitalsRingMetric.CoolantGasPressure:
                return VitalsUiTrafficColors.EvaluateCeiling(value, VitalsNominalLimits.CoolGasMax);
            case VitalsRingMetric.ScrubberACo2:
            case VitalsRingMetric.ScrubberBCo2:
                return VitalsUiTrafficColors.EvaluateCeiling(value, VitalsNominalLimits.ScrubberCo2StorMax);

            case VitalsRingMetric.OxyPriStorage:
            case VitalsRingMetric.OxySecStorage:
                return VitalsUiTrafficColors.EvaluateFloor(value, VitalsNominalLimits.OxyStorMin);
            case VitalsRingMetric.CoolantStorage:
                return VitalsUiTrafficColors.EvaluateFloor(value, VitalsNominalLimits.CoolStorMin);
            case VitalsRingMetric.OxyTimeLeft:
                return VitalsUiTrafficColors.EvaluateFloor(value, VitalsNominalLimits.OxyTimeMin);
            case VitalsRingMetric.BattTimeLeft:
                return VitalsUiTrafficColors.EvaluateFloor(value, VitalsNominalLimits.BattTimeMin);

            default:
                return VitalsUiTrafficColors.Good;
        }
    }
}
