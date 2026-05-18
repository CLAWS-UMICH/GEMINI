using UnityEngine;

/// <summary>
/// Display and threshold metadata for each <see cref="VitalsRingPage.VitalsRingMetric"/>.
/// </summary>
public static class VitalsMetricSpec
{
    public enum FillMode
    {
        HigherIsBetter,
        LowerIsBetter,
        Band
    }

    public enum ColorMode
    {
        Floor,
        Ceiling,
        Band,
        BandWithNominal
    }

    public readonly struct Spec
    {
        public readonly string Unit;
        public readonly float Min;
        public readonly float Nominal;
        public readonly float Max;
        public readonly FillMode Fill;
        public readonly ColorMode Color;
        public readonly string ValueFormat;

        public bool HasNominal => !float.IsNaN(Nominal);

        public Spec(
            string unit,
            float min,
            float nominal,
            float max,
            FillMode fill,
            ColorMode color,
            string valueFormat)
        {
            Unit = unit;
            Min = min;
            Nominal = nominal;
            Max = max;
            Fill = fill;
            Color = color;
            ValueFormat = valueFormat;
        }
    }

    private static readonly Spec[] Table = BuildTable();

    public static Spec Get(VitalsRingPage.VitalsRingMetric metric)
    {
        int i = (int)metric;
        if (i < 0 || i >= Table.Length)
            return default;
        return Table[i];
    }

    public static float ComputeArcFill(float value, in Spec spec)
    {
        const float arcSpan = VitalsRingPage.ArcSpanDegrees;

        switch (spec.Fill)
        {
            case FillMode.LowerIsBetter:
            {
                float max = spec.Max > 0f ? spec.Max : 1f;
                float t = Mathf.Clamp01(value / max);
                return t * arcSpan;
            }
            default:
            {
                float min = spec.Min;
                float max = spec.Max > min ? spec.Max : min + 1f;
                float t = Mathf.Clamp01((value - min) / (max - min));
                return (1f - t) * arcSpan;
            }
        }
    }

    public static Color EvaluateColor(float value, in Spec spec)
    {
        switch (spec.Color)
        {
            case ColorMode.Floor:
                return VitalsUiTrafficColors.EvaluateFloor(value, spec.Min);
            case ColorMode.Ceiling:
                return VitalsUiTrafficColors.EvaluateCeiling(value, spec.Max);
            case ColorMode.BandWithNominal when spec.HasNominal:
                return VitalsUiTrafficColors.EvaluateBandWithNominal(
                    value, spec.Min, spec.Nominal, spec.Max);
            default:
                return VitalsUiTrafficColors.EvaluateBand(value, spec.Min, spec.Max);
        }
    }

