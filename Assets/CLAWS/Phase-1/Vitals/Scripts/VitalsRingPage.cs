using UnityEngine;
using TMPro;

/// <summary>
/// Drives one page of radial vitals widgets: writes the formatted value into
/// each ring's value TMP, fills the RingFull arc, and tints it red / yellow /
/// green against <see cref="VitalsMetricSpec"/>.
/// Subscribes to <see cref="UpdatedVitalsEvent"/> on enable.
/// </summary>
public class VitalsRingPage : MonoBehaviour
{
    public const float ArcSpanDegrees = 302f;

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

        PrimaryBatteryLevel,
        SecondaryBatteryLevel,
        CoolantStorage,
        CoolantLiquidPressure,
        CoolantGasPressure,

        FanPriRpm,
        FanSecRpm,
        ScrubberACo2,
        ScrubberBCo2,

        HeartRate,
        Temperature,
        OxyConsumption,
        Co2Production
    }

    [System.Serializable]
    public struct RingBinding
    {
        public VitalsRingMetric metric;
        public TextMeshPro valueText;
        public TextMeshPro unitText;
        public SpriteRenderer ringFull;
        [Tooltip("Legacy; arc fill is driven by VitalsMetricSpec at runtime.")]
        public float arcMax;
        [Tooltip("Overrides VitalsMetricSpec format when non-empty.")]
        public string valueFormat;
    }

    [SerializeField] private RingBinding[] bindings;

    private Subscription<UpdatedVitalsEvent> vitalsSubscription;

    private void Awake()
    {
        ResolveUnitTexts();
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

    private void ResolveUnitTexts()
    {
        if (bindings == null) return;
        for (int i = 0; i < bindings.Length; i++)
        {
            if (bindings[i].unitText != null)
                continue;
            if (bindings[i].valueText == null)
                continue;
            Transform ring = bindings[i].valueText.transform.parent;
            if (ring == null)
                continue;
            Transform unit = ring.Find("Unit");
            if (unit != null)
                bindings[i].unitText = unit.GetComponent<TextMeshPro>();
        }
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
            VitalsMetricSpec.Spec spec = VitalsMetricSpec.Get(b.metric);

            if (b.unitText != null && !string.IsNullOrEmpty(spec.Unit))
                b.unitText.text = spec.Unit;

            string fmt = string.IsNullOrEmpty(b.valueFormat) ? spec.ValueFormat : b.valueFormat;
            if (b.valueText != null)
                b.valueText.text = FormatValue(value, fmt);

            if (b.ringFull != null)
            {
                float arc = VitalsMetricSpec.ComputeArcFill(value, spec);
                Material mat = b.ringFull.material;
                if (mat != null)
                    mat.SetFloat("_Arc1", arc);

                VitalsUiTrafficColors.ApplyRingColor(b.ringFull, VitalsMetricSpec.EvaluateColor(value, spec));
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

            case VitalsRingMetric.PrimaryBatteryLevel:   return (float)v.primary_battery_level;
            case VitalsRingMetric.SecondaryBatteryLevel: return (float)v.secondary_battery_level;
            case VitalsRingMetric.CoolantStorage:        return (float)v.coolant_m;
            case VitalsRingMetric.CoolantLiquidPressure: return (float)v.coolant_liquid_pressure;
            case VitalsRingMetric.CoolantGasPressure:    return (float)v.coolant_gas_pressure;

            case VitalsRingMetric.FanPriRpm:             return (float)v.fan_pri_rpm;
            case VitalsRingMetric.FanSecRpm:             return (float)v.fan_sec_rpm;
            case VitalsRingMetric.ScrubberACo2:          return (float)v.scrubber_a_co2_storage;
            case VitalsRingMetric.ScrubberBCo2:          return (float)v.scrubber_b_co2_storage;

            case VitalsRingMetric.HeartRate:             return (float)v.heart_rate;
            case VitalsRingMetric.Temperature:           return (float)v.temperature;
            case VitalsRingMetric.OxyConsumption:        return (float)v.oxy_consumption;
            case VitalsRingMetric.Co2Production:         return (float)v.co2_production;

            default: return 0f;
        }
    }

    private static string FormatValue(float value, string fmt)
    {
        if (string.IsNullOrEmpty(fmt))
            fmt = "F1";
        return value.ToString(fmt);
    }
}
