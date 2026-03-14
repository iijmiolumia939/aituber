// =============================================================================
//  AITuber/WireframeSolid
//  URP — "Wireframe + Solid blend" appearance mode.
//
//  Technique: SV_VertexID % 3 を使い、頂点シェーダー内で
//  (1,0,0)/(0,1,0)/(0,0,1) の重心座標を自動生成。
//  UV セームで頂点が分割されているメッシュ（FBX インポート標準）で動作する。
//  fwidth() でエッジ幅をスクリーンピクセル単位に変換し、
//  暗いソリッドボディの上に発光するワイヤーラインを描く。
// =============================================================================
Shader "AITuber/WireframeSolid"
{
    Properties
    {
        [Header(Solid Base)]
        _BaseMap     ("Base Map",   2D)    = "white" {}
        _BaseColor   ("Base Color", Color) = (0.04, 0.06, 0.10, 1)

        [Header(Wireframe)]
        _WireColor   ("Wire Color",       Color)           = (0.2, 0.8, 1.0, 1)
        _WireWidth   ("Wire Width (px)",  Range(0.3, 4.0)) = 1.2
        _WireGlow    ("Wire Glow",        Range(0, 5))     = 2.0
        _WireAnimate ("Wire Pulse Speed", Range(0, 5))     = 1.2

        [Header(Cull)]
        [Enum(UnityEngine.Rendering.CullMode)]
        _Cull ("Cull Mode", Float) = 2
    }

    SubShader
    {
        Tags
        {
            "RenderType"     = "Transparent"
            "RenderPipeline" = "UniversalPipeline"
            "Queue"          = "Transparent"
        }
        LOD 200

        Pass
        {
            Name "UniversalForward"
            Tags { "LightMode" = "UniversalForward" }
            Cull  [_Cull]
            ZWrite Off
            Blend One One       // 加算合成: ワイヤーグロー、非ワイヤー(黒) = 透明

            HLSLPROGRAM
            #pragma vertex   vert
            #pragma fragment frag
            #pragma multi_compile_instancing
            #pragma multi_compile_fog
            #pragma target 3.5

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"

            CBUFFER_START(UnityPerMaterial)
                float4 _BaseMap_ST;
                half4  _BaseColor;
                half4  _WireColor;
                float  _WireWidth;
                half   _WireGlow;
                float  _WireAnimate;
            CBUFFER_END

            TEXTURE2D(_BaseMap); SAMPLER(sampler_BaseMap);

            struct Attribs
            {
                float4 positionOS : POSITION;
                float3 normalOS   : NORMAL;
                float2 uv         : TEXCOORD0;
                uint   vertexID   : SV_VertexID;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float2 uv         : TEXCOORD0;
                float3 normalWS   : TEXCOORD1;
                float3 bary       : TEXCOORD2;
                float  fogFactor  : TEXCOORD3;
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
                OUT.fogFactor  = ComputeFogFactor(vpi.positionCS.z);

                // SV_VertexID % 3 で重心座標を自動割り当て
                uint bid = IN.vertexID % 3u;
                OUT.bary = float3(bid == 0u, bid == 1u, bid == 2u);

                return OUT;
            }

            half4 frag(Varyings IN) : SV_Target
            {
                // ── ワイヤーエッジのみ描画 (面は透明) ─────────────────
                float3 d  = fwidth(IN.bary);
                float3 fw = d * _WireWidth;
                float3 f  = smoothstep(float3(0,0,0), fw, IN.bary);
                float  ef = 1.0 - min(f.x, min(f.y, f.z));

                // 非エッジピクセルを早期破棄（加算合成なので黒=透明だが clip で帯域節約）
                clip(ef - 0.02);

                // パルスアニメーション
                float  pulse   = 0.5 + 0.5 * sin(_Time.y * _WireAnimate * 6.2832);
                half3  wireCol = _WireColor.rgb * _WireGlow * (1.0 + 0.25 * pulse);

                // ワイヤーラインのみ出力（加算合成: 背景に発光グローが乗る）
                return half4(wireCol * ef, 1.0);
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
            CBUFFER_START(UnityPerMaterial)
                float4 _BaseMap_ST;
                half4  _BaseColor;
                half4  _WireColor;
                float  _WireWidth;
                half   _WireGlow;
                float  _WireAnimate;
            CBUFFER_END
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