    private static Spec[] BuildTable()
    {
        int count = System.Enum.GetValues(typeof(VitalsRingPage.VitalsRingMetric)).Length;
        var table = new Spec[count];
        float nan = float.NaN;

        table[(int)VitalsRingPage.VitalsRingMetric.SuitPressureTotal] =
            new Spec("psi", VitalsNominalLimits.SuitPresTotalMin, 4f, VitalsNominalLimits.SuitPresTotalMax,
                FillMode.Band, ColorMode.Band, "F1");
        table[(int)VitalsRingPage.VitalsRingMetric.SuitPressureOxy] =
            new Spec("psi", VitalsNominalLimits.SuitPresOxyMin, 4f, VitalsNominalLimits.SuitPresOxyMax,
                FillMode.Band, ColorMode.Band, "F1");
        table[(int)VitalsRingPage.VitalsRingMetric.SuitPressureCo2] =
            new Spec("psi", 0f, 0f, VitalsNominalLimits.SuitPresCo2Max,
                FillMode.LowerIsBetter, ColorMode.Ceiling, "F2");
        table[(int)VitalsRingPage.VitalsRingMetric.HelmetPressureCo2] =
            new Spec("psi", 0f, 0f, VitalsNominalLimits.HelmetPresCo2Max,
                FillMode.LowerIsBetter, ColorMode.Ceiling, "F2");
        table[(int)VitalsRingPage.VitalsRingMetric.SuitPressureOther] =
            new Spec("psi", 0f, 0f, VitalsNominalLimits.SuitPresOtherMax,
                FillMode.LowerIsBetter, ColorMode.Ceiling, "F1");

        table[(int)VitalsRingPage.VitalsRingMetric.OxyPriStorage] =
            new Spec("%", VitalsNominalLimits.OxyStorMin, nan, VitalsNominalLimits.OxyStorMax,
                FillMode.HigherIsBetter, ColorMode.Floor, "F0");
        table[(int)VitalsRingPage.VitalsRingMetric.OxySecStorage] =
            new Spec("%", VitalsNominalLimits.OxyStorMin, nan, VitalsNominalLimits.OxyStorMax,
                FillMode.HigherIsBetter, ColorMode.Floor, "F0");
        table[(int)VitalsRingPage.VitalsRingMetric.OxyPriPressure] =
            new Spec("psi", VitalsNominalLimits.OxyPresMin, nan, VitalsNominalLimits.OxyPresMax,
                FillMode.Band, ColorMode.Band, "F0");
        table[(int)VitalsRingPage.VitalsRingMetric.OxySecPressure] =
            new Spec("psi", VitalsNominalLimits.OxyPresMin, nan, VitalsNominalLimits.OxyPresMax,
                FillMode.Band, ColorMode.Band, "F0");

        table[(int)VitalsRingPage.VitalsRingMetric.PrimaryBatteryLevel] =
            new Spec("%", VitalsNominalLimits.BattLevelMin, nan, VitalsNominalLimits.BattLevelMax,
                FillMode.HigherIsBetter, ColorMode.Floor, "F0");
        table[(int)VitalsRingPage.VitalsRingMetric.SecondaryBatteryLevel] =
            new Spec("%", VitalsNominalLimits.BattLevelMin, nan, VitalsNominalLimits.BattLevelMax,
                FillMode.HigherIsBetter, ColorMode.Floor, "F0");
        table[(int)VitalsRingPage.VitalsRingMetric.CoolantStorage] =
            new Spec("%", VitalsNominalLimits.CoolStorMin, VitalsNominalLimits.CoolStorMax, VitalsNominalLimits.CoolStorMax,
                FillMode.HigherIsBetter, ColorMode.Floor, "F0");
        table[(int)VitalsRingPage.VitalsRingMetric.CoolantLiquidPressure] =
            new Spec("psi", VitalsNominalLimits.CoolLiqMin, 500f, VitalsNominalLimits.CoolLiqMax,
                FillMode.Band, ColorMode.BandWithNominal, "F0");
        table[(int)VitalsRingPage.VitalsRingMetric.CoolantGasPressure] =
            new Spec("psi", 0f, 0f, VitalsNominalLimits.CoolGasMax,
                FillMode.LowerIsBetter, ColorMode.Ceiling, "F0");

        table[(int)VitalsRingPage.VitalsRingMetric.FanPriRpm] =
            new Spec("rpm", VitalsNominalLimits.FanSpeedMin, VitalsNominalLimits.FanSpeedMax, VitalsNominalLimits.FanSpeedMax,
                FillMode.Band, ColorMode.Band, "N0");
        table[(int)VitalsRingPage.VitalsRingMetric.FanSecRpm] =
            new Spec("rpm", VitalsNominalLimits.FanSpeedMin, VitalsNominalLimits.FanSpeedMax, VitalsNominalLimits.FanSpeedMax,
                FillMode.Band, ColorMode.Band, "N0");
        table[(int)VitalsRingPage.VitalsRingMetric.ScrubberACo2] =
            new Spec("%", 0f, nan, VitalsNominalLimits.ScrubberCo2StorMax,
                FillMode.LowerIsBetter, ColorMode.Ceiling, "F0");
        table[(int)VitalsRingPage.VitalsRingMetric.ScrubberBCo2] =
            new Spec("%", 0f, nan, VitalsNominalLimits.ScrubberCo2StorMax,
                FillMode.LowerIsBetter, ColorMode.Ceiling, "F0");

        table[(int)VitalsRingPage.VitalsRingMetric.HeartRate] =
            new Spec("bpm", VitalsNominalLimits.HeartRateMin, nan, VitalsNominalLimits.HeartRateMax,
                FillMode.Band, ColorMode.Band, "F0");
        table[(int)VitalsRingPage.VitalsRingMetric.Temperature] =
            new Spec("°C", VitalsNominalLimits.TempMin, VitalsNominalLimits.TempNominal, VitalsNominalLimits.TempMax,
                FillMode.Band, ColorMode.BandWithNominal, "F0");
        table[(int)VitalsRingPage.VitalsRingMetric.OxyConsumption] =
            new Spec("psi/min", VitalsNominalLimits.OxyConsumMin, 0.1f, VitalsNominalLimits.OxyConsumMax,
                FillMode.Band, ColorMode.BandWithNominal, "F2");
        table[(int)VitalsRingPage.VitalsRingMetric.Co2Production] =
            new Spec("psi/min", VitalsNominalLimits.Co2ProdMin, 0.1f, VitalsNominalLimits.Co2ProdMax,
                FillMode.Band, ColorMode.BandWithNominal, "F2");

        return table;
    }
}
