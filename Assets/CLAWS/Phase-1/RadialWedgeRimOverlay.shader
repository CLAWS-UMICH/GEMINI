Shader "CLAWS/RadialWedgeRimOverlay"
{
    Properties
    {
        _RimColor("Rim Color", Color) = (1, 1, 1, 1)
        _RimHighlight("Rim Highlight", Range(0, 1)) = 0
        _RimUvMode("Rim UV Mode", Float) = 0
        _AngleSpanRad("Angle Span Rad", Float) = 0
        _InnerRadius("Inner Radius", Float) = 0.04
        _OuterRadius("Outer Radius", Float) = 0.09
        _RimWidthWorld("Rim Width World m", Range(0.0002, 0.02)) = 0.002
        _RimSoftnessWorld("Rim Softness World m", Range(0, 0.01)) = 0.0008
        _RimWidth("Rim Width UV", Range(0.001, 0.25)) = 0.04
        _RimSoftness("Rim Softness UV", Range(0, 0.2)) = 0.02
    }

    SubShader
    {
        Tags
        {
            "RenderType" = "Transparent"
            "RenderPipeline" = "UniversalPipeline"
            "Queue" = "Transparent+10"
        }

        Pass
        {
            Name "ForwardUnlitRim"
            Tags { "LightMode" = "UniversalForward" }

            ZWrite Off
            Blend SrcAlpha OneMinusSrcAlpha
            Cull Off

            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile_instancing

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            #include "RadialWedgeRim.hlsl"

            CBUFFER_START(UnityPerMaterial)
                half4 _RimColor;
                half _RimHighlight;
                half _RimUvMode;
                half _AngleSpanRad;
                half _InnerRadius;
                half _OuterRadius;
                half _RimWidthWorld;
                half _RimSoftnessWorld;
                half _RimWidth;
                half _RimSoftness;
            CBUFFER_END

            struct Attributes
            {
                float4 positionOS : POSITION;
                float2 uv : TEXCOORD0;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float2 uv : TEXCOORD0;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            Varyings vert(Attributes input)
            {
                Varyings output;
                UNITY_SETUP_INSTANCE_ID(input);
                UNITY_TRANSFER_INSTANCE_ID(input, output);
                output.positionCS = TransformObjectToHClip(input.positionOS.xyz);
                output.uv = input.uv;
                return output;
            }

            half4 frag(Varyings input) : SV_Target
            {
                UNITY_SETUP_INSTANCE_ID(input);
                half rimAmt = ClawsRadialWedgeRimAmount(
                    input.uv,
                    _RimUvMode,
                    _AngleSpanRad,
                    _InnerRadius,
                    _OuterRadius,
                    _RimWidthWorld,
                    _RimSoftnessWorld,
                    _RimWidth,
                    _RimSoftness);
                half a = saturate(rimAmt * _RimHighlight) * _RimColor.a;
                return half4(_RimColor.rgb, a);
            }
            ENDHLSL
        }
    }
    FallBack Off
}
