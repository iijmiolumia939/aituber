// PixelArtAvatar.shader
// Per-renderer dot/pixel-art stylised shader for the AI avatar.
//
// Effect layers (all per-material, no camera RT required):
//   1. UV quantisation  – texture is sampled at block-snapped coordinates
//   2. Palette quant    – RGB values rounded to N steps per channel
//   3. Dot pattern      – corners of each "pixel" cell are slightly darkened
//   4. Rim outline      – silhouette edge darkened with configurable colour
//
// SRS refs: FR-SHADER-02 (PixelArt mode)

Shader "AITuber/PixelArtAvatar"
{
    Properties
    {
        _MainTex       ("Base Texture",    2D)           = "white" {}
        _BaseColor     ("Base Color",      Color)        = (1, 1, 1, 1)
        [Space]
        [Header(Pixel Art)]
        _BlockSize     ("Block Size",      Range(4, 256)) = 48
        _ColorSteps    ("Color Steps",     Range(2, 32))  = 10
        [Space]
        [Header(Dot Pattern)]
        _DotRadius     ("Dot Radius",      Range(0, 1))   = 0.42
        _DotDim        ("Corner Dimming",  Range(0, 1))   = 0.30
        [Space]
        [Header(Outline)]
        _OutlineWidth  ("Outline Width",   Range(0, 1))   = 0.38
        _OutlineColor  ("Outline Color",   Color)         = (0.06, 0.03, 0.10, 1)
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
            ZWrite On

            HLSLPROGRAM
            #pragma vertex   Vert
            #pragma fragment Frag
            #pragma multi_compile_instancing
            #pragma multi_compile_fog

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"

            CBUFFER_START(UnityPerMaterial)
                float4 _MainTex_ST;
                float4 _BaseColor;
                float4 _OutlineColor;
                float  _BlockSize;
                float  _ColorSteps;
                float  _DotRadius;
                float  _DotDim;
                float  _OutlineWidth;
            CBUFFER_END

            TEXTURE2D(_MainTex); SAMPLER(sampler_MainTex);

            struct Attributes
            {
                float4 positionOS : POSITION;
                float3 normalOS   : NORMAL;
                float2 uv         : TEXCOORD0;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float3 positionWS : TEXCOORD0;
                float2 uv         : TEXCOORD1;
                float3 normalWS   : TEXCOORD2;
                float  fogFactor  : TEXCOORD3;
                UNITY_VERTEX_OUTPUT_STEREO
            };

            Varyings Vert(Attributes IN)
            {
                UNITY_SETUP_INSTANCE_ID(IN);
                Varyings OUT;
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(OUT);
                VertexPositionInputs vpi = GetVertexPositionInputs(IN.positionOS.xyz);
                OUT.positionCS = vpi.positionCS;
                OUT.positionWS = vpi.positionWS;
                OUT.uv         = TRANSFORM_TEX(IN.uv, _MainTex);
                OUT.normalWS   = TransformObjectToWorldNormal(IN.normalOS);
                OUT.fogFactor  = ComputeFogFactor(vpi.positionCS.z);
                return OUT;
            }

            float4 Frag(Varyings IN) : SV_Target
            {
                // ── 1. UV quantisation ────────────────────────────────────────
                float2 blockUV = (floor(IN.uv * _BlockSize) + 0.5) / _BlockSize;
                float4 col = SAMPLE_TEXTURE2D(_MainTex, sampler_MainTex, blockUV) * _BaseColor;

                // ── 2. Palette quantisation ───────────────────────────────────
                col.rgb = floor(col.rgb * _ColorSteps + 0.5) / _ColorSteps;

                // ── 3. Dot pattern (darken pixel corners) ──────────────────────
                float2 dotPos = frac(IN.uv * _BlockSize) - 0.5; // [-0.5, 0.5]
                float  inDot  = step(dot(dotPos, dotPos), _DotRadius * _DotRadius * 0.25);
                col.rgb *= lerp(1.0 - _DotDim, 1.0, inDot);

                // ── 4. Rim-based outline ───────────────────────────────────────
                float3 viewDir = normalize(GetWorldSpaceViewDir(IN.positionWS));
                float  NdotV   = saturate(dot(normalize(IN.normalWS), viewDir));
                float  rim     = 1.0 - NdotV;
                float  outline = step(1.0 - _OutlineWidth * 0.80, rim);
                col.rgb = lerp(col.rgb, _OutlineColor.rgb, outline);

                col.rgb = MixFog(col.rgb, IN.fogFactor);
                return float4(col.rgb, 1.0);
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

            HLSLPROGRAM
            #pragma vertex   ShadowVert
            #pragma fragment ShadowFrag
            #pragma multi_compile_instancing

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Shadows.hlsl"

            CBUFFER_START(UnityPerMaterial)
                float4 _MainTex_ST;
                float4 _BaseColor;
                float4 _OutlineColor;
                float  _BlockSize;
                float  _ColorSteps;
                float  _DotRadius;
                float  _DotDim;
                float  _OutlineWidth;
            CBUFFER_END

            struct ShadowAttribs
            {
                float4 pos    : POSITION;
                float3 normal : NORMAL;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct ShadowVaryings { float4 pos : SV_POSITION; };

            float3 _LightDirection;

            ShadowVaryings ShadowVert(ShadowAttribs IN)
            {
                UNITY_SETUP_INSTANCE_ID(IN);
                ShadowVaryings OUT;
                float3 posWS  = TransformObjectToWorld(IN.pos.xyz);
                float3 normWS = TransformObjectToWorldNormal(IN.normal);
                OUT.pos = TransformWorldToHClip(ApplyShadowBias(posWS, normWS, _LightDirection));
                return OUT;
            }

            float4 ShadowFrag(ShadowVaryings IN) : SV_Target { return 0; }
            ENDHLSL
        }
    }
}