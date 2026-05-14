#ifndef CLAWS_RADIAL_WEDGE_RIM_INCLUDED
#define CLAWS_RADIAL_WEDGE_RIM_INCLUDED

half ClawsRadialWedgeRimAmount(
    half2 uv,
    half rimUvMode,
    half angleSpanRad,
    half innerRadius,
    half outerRadius,
    half rimWidthWorld,
    half rimSoftnessWorld,
    half rimWidthUv,
    half rimSoftnessUv)
{
    half rimAmt = 0;

    if (rimUvMode > 0.5h)
    {
        half r = length(uv - half2(0.5h, 0.5h)) * 2;
        rimAmt = smoothstep(1 - rimWidthUv - rimSoftnessUv, 1 - rimWidthUv, r);
    }
    else if (angleSpanRad > 0.0001h)
    {
        half rWorld = lerp(innerRadius, outerRadius, uv.y);
        half radialSpan = outerRadius - innerRadius;
        half distRadial = min(uv.x, 1 - uv.x) * angleSpanRad * rWorld;
        half distArc = min(uv.y, 1 - uv.y) * radialSpan;
        half edgeDist = min(distRadial, distArc);
        rimAmt = 1 - smoothstep(rimWidthWorld, rimWidthWorld + rimSoftnessWorld, edgeDist);
    }
    else
    {
        half edge = min(min(uv.x, 1 - uv.x), min(uv.y, 1 - uv.y));
        rimAmt = 1 - smoothstep(rimWidthUv, rimWidthUv + rimSoftnessUv, edge);
    }

    return rimAmt;
}

#endif
