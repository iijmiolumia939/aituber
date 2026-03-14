// =============================================================================
//  AITuber/WatercolorAvatar
//  URP — "Watercolor" appearance mode.
//  Technique:
//    1. Quantised toon lighting (3 tones: lit / mid / shadow)
//    2. Edge "bleed" via screen-space UV jitter with a noise texture,
//       mimicking the soft pigment spread of real watercolour.
//    3. "Granulation" — subtle paper-grain in shadow areas.
//    4. Wet-on-wet bloom: Fresnel-based edge lightening.
//    5. Paper texture multiply (same pattern as CrosshatchSketch).
// =============================================================================
Shader "AITuber/WatercolorAvatar"
{
    Properties
    {
        [Header(Color)]
        _BaseMap        ("Base Map",       2D)    = "white" {}
        _BaseColor      ("Base Color",     Color) = (1, 1, 1, 1)
        _ShadowColor    ("Shadow Tint",    Color) = (0.45, 0.55, 0.80, 1)
        _MidColor       ("Mid Tint",       Color) = (0.75, 0.80, 0.90, 1)

        [Header(Toon Bands)]
        _LitStep        ("Lit Threshold",  Range(0,1)) = 0.65
        _MidStep        ("Mid Threshold",  Range(0,1)) = 0.30
        _BandSmooth     ("Band Smoothness",Range(0.001,0.2)) = 0.05

        [Header(Watercolor Bleed)]
        [NoScaleOffset]
        _NoiseMap       ("Noise Texture (RG offsets)", 2D) = "bump" {}
        _BleedAmount    ("Bleed Amount",   Range(0, 0.04)) = 0.012
        _BleedScale     ("Noise UV Scale", Range(0.5, 10)) = 3.0

        [Header(Paper)]
        [NoScaleOffset]
        _PaperMap       ("Paper Grain Texture", 2D) = "white" {}
        _PaperStrength  ("Paper Strength",  Range(0, 1)) = 0.18
        _GranulationStr ("Granulation (shadow only)", Range(0,1)) = 0.25

        [Header(Fresnel Bloom)]
        _WetEdge        ("Wet Edge Intensity",  Range(0, 1)) = 0.30
        _WetPower       ("Wet Edge Power",      Range(1, 8)) = 3.0

        [Header(Cull)]
        [Enum(UnityEngine.Rendering.CullMode)]
        _Cull ("Cull Mode", Float) = 2
    }

    SubShader
    {
        Tags
        {
            "RenderType"     = "Opaque"
            "RenderPipeline" = "UniversalPipeline"
            "Queue"          = "Geometry"
        }
        LOD 200

        Pass
        {
            Name "UniversalForward"
            Tags { "LightMode" = "UniversalForward" }
            Cull [_Cull]

            HLSLPROGRAM
            #pragma vertex   vert
            #pragma fragment frag
            #pragma multi_compile_fog
            #pragma multi_compile_instancing
            #pragma multi_compile _ _MAIN_LIGHT_SHADOWS _MAIN_LIGHT_SHADOWS_CASCADE

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"

            CBUFFER_START(UnityPerMaterial)
                float4 _BaseMap_ST;
                half4  _BaseColor;
                half4  _ShadowColor;
                half4  _MidColor;
                float  _LitStep;
                float  _MidStep;
                float  _BandSmooth;
                float  _BleedAmount;
                float  _BleedScale;
                float  _PaperStrength;
                float  _GranulationStr;
                float  _WetEdge;
                float  _WetPower;
            CBUFFER_END

            TEXTURE2D(_BaseMap);  SAMPLER(sampler_BaseMap);
            TEXTURE2D(_NoiseMap); SAMPLER(sampler_NoiseMap);
            TEXTURE2D(_PaperMap); SAMPLER(sampler_PaperMap);

            struct Attribs
            {
                float4 positionOS : POSITION;
                float3 normalOS   : NORMAL;
                float2 uv         : TEXCOORD0;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct Varyings
            {
                float4 positionCS  : SV_POSITION;
                float2 uv          : TEXCOORD0;
                float3 normalWS    : TEXCOORD1;
                float3 viewDirWS   : TEXCOORD2;
                float  fogFactor   : TEXCOORD3;
                UNITY_VERTEX_OUTPUT_STEREO
            };

            Varyings vert(Attribs IN)
            {
                UNITY_SETUP_INSTANCE_ID(IN);
                Varyings OUT;
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(OUT);
                VertexPositionInputs vpi = GetVertexPositionInputs(IN.positionOS.xyz);
                OUT.positionCS = vpi.positionCS;
                OUT.uv         = TRANSFORM_TEX(IN.uv, _BaseMap);
                OUT.normalWS   = TransformObjectToWorldNormal(IN.normalOS);
                OUT.viewDirWS  = GetWorldSpaceViewDir(vpi.positionWS);
                OUT.fogFactor  = ComputeFogFactor(vpi.positionCS.z);
                return OUT;
            }

            half4 frag(Varyings IN) : SV_Target
            {
                // ── Noise-based UV bleed ───────────────────────────────────
                float2 noiseUV  = IN.uv * _BleedScale + _Time.y * 0.02;
                float2 noise    = (SAMPLE_TEXTURE2D(_NoiseMap, sampler_NoiseMap, noiseUV).rg - 0.5) * 2.0;
                float2 bleedUV  = IN.uv + noise * _BleedAmount;

                // ── Albedo ────────────────────────────────────────────────
                half4 albedo    = SAMPLE_TEXTURE2D(_BaseMap, sampler_BaseMap, bleedUV) * _BaseColor;

                // ── Lambert ───────────────────────────────────────────────
                Light mainLight = GetMainLight();
                half  ndotl     = saturate(dot(IN.normalWS, mainLight.direction));

                // ── 3-band toon ───────────────────────────────────────────
                half litMask = smoothstep(_LitStep - _BandSmooth, _LitStep + _BandSmooth, ndotl);
                half midMask = smoothstep(_MidStep - _BandSmooth, _MidStep + _BandSmooth, ndotl)
                             - litMask;
                half shdMask = 1.0 - litMask - midMask;

                half3 color  = albedo.rgb * mainLight.color * (
                                  litMask * half3(1,1,1)
                                + midMask * _MidColor.rgb
                                + shdMask * _ShadowColor.rgb);

                // ── Wet edge (Fresnel brightening) ────────────────────────
                half3 N       = normalize(IN.normalWS);
                half3 V       = normalize(IN.viewDirWS);
                half  fresnel = pow(1.0 - saturate(dot(N, V)), _WetPower);
                color += fresnel * _WetEdge;

                // ── Paper + granulation ───────────────────────────────────
                float2 screenUV = IN.positionCS.xy / _ScaledScreenParams.xy;
                half   grain    = SAMPLE_TEXTURE2D(_PaperMap, sampler_PaperMap, screenUV * 4.0).r;
                color *= lerp(1.0, grain, _PaperStrength);
                // Extra granulation in shadows
                color -= shdMask * _GranulationStr * (1.0 - grain) * 0.5;

                color   = MixFog(saturate(color), IN.fogFactor);
                return half4(color, albedo.a);
            }
            ENDHLSL
        }

        Pass
        {
            Name "ShadowCaster"
            Tags { "LightMode" = "ShadowCaster" }
            ZWrite On
            ZTest  LEqual
            ColorMask 0
            Cull [_Cull]
            HLSLPROGRAM
            #pragma vertex   ShadowVert
            #pragma fragment ShadowFrag
            #pragma multi_compile_instancing
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Shadows.hlsl"
            struct ShadowAttribs  { float4 pos : POSITION; float3 normal : NORMAL; };
            struct ShadowVaryings { float4 pos : SV_POSITION; };
            float3 _LightDirection;
            ShadowVaryings ShadowVert(ShadowAttribs IN)
            {
                ShadowVaryings OUT;
                float3 posWS  = TransformObjectToWorld(IN.pos.xyz);
                float3 normWS = TransformObjectToWorldNormal(IN.normal);
                OUT.pos = TransformWorldToHClip(ApplyShadowBias(posWS, normWS, _LightDirection));
                return OUT;
            }
            half4 ShadowFrag(ShadowVaryings IN) : SV_Target { return 0; }
            ENDHLSL
        }
    }
}
