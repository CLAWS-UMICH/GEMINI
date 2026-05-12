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
    [SerializeField] [Range(0.05f, 0.45f)] private float bandWarningFraction = 0.15f;
    [SerializeField] [Range(0.5f, 0.95f)] private float ceilingWarningFraction = 0.7f;

    private static readonly Color Good = new Color(0.2f, 0.85f, 0.25f, 1f);
    private static readonly Color Warn = new Color(0.95f, 0.85f, 0.15f, 1f);
    private static readonly Color Bad = new Color(0.95f, 0.2f, 0.2f, 1f);

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
                ApplyColor(rb.ring, Good);
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
            ApplyColor(rb.ring, Evaluate(rb.metric, value));
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
                return EvaluateBand(value, VitalsNominalLimits.SuitPresTotalMin, VitalsNominalLimits.SuitPresTotalMax);
            case HelmetRingMetric.SuitPressureOxy:
                return EvaluateBand(value, VitalsNominalLimits.SuitPresOxyMin, VitalsNominalLimits.SuitPresOxyMax);
            case HelmetRingMetric.SuitPressureCo2:
                return EvaluateCeiling(value, VitalsNominalLimits.SuitPresCo2Max);
            case HelmetRingMetric.HelmetPressureCo2:
                return EvaluateCeiling(value, VitalsNominalLimits.HelmetPresCo2Max);
            case HelmetRingMetric.SuitPressureOther:
                return EvaluateCeiling(value, VitalsNominalLimits.SuitPresOtherMax);
            default:
                return Good;
        }
    }

    private Color EvaluateBand(float value, float min, float max)
    {
        if (value < min || value > max)
            return Bad;
        float span = max - min;
        if (span <= 0f)
            return Good;
        float margin = bandWarningFraction * span;
        if (value < min + margin || value > max - margin)
            return Warn;
        return Good;
    }

    private Color EvaluateCeiling(float value, float max)
    {
        if (max <= 0f)
            return value > 0f ? Bad : Good;
        if (value > max)
            return Bad;
        if (value > ceilingWarningFraction * max)
            return Warn;
        return Good;
    }

    private static void ApplyColor(SpriteRenderer sr, Color c)
    {
        sr.color = c;
        Material mat = sr.material;
        if (mat != null && mat.HasProperty("_Color"))
            mat.SetColor("_Color", c);
    }
}