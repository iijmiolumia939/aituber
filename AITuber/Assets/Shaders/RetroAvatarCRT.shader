// =============================================================================
//  AITuber/RetroAvatarCRT
//  URP — "CRT / Retro 2.5D" appearance mode.
//  Renders the avatar with:
//    - Halftone-like scanline bands (horizontal dark stripes)
//    - Horizontal colour fringe (RGB channel offset, controlled by _FringeAmount)
//    - Subtle noise/roll interference line
//    - Flicker (adjustable strength)
//    - Desaturation with a tint tilt toward green/amber phosphor
//  Lit by URP directional light (Lambert) so body volume reads.
// =============================================================================
Shader "AITuber/RetroAvatarCRT"
{
    Properties
    {
        [Header(Base)]
        _BaseMap        ("Base Map",    2D)    = "white" {}
        _BaseColor      ("Base Color",  Color) = (1,1,1,1)

        [Header(CRT)]
        _ScanlineFreq   ("Scanline Frequency",  Range(20,300))   = 120
        _ScanlineDark   ("Scanline Darkness",   Range(0, 0.8))   = 0.35
        _FringeAmount   ("Color Fringe (px≈)",  Range(0, 0.01))  = 0.003
        _Phosphor       ("Phosphor Tint (0=amber 1=green)", Range(0,1)) = 0.5
        _Desat          ("Desaturation",        Range(0, 1))     = 0.5
        _Flicker        ("Flicker Strength",    Range(0, 0.08))  = 0.03
        _RollSpeed      ("Roll-bar Speed",      Range(0, 2))     = 0.4
        _RollBand       ("Roll-bar Width",      Range(0.001,0.1))= 0.015

        [Header(Cull Alpha)]
        [Enum(UnityEngine.Rendering.CullMode)]
        _Cull           ("Cull Mode", Float) = 2
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

        // ── Forward pass ─────────────────────────────────────────────────
        Pass
        {
            Name "UniversalForward"
            Tags { "LightMode" = "UniversalForward" }
            Cull [_Cull]
            ZWrite On
            Blend Off

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
                float  _ScanlineFreq;
                half   _ScanlineDark;
                float  _FringeAmount;
                half   _Phosphor;
                half   _Desat;
                half   _Flicker;
                float  _RollSpeed;
                float  _RollBand;
            CBUFFER_END

            TEXTURE2D(_BaseMap);  SAMPLER(sampler_BaseMap);

            struct Attribs
            {
                float4 positionOS : POSITION;
                float3 normalOS   : NORMAL;
                float2 uv         : TEXCOORD0;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float2 uv         : TEXCOORD0;
                float3 normalWS   : TEXCOORD1;
                float4 fogFactor  : TEXCOORD2;
                UNITY_VERTEX_OUTPUT_STEREO
            };

            Varyings vert(Attribs IN)
            {
                UNITY_SETUP_INSTANCE_ID(IN);
                Varyings OUT;
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(OUT);
                OUT.positionCS = TransformObjectToHClip(IN.positionOS.xyz);
                OUT.uv         = TRANSFORM_TEX(IN.uv, _BaseMap);
                OUT.normalWS   = TransformObjectToWorldNormal(IN.normalOS);
                OUT.fogFactor  = ComputeFogFactor(OUT.positionCS.z);
                return OUT;
            }

            // Simple hash noise
            float hash(float2 p)
            {
                return frac(sin(dot(p, float2(127.1, 311.7))) * 43758.5453);
            }

            half4 frag(Varyings IN) : SV_Target
            {
                float2 uv = IN.uv;

                // ── Lambert lighting ──────────────────────────────────────
                Light mainLight = GetMainLight();
                half  ndotl     = saturate(dot(IN.normalWS, mainLight.direction));
                half3 lighting  = mainLight.color * (ndotl * 0.8 + 0.2);

                // ── Color fringe (chromatic aberration on U) ──────────────
                half r = SAMPLE_TEXTURE2D(_BaseMap, sampler_BaseMap, uv + float2( _FringeAmount, 0)).r;
                half g = SAMPLE_TEXTURE2D(_BaseMap, sampler_BaseMap, uv                          ).g;
                half b = SAMPLE_TEXTURE2D(_BaseMap, sampler_BaseMap, uv - float2( _FringeAmount, 0)).b;
                half a = SAMPLE_TEXTURE2D(_BaseMap, sampler_BaseMap, uv).a;
                half3 col = half3(r, g, b) * _BaseColor.rgb;

                // ── Scanlines ─────────────────────────────────────────────
                float scanline = abs(sin(uv.y * _ScanlineFreq * 3.14159));
                col *= 1.0 - _ScanlineDark * (1.0 - scanline * scanline);

                // ── Roll bar ──────────────────────────────────────────────
                float rollY     = frac(uv.y - _Time.y * _RollSpeed);
                float rollMask  = 1.0 - smoothstep(0.0, _RollBand, rollY)
                                      * smoothstep(_RollBand * 2.0, _RollBand, rollY);
                col *= 1.0 - 0.5 * rollMask;

                // ── Phosphor desaturation & tint ──────────────────────────
                half  luma   = dot(col, half3(0.299, 0.587, 0.114));
                // 0=amber(1,0.8,0.3) 1=green(0.15,1,0.2)
                half3 amber  = half3(1.0, 0.80, 0.30);
                half3 green  = half3(0.15, 1.0, 0.20);
                half3 tint   = lerp(amber, green, _Phosphor);
                half3 desCol = luma * tint;
                col  = lerp(col, desCol, _Desat);

                // ── Flicker ───────────────────────────────────────────────
                float fk = 1.0 - _Flicker * hash(float2(_Time.y * 7.3, 0.5));
                col *= fk;

                // ── Apply lighting ────────────────────────────────────────
                col *= lighting;

                half4 result = half4(col, a);
                result.rgb   = MixFog(result.rgb, IN.fogFactor.x);
                return result;
            }
            ENDHLSL
        }

        // ── ShadowCaster ─────────────────────────────────────────────────
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
