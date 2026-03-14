// =============================================================================
//  AITuber/MangaPanel
//  URP ? Manga / comic-panel appearance mode.
//
//  Algorithm:
//    1. 3-tone Lambert shading (lit / mid-shadow / deep-shadow).
//    2. Screen-tone half-tone dots in mid-shadow areas only.
//    3. Blinn-Phong specular highlight (tight, small).
//    4. Inverted-hull black outline.
//
//  SRP Batcher compatible: IDENTICAL UnityPerMaterial CBUFFER in all passes.
//  (Previous version had mismatched CBUFFER between Outline and Forward
//   passes, causing SRP Batcher fallback and undefined rendering => cyan.)
// =============================================================================
Shader "AITuber/MangaPanel"
{
    Properties
    {
        [Header(Base)]
        _BaseMap        ("Base Map",     2D)    = "white" {}
        _BaseColor      ("Base Color",   Color) = (1,1,1,1)

        [Header(Manga Shading)]
        _ShadowColor    ("Shadow Color",     Color)        = (0.65, 0.70, 0.80, 1)
        _LitThresh      ("Lit Threshold",    Range(0,1))   = 0.55
        _ShadowThresh   ("Shadow Threshold", Range(0,1))   = 0.20

        [Header(Screen Tone Dots)]
        _ToneFreq       ("Tone Frequency (px)", Range(8, 200)) = 60
        _ToneDotSize    ("Dot Radius",           Range(0.1, 0.7)) = 0.35
        _ToneStrength   ("Dot Strength",         Range(0, 1.2))   = 0.6

        [Header(Highlight)]
        _HighlightColor ("Highlight Color",  Color)         = (1,1,1,1)
        _HighlightPow   ("Highlight Power",  Range(8, 128)) = 64
        _HighlightThresh("Highlight Thresh", Range(0.5, 0.99)) = 0.88

        [Header(Outline)]
        _OutlineColor   ("Outline Color", Color)          = (0.05, 0.03, 0.05, 1)
        _OutlineWidth   ("Outline Width", Range(0, 0.02)) = 0.005

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

        // ���� PASS 0: Outline (inverted hull) ����������������������������������������������������������
        Pass
        {
            Name "Outline"
            Tags  { "LightMode" = "SRPDefaultUnlit" }
            Cull  Front
            ZWrite On

            HLSLPROGRAM
            #pragma vertex   OutVert
            #pragma fragment OutFrag
            #pragma multi_compile_instancing

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"

            // CBUFFER must be IDENTICAL to the Forward pass for SRP Batcher compat.
            CBUFFER_START(UnityPerMaterial)
                float4 _BaseMap_ST;
                half4  _BaseColor;
                half4  _ShadowColor;
                float  _LitThresh;
                float  _ShadowThresh;
                float  _ToneFreq;
                float  _ToneDotSize;
                half   _ToneStrength;
                half4  _HighlightColor;
                float  _HighlightPow;
                float  _HighlightThresh;
                half4  _OutlineColor;
                float  _OutlineWidth;
            CBUFFER_END

            struct OA { float4 pos : POSITION; float3 n : NORMAL;
                        UNITY_VERTEX_INPUT_INSTANCE_ID };
            struct OV { float4 pos : SV_POSITION;
                        UNITY_VERTEX_OUTPUT_STEREO };

            OV OutVert(OA IN)
            {
                UNITY_SETUP_INSTANCE_ID(IN);
                OV OUT;
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(OUT);
                float3 posWS  = TransformObjectToWorld(IN.pos.xyz);
                float3 normWS = normalize(TransformObjectToWorldNormal(IN.n));
                posWS        += normWS * _OutlineWidth;
                OUT.pos       = TransformWorldToHClip(posWS);
                return OUT;
            }

            half4 OutFrag(OV IN) : SV_Target { return _OutlineColor; }
            ENDHLSL
        }

        // ���� PASS 1: Manga forward ��������������������������������������������������������������������������������
        Pass
        {
            Name "UniversalForward"
            Tags { "LightMode" = "UniversalForward" }
            Cull  [_Cull]
            ZWrite On

            HLSLPROGRAM
            #pragma vertex   vert
            #pragma fragment frag
            #pragma multi_compile_instancing
            #pragma multi_compile _ _MAIN_LIGHT_SHADOWS _MAIN_LIGHT_SHADOWS_CASCADE

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"

            CBUFFER_START(UnityPerMaterial)
                float4 _BaseMap_ST;
                half4  _BaseColor;
                half4  _ShadowColor;
                float  _LitThresh;
                float  _ShadowThresh;
                float  _ToneFreq;
                float  _ToneDotSize;
                half   _ToneStrength;
                half4  _HighlightColor;
                float  _HighlightPow;
                float  _HighlightThresh;
                half4  _OutlineColor;
                float  _OutlineWidth;
            CBUFFER_END

            TEXTURE2D(_BaseMap); SAMPLER(sampler_BaseMap);

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
                float3 viewDirWS  : TEXCOORD2;
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
                return OUT;
            }

            half4 frag(Varyings IN) : SV_Target
            {
                half4 albedo = SAMPLE_TEXTURE2D(_BaseMap, sampler_BaseMap, IN.uv) * _BaseColor;

                // ���� 3-tone Lambert shading ����������������������������������������������������������������
                Light  mainLight = GetMainLight();
                float3 nWS       = normalize(IN.normalWS);
                half   ndotl     = saturate(dot(nWS, mainLight.direction));

                // isMid: between ShadowThresh and LitThresh
                half isMid  = step(ndotl, _LitThresh)   * step(_ShadowThresh, ndotl);
                half isDeep = step(ndotl, _ShadowThresh);

                half3 color = albedo.rgb;
                color = lerp(color, color * _ShadowColor.rgb,        isMid  * 0.5h);
                color = lerp(color, color * _ShadowColor.rgb * 0.5h, isDeep);

                // ���� Screen-tone dots (mid-shadow only) ����������������������������������������
                float2 tileUV = frac(IN.positionCS.xy / _ToneFreq) - 0.5;
                float  dot2   = dot(tileUV, tileUV);
                float  r2     = _ToneDotSize * _ToneDotSize * 0.25;
                half   tone   = (half)step(dot2, r2) * isMid * _ToneStrength;
                color         = color * (1.0h - tone * 0.5h);

                // ���� Blinn-Phong highlight (small, tight, no Voronoi) ������������
                float3 vWS    = normalize(IN.viewDirWS);
                half3  halfV  = (half3)normalize(mainLight.direction + vWS);
                half   nh     = saturate(dot((half3)nWS, halfV));
                float  hilite = step(_HighlightThresh, pow(nh, _HighlightPow));
                color        += hilite * _HighlightColor.rgb;

                return half4(saturate(color), albedo.a);
            }
            ENDHLSL
        }

        // ���� PASS 2: ShadowCaster ����������������������������������������������������������������������������������
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

            CBUFFER_START(UnityPerMaterial)
                float4 _BaseMap_ST;
                half4  _BaseColor;
                half4  _ShadowColor;
                float  _LitThresh;
                float  _ShadowThresh;
                float  _ToneFreq;
                float  _ToneDotSize;
                half   _ToneStrength;
                half4  _HighlightColor;
                float  _HighlightPow;
                float  _HighlightThresh;
                half4  _OutlineColor;
                float  _OutlineWidth;
            CBUFFER_END

            float3 _LightDirection;
            struct ShadowA { float4 pos : POSITION; float3 n : NORMAL; };
            struct ShadowV { float4 pos : SV_POSITION; };

            ShadowV ShadowVert(ShadowA IN)
            {
                ShadowV OUT;
                float3 posWS  = TransformObjectToWorld(IN.pos.xyz);
                float3 normWS = TransformObjectToWorldNormal(IN.n);
                OUT.pos = TransformWorldToHClip(ApplyShadowBias(posWS, normWS, _LightDirection));
                return OUT;
            }
            half4 ShadowFrag(ShadowV IN) : SV_Target { return 0; }
            ENDHLSL
        }
    }
}
