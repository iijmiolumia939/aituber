// =============================================================================
//  AITuber/CrosshatchSketch
//  URP ? "Dessin / Pencil Sketch" appearance mode.
//  Based on: https://usagi-meteor.com/dessin technique (Built-in CG)
//  Ported to URP HLSL.
//
//  Algorithm:
//    1. nl = NdotL x albedo-luminance x Brightness (article formula)
//    2. Screen-space UV ? strokes stay fixed on screen as avatar moves.
//    3. stroke1 = single 45deg diagonal hatch; stroke2 = cross-hatch.
//    4. col2 = _PaperColor x strokeTex x brightness_scale.
//    5. nl > 0.5 => clean paper (no strokes).
//    6. Animated shake (floor-sin time) for hand-drawn feel.
//    7. Inverted-hull outline also gets the shake offset.
//  SRP Batcher: identical UnityPerMaterial CBUFFER in all 3 passes.
// =============================================================================
Shader "AITuber/CrosshatchSketch"
{
    Properties
    {
        [Header(Base)]
        _BaseMap        ("Base Map",     2D)    = "white" {}
        _BaseColor      ("Base Color",   Color) = (1,1,1,1)

        [Header(Paper and Ink)]
        _PaperColor     ("Paper Color",  Color)        = (0.95, 0.92, 0.84, 1)
        _InkColor       ("Ink Color",    Color)        = (0.12, 0.08, 0.04, 1)

        [Header(Stroke)]
        _StrokeDensity  ("Stroke Density",   Range(1, 16)) = 6
        _Brightness     ("Brightness Boost", Range(0.5, 3)) = 1.0

        [Header(Shake)]
        [Toggle] _Move      ("Animate Shake", Float) = 1
        _Frec               ("Shake Frequency",  Range(0, 1)) = 0.5
        _ShakeSize          ("Shake Amount",     Range(0, 0.006)) = 0.003

        [Header(Outline)]
        _OutlineColor   ("Outline Color", Color)          = (0.08, 0.05, 0.05, 1)
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

        // ���� PASS 0: Outline (inverted hull + shake) ��������������������������������������������
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

            CBUFFER_START(UnityPerMaterial)
                float4 _BaseMap_ST;
                half4  _BaseColor;
                half4  _PaperColor;
                half4  _InkColor;
                float  _StrokeDensity;
                float  _Brightness;
                float  _Move;
                float  _Frec;
                float  _ShakeSize;
                half4  _OutlineColor;
                float  _OutlineWidth;
            CBUFFER_END

            struct OA { float4 pos : POSITION; float3 n : NORMAL;
                        UNITY_VERTEX_INPUT_INSTANCE_ID };
            struct OV { float4 pos : SV_POSITION;
                        UNITY_VERTEX_OUTPUT_STEREO };

            float _randSketch(float2 co)
            {
                return frac(sin(dot(co, float2(12.9898, 78.233))) * 43758.5453);
            }

            OV OutVert(OA IN)
            {
                UNITY_SETUP_INSTANCE_ID(IN);
                OV OUT;
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(OUT);
                float3 posWS  = TransformObjectToWorld(IN.pos.xyz);
                float3 normWS = normalize(TransformObjectToWorldNormal(IN.n));
                posWS        += normWS * _OutlineWidth;
                float4 posCS  = TransformWorldToHClip(posWS);
                if (_Move > 0.5)
                {
                    float time = floor(sin(_Time.y * 0.05 * 3.14159) * _Frec * 200.0);
                    float r    = _randSketch(float2(time, time)) * _ShakeSize;
                    posCS.xy  += r;
                }
                OUT.pos = posCS;
                return OUT;
            }

            half4 OutFrag(OV IN) : SV_Target { return _OutlineColor; }
            ENDHLSL
        }

        // ���� PASS 1: Sketch forward ��������������������������������������������������������������������������������
        Pass
        {
            Name "UniversalForward"
            Tags { "LightMode" = "UniversalForward" }
            Cull  [_Cull]
            ZWrite On

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
                half4  _PaperColor;
                half4  _InkColor;
                float  _StrokeDensity;
                float  _Brightness;
                float  _Move;
                float  _Frec;
                float  _ShakeSize;
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
                float  fogFactor  : TEXCOORD2;
                UNITY_VERTEX_OUTPUT_STEREO
            };

            float _randSketch(float2 co)
            {
                return frac(sin(dot(co, float2(12.9898, 78.233))) * 43758.5453);
            }

            // strokeTex1: single diagonal hatch at 45deg
            // Returns 0.0 at hatch lines, 1.0 at open paper.
            half strokeTex1(float2 p)
            {
                float t = frac((p.x + p.y) * 0.707);
                return (half)smoothstep(0.0, 0.09, t);
            }

            // strokeTex2: cross-hatch (45deg and 135deg)
            half strokeTex2(float2 p)
            {
                float t1 = frac(( p.x + p.y) * 0.707);
                float t2 = frac((-p.x + p.y) * 0.707);
                return (half)min(smoothstep(0.0, 0.09, t1),
                                  smoothstep(0.0, 0.09, t2));
            }

            Varyings vert(Attribs IN)
            {
                UNITY_SETUP_INSTANCE_ID(IN);
                Varyings OUT;
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(OUT);
                VertexPositionInputs vpi = GetVertexPositionInputs(IN.positionOS.xyz);
                OUT.positionCS = vpi.positionCS;
                if (_Move > 0.5)
                {
                    float time     = floor(sin(_Time.y * 0.05 * 3.14159) * _Frec * 200.0);
                    float r        = _randSketch(float2(time, time)) * _ShakeSize;
                    OUT.positionCS.xy += r;
                }
                OUT.uv        = TRANSFORM_TEX(IN.uv, _BaseMap);
                OUT.normalWS  = TransformObjectToWorldNormal(IN.normalOS);
                OUT.fogFactor = ComputeFogFactor(vpi.positionCS.z);
                return OUT;
            }

            half4 frag(Varyings IN) : SV_Target
            {
                // Albedo ? used for luminance only (article: nl = NdotL * lum)
                half4 col = SAMPLE_TEXTURE2D(_BaseMap, sampler_BaseMap, IN.uv) * _BaseColor;

                Light  mainLight = GetMainLight();
                float3 nWS       = normalize(IN.normalWS);
                half   NdotL     = saturate(dot(nWS, mainLight.direction));
                half   lum       = dot(col.rgb, half3(0.3h, 0.59h, 0.11h));
                half   nl        = saturate(NdotL * lum) * _Brightness;

                // Screen-space stroke UV ? fixed to screen, not model surface
                float2 scrPos = (IN.positionCS.xy / _ScreenParams.xy) * _StrokeDensity;

                half3 col2 = _PaperColor.rgb;
                half  s1   = strokeTex1(scrPos);
                half  s2   = strokeTex2(scrPos);

                // 6-level quantisation (direct port of article)
                if      (nl <= 0.01h) col2 = col2 * s1 * 0.50h;
                else if (nl <= 0.10h) col2 = col2 * s1 * 0.70h;
                else if (nl <= 0.20h) col2 = col2 * s1 * 0.90h;
                else if (nl <= 0.30h) col2 = col2 * s2 * 0.80h;
                else if (nl <= 0.40h) col2 = col2 * s2 * 1.00h;
                else if (nl <= 0.50h) col2 = col2 * s2 * 1.30h;
                // else nl > 0.5: bright area => clean paper, col2 unchanged

                col2 = saturate(col2);
                col2 = MixFog(col2, IN.fogFactor);
                return half4(col2, col.a);
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
                half4  _PaperColor;
                half4  _InkColor;
                float  _StrokeDensity;
                float  _Brightness;
                float  _Move;
                float  _Frec;
                float  _ShakeSize;
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
