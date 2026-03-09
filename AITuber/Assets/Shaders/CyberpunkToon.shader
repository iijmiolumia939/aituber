// =============================================================================
//  AITuber/CyberpunkToon
//  URP toon shader inspired by PotaToon's feature set.
//  Supports: Base Step shadow, MidTone, RimLight (neon), HighLight (specular),
//            MatCap, Emission, Outline (inverted hull), Normal Map,
//            SRP Batcher, Multi-light, Fog, ShadowCaster, DepthOnly.
// =============================================================================
Shader "AITuber/CyberpunkToon"
{
    Properties
    {
        // ── Base ────────────────────────────────────────────────────────────
        [Header(Base)]
        _BaseMap        ("Base (Lit) Map",   2D)    = "white" {}
        _BaseColor      ("Base Color",       Color) = (1, 1, 1, 1)
        _ShadeMap       ("Shade (Shadow) Map", 2D)  = "white" {}
        _ShadeColor     ("Shade Color",      Color) = (0.35, 0.25, 0.45, 1)

        // ── Toon Step ───────────────────────────────────────────────────────
        [Header(Toon Shadow Step)]
        _BaseStep       ("Base Step",        Range(-1, 1)) = 0.0
        _StepSmooth     ("Step Smoothness",  Range(0.001, 0.5)) = 0.02

        // ── MidTone (shadow boundary gradient) ─────────────────────────────
        [Header(MidTone)]
        [Toggle] _UseMidTone     ("Use MidTone",      Float) = 0
        _MidToneColor            ("MidTone Color",    Color) = (0.7, 0.55, 0.8, 1)
        _MidToneThickness        ("MidTone Thickness",Range(0.001, 0.5)) = 0.05

        // ── Normal Map ──────────────────────────────────────────────────────
        [Header(Normal Map)]
        [Toggle] _UseNormalMap   ("Use Normal Map",   Float) = 0
        [Normal] _NormalMap      ("Normal Map",       2D)    = "bump" {}
        _BumpScale               ("Bump Scale",       Range(0, 2)) = 1.0

        // ── Rim Light (Neon) ────────────────────────────────────────────────
        [Header(Rim Light Neon)]
        [Toggle] _UseRimLight    ("Use Rim Light",    Float) = 1
        _RimColor                ("Rim Color",        Color) = (0, 1, 1, 1)
        _RimPower                ("Rim Power",        Range(0.1, 10)) = 3.0
        _RimSmooth               ("Rim Smoothness",   Range(0.001, 0.5)) = 0.02
        _RimIntensity            ("Rim Intensity",    Range(0, 5)) = 2.0
        _RimMask                 ("Rim Mask (R=on)",  2D) = "white" {}

        // ── HighLight (Stylized Specular) ───────────────────────────────────
        [Header(HighLight Specular)]
        [Toggle] _UseHighLight   ("Use HighLight",    Float) = 1
        _HighLightColor          ("HighLight Color",  Color) = (1, 0.9, 1, 1)
        _HighLightPower          ("HighLight Power",  Range(1, 512)) = 64
        _HighLightSmooth         ("HighLight Smooth", Range(0.001, 0.5)) = 0.02
        _HighLightMask           ("HighLight Mask (R=on)", 2D) = "white" {}

        // ── MatCap ──────────────────────────────────────────────────────────
        [Header(MatCap)]
        [Toggle] _UseMatCap      ("Use MatCap",       Float) = 0
        _MatCapMap               ("MatCap Map",       2D)    = "black" {}
        _MatCapWeight            ("MatCap Weight",    Range(0, 1)) = 0.3
        [Enum(Add,0,Multiply,1)]
        _MatCapMode              ("MatCap Mode",      Float) = 0

        // ── Emission ────────────────────────────────────────────────────────
        [Header(Emission)]
        [HDR] _EmissionColor     ("Emission Color",   Color) = (0, 1, 1, 0)
        _EmissionMap             ("Emission Map",     2D)    = "black" {}
        _EmissionIntensity       ("Emission Intensity",Range(0, 10)) = 1.0

        // ── Outline ─────────────────────────────────────────────────────────
        [Header(Outline)]
        _OutlineColor            ("Outline Color",    Color) = (0.04, 0.02, 0.08, 1)
        _OutlineWidth            ("Outline Width",    Range(0, 0.05)) = 0.003
        _OutlineLightingDimmer   ("Outline Light Dimmer", Range(0, 1)) = 0.0

        // ── Hair Highlight (angle-dependent, stronger from above) ───────────
        [Header(Hair Highlight)]
        [Toggle] _UseHairHighlight  ("Use Hair Highlight",   Float) = 0
        _HairHighlightColor         ("Hair Highlight Color", Color) = (1, 0.95, 0.85, 1)
        _HairHighlightPower         ("Hair Highlight Power", Range(1, 512)) = 128
        _HairHighlightSmooth        ("Hair Highlight Smooth",Range(0.001, 0.3)) = 0.02
        _HairHighlightShift         ("Height Shift",         Range(-1, 1)) = 0.3
        _HairHighlightMask          ("Hair Highlight Mask (R=on)", 2D) = "white" {}

        // ── Ambient Influence (SH fills dark areas) ─────────────────────
        [Header(Ambient)]
        _AmbientInfluence           ("Ambient Influence",    Range(0, 1)) = 0.3

        // ── Color Grading (per-region saturation) ───────────────────────
        [Header(Color Grading)]
        _LitSaturation              ("Lit Saturation",       Range(0, 2)) = 1.0
        _ShadowSaturation           ("Shadow Saturation",    Range(0, 2)) = 0.85

        // ── Alpha / Cull ─────────────────────────────────────────────────────
        [Header(Alpha)]
        [Toggle] _UseAlphaCutoff ("Use Alpha Cutoff", Float) = 0
        _AlphaCutoff             ("Alpha Cutoff",     Range(0, 1)) = 0.5
        [Enum(UnityEngine.Rendering.CullMode)]
        _Cull                    ("Cull Mode",        Float) = 2
    }

    SubShader
    {
        Tags
        {
            "RenderType"       = "Opaque"
            "RenderPipeline"   = "UniversalPipeline"
            "Queue"            = "Geometry"
            "IgnoreProjector"  = "True"
        }
        LOD 300

        // =================================================================
        // PASS 0 – Outline  (inverted hull, Cull Front)
        // =================================================================
        Pass
        {
            Name "Outline"
            Tags { "LightMode" = "SRPDefaultUnlit" }
            Cull  Front
            ZWrite On
            ZTest LEqual
            Blend Off

            HLSLPROGRAM
            #pragma vertex   OutlineVertex
            #pragma fragment OutlineFragment
            #pragma multi_compile_fog
            #pragma multi_compile_instancing

            #include "CyberpunkToonOutlinePass.hlsl"
            ENDHLSL
        }

        // =================================================================
        // PASS 1 – UniversalForward  (main toon lit pass)
        // =================================================================
        Pass
        {
            Name "UniversalForward"
            Tags { "LightMode" = "UniversalForward" }
            Cull  [_Cull]
            ZWrite On
            ZTest LEqual
            Blend Off

            HLSLPROGRAM
            #pragma vertex   ToonVertex
            #pragma fragment ToonFragment

            // URP shadow keywords
            #pragma multi_compile _ _MAIN_LIGHT_SHADOWS _MAIN_LIGHT_SHADOWS_CASCADE _MAIN_LIGHT_SHADOWS_SCREEN
            #pragma multi_compile _ _ADDITIONAL_LIGHTS_VERTEX _ADDITIONAL_LIGHTS
            #pragma multi_compile _ _ADDITIONAL_LIGHT_SHADOWS
            #pragma multi_compile _ _SHADOWS_SOFT _SHADOWS_SOFT_LOW _SHADOWS_SOFT_MEDIUM _SHADOWS_SOFT_HIGH
            #pragma multi_compile _ EVALUATE_SH_MIXED EVALUATE_SH_VERTEX
            #pragma multi_compile _ LIGHTMAP_SHADOW_MIXING
            #pragma multi_compile _ SHADOWS_SHADOWMASK
            #pragma multi_compile_fog
            #pragma multi_compile_instancing

            #include "CyberpunkToonForwardPass.hlsl"
            ENDHLSL
        }

        // =================================================================
        // PASS 2 – ShadowCaster
        // =================================================================
        Pass
        {
            Name "ShadowCaster"
            Tags { "LightMode" = "ShadowCaster" }
            ZWrite On
            ZTest  LEqual
            ColorMask 0
            Cull [_Cull]

            HLSLPROGRAM
            #pragma vertex   ShadowCasterVertex
            #pragma fragment ShadowCasterFragment
            #pragma multi_compile_vertex _ _CASTING_PUNCTUAL_LIGHT_SHADOW
            #pragma multi_compile_instancing

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Shadows.hlsl"
            #include "CyberpunkToonInput.hlsl"

            float3 _LightDirection;
            float3 _LightPosition;

            struct ShadowAttribs  { float4 positionOS : POSITION; float3 normalOS : NORMAL; };
            struct ShadowVaryings { float4 positionCS : SV_POSITION; };

            ShadowVaryings ShadowCasterVertex(ShadowAttribs IN)
            {
                ShadowVaryings OUT;
                float3 posWS  = TransformObjectToWorld(IN.positionOS.xyz);
                float3 normWS = TransformObjectToWorldNormal(IN.normalOS);

                #if _CASTING_PUNCTUAL_LIGHT_SHADOW
                    float3 lightDir = normalize(_LightPosition - posWS);
                #else
                    float3 lightDir = _LightDirection;
                #endif

                float4 posCS = TransformWorldToHClip(
                    ApplyShadowBias(posWS, normWS, lightDir));

                #if UNITY_REVERSED_Z
                    posCS.z = min(posCS.z, UNITY_NEAR_CLIP_VALUE);
                #else
                    posCS.z = max(posCS.z, UNITY_NEAR_CLIP_VALUE);
                #endif

                OUT.positionCS = posCS;
                return OUT;
            }

            half4 ShadowCasterFragment(ShadowVaryings IN) : SV_Target { return 0; }
            ENDHLSL
        }

        // =================================================================
        // PASS 3 – DepthOnly  (needed for depth prepass / SSAO)
        // =================================================================
        Pass
        {
            Name "DepthOnly"
            Tags { "LightMode" = "DepthOnly" }
            ZWrite On
            ColorMask R
            Cull [_Cull]

            HLSLPROGRAM
            #pragma vertex   DepthOnlyVertex
            #pragma fragment DepthOnlyFragment
            #pragma multi_compile_instancing

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            #include "CyberpunkToonInput.hlsl"

            struct DepthAttribs  { float4 positionOS : POSITION; };
            struct DepthVaryings { float4 positionCS : SV_POSITION; };

            DepthVaryings DepthOnlyVertex(DepthAttribs IN)
            {
                DepthVaryings OUT;
                OUT.positionCS = TransformObjectToHClip(IN.positionOS.xyz);
                return OUT;
            }

            half4 DepthOnlyFragment(DepthVaryings IN) : SV_Target { return 0; }
            ENDHLSL
        }

        // =================================================================
        // PASS 4 – DepthNormals  (needed for SSAO / temporal AA)
        // =================================================================
        Pass
        {
            Name "DepthNormals"
            Tags { "LightMode" = "DepthNormals" }
            ZWrite On
            Cull [_Cull]

            HLSLPROGRAM
            #pragma vertex   DepthNormalsVertex
            #pragma fragment DepthNormalsFragment
            #pragma multi_compile_instancing

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            #include "CyberpunkToonInput.hlsl"

            struct DNAttribs  { float4 positionOS : POSITION; float3 normalOS : NORMAL; };
            struct DNVaryings { float4 positionCS : SV_POSITION; float3 normalWS : TEXCOORD0; };

            DNVaryings DepthNormalsVertex(DNAttribs IN)
            {
                DNVaryings OUT;
                OUT.positionCS = TransformObjectToHClip(IN.positionOS.xyz);
                OUT.normalWS   = TransformObjectToWorldNormal(IN.normalOS);
                return OUT;
            }

            half4 DepthNormalsFragment(DNVaryings IN) : SV_Target
            {
                // Store view-space normals in RG, 0 in BA
                float3 n = normalize(IN.normalWS);
                return half4(n.xyz * 0.5 + 0.5, 0);
            }
            ENDHLSL
        }
    }

    FallBack "Universal Render Pipeline/Lit"
    CustomEditor "CyberpunkToonGUI"
}
