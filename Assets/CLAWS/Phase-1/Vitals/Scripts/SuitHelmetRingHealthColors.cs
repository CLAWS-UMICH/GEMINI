using UnityEngine;

/// <summary>
/// Traffic-light tint for helmet pressure RingFull sprites. Uses <see cref="VitalsNominalLimits"/> and
/// <see cref="UpdatedVitalsEvent"/> only — do not attach <see cref="VitalsController"/> to the helmet root.
/// </summary>
public class SuitHelmetRingHealthColors : MonoBehaviour
{
    public enum HelmetRingMetric
    {
        SuitPressureTotal = 0,
        SuitPressureOxy = 1,
        SuitPressureCo2 = 2,
        HelmetPressureCo2 = 3,
        SuitPressureOther = 4
    }

    [System.Serializable]
    public struct RingBinding
    {
        public SpriteRenderer ring;
        public HelmetRingMetric metric;
    }

    [SerializeField] private RingBinding[] rings;

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
        if (rings == null)
            return;
        foreach (RingBinding rb in rings)
        {
            if (rb.ring != null)
                VitalsUiTrafficColors.ApplyRingColor(rb.ring, VitalsUiTrafficColors.Good);
        }
    }

    private void ApplyVitals(Vitals v)
    {
        if (rings == null)
            return;
        foreach (RingBinding rb in rings)
        {
            if (rb.ring == null)
                continue;
            float value = GetValue(rb.metric, v);
            VitalsUiTrafficColors.ApplyRingColor(rb.ring, Evaluate(rb.metric, value));
        }
    }

    private static float GetValue(HelmetRingMetric metric, Vitals v)
    {
        switch (metric)
        {
            case HelmetRingMetric.SuitPressureTotal:
                return (float)v.suit_pressure_total;
            case HelmetRingMetric.SuitPressureOxy:
                return (float)v.suit_pressure_oxy;
            case HelmetRingMetric.SuitPressureCo2:
                return (float)v.suit_pressure_co2;
            case HelmetRingMetric.HelmetPressureCo2:
                return (float)v.helmet_pressure_co2;
            case HelmetRingMetric.SuitPressureOther:
                return (float)v.suit_pressure_other;
            default:
                return 0f;
        }
    }

    private Color Evaluate(HelmetRingMetric metric, float value)
    {
        switch (metric)
        {
            case HelmetRingMetric.SuitPressureTotal:
                return VitalsUiTrafficColors.EvaluateBand(value, VitalsNominalLimits.SuitPresTotalMin, VitalsNominalLimits.SuitPresTotalMax);
            case HelmetRingMetric.SuitPressureOxy:
                return VitalsUiTrafficColors.EvaluateBand(value, VitalsNominalLimits.SuitPresOxyMin, VitalsNominalLimits.SuitPresOxyMax);
            case HelmetRingMetric.SuitPressureCo2:
                return VitalsUiTrafficColors.EvaluateCeiling(value, VitalsNominalLimits.SuitPresCo2Max);
            case HelmetRingMetric.HelmetPressureCo2:
                return VitalsUiTrafficColors.EvaluateCeiling(value, VitalsNominalLimits.HelmetPresCo2Max);
            case HelmetRingMetric.SuitPressureOther:
                return VitalsUiTrafficColors.EvaluateCeiling(value, VitalsNominalLimits.SuitPresOtherMax);
            default:
                return VitalsUiTrafficColors.Good;
        }
    }
}