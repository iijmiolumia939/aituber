// ShaderTransitionAvatar.shader
// Avatar wireframe-pivot transition effect applied directly to SkinnedMeshRenderers.
//
// _TransitionProgress semantics:
//   0.0 = original texture, render unchanged
//   1.0 = pure wireframe glow lines on dark background  ← PEAK / midpoint of the swap
//
// AppearanceController drives:
//   Phase-1 (src material)  : _TransitionProgress 0 -> 1   (texture dissolves into wire)
//   Phase-2 (dst material)  : _TransitionProgress 1 -> 0   (wire materialises into texture)
//
// SRS refs: FR-SHADER-TRANSITION-01

Shader "AITuber/ShaderTransitionAvatar"
{
    Properties
    {
        _MainTex            ("Base Texture",        2D)              = "white" {}
        _BaseColor          ("Base Color",          Color)           = (1, 1, 1, 1)
        _HoloColor          ("Wire Glow Color",     Color)           = (0.05, 0.88, 1.0, 1.0)
        _WireGridScale      ("Wire Grid Scale",     Float)           = 18.0
        _WireGlow           ("Wire Glow",           Range(0.5, 8.0)) = 3.0
        _ScanlineFreq       ("Scanline Frequency",  Float)           = 90.0
        _TransitionProgress ("Transition Progress", Range(0, 1))     = 0
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
                float4 _HoloColor;
                float  _WireGridScale;
                float  _WireGlow;
                float  _ScanlineFreq;
                float  _TransitionProgress;
            CBUFFER_END

            TEXTURE2D(_MainTex); SAMPLER(sampler_MainTex);

            struct Attributes
            {
                float4 positionOS : POSITION;
                float3 normalOS   : NORMAL;
                float2 uv         : TEXCOORD0;
                uint   vertexID   : SV_VertexID;   // 重心座標自動生成用
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float2 uv         : TEXCOORD0;
                float3 normalWS   : TEXCOORD1;
                float  fogFactor  : TEXCOORD2;
                float3 bary       : TEXCOORD3;     // 重心座標 (SV_VertexID % 3)
                UNITY_VERTEX_OUTPUT_STEREO
            };

            float hash2(float2 p)
            {
                p = frac(p * float2(127.1, 311.7));
                p += dot(p, p + 19.19);
                return frac(p.x * p.y);
            }

            float smoothNoise(float2 p)
            {
                float2 i = floor(p);
                float2 f = frac(p);
                f = f * f * (3.0 - 2.0 * f);
                return lerp(
                    lerp(hash2(i),                hash2(i + float2(1, 0)), f.x),
                    lerp(hash2(i + float2(0, 1)), hash2(i + float2(1, 1)), f.x),
                    f.y);
            }

            Varyings Vert(Attributes IN)
            {
                UNITY_SETUP_INSTANCE_ID(IN);
                Varyings OUT;
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(OUT);
                VertexPositionInputs vpi = GetVertexPositionInputs(IN.positionOS.xyz);
                OUT.positionCS = vpi.positionCS;
                OUT.uv         = TRANSFORM_TEX(IN.uv, _MainTex);
                OUT.normalWS   = TransformObjectToWorldNormal(IN.normalOS);
                OUT.fogFactor  = ComputeFogFactor(vpi.positionCS.z);
                // 重心座標: SV_VertexID % 3 で自動割り当て
                uint bid = IN.vertexID % 3u;
                OUT.bary = float3(bid == 0u, bid == 1u, bid == 2u);
                return OUT;
            }

            float4 Frag(Varyings IN) : SV_Target
            {
                float p = _TransitionProgress;
                float t = _Time.y;

                // ── Barycentric wireframe edge (SV_VertexID 済み小岐管: ポリゴンエッジ = 線のみ) ──
                float3 db        = fwidth(IN.bary);
                float  lw        = lerp(0.8, 2.5, p);   // p=1 に近づくと線を強調
                float3 fw        = db * lw;
                float3 fv        = smoothstep(float3(0,0,0), fw, IN.bary);
                float  wireEdge  = 1.0 - min(fv.x, min(fv.y, fv.z));
                float  pulse    = 0.5 + 0.5 * sin(t * 5.0 + IN.uv.y * 8.0);
                float  wirePhase = smoothstep(0.40, 0.88, p);
                float3 wireGlow = _HoloColor.rgb * _WireGlow * wireEdge
                                  * (1.0 + 0.25 * pulse) * wirePhase;

                // pureFactor はここで先に計算
                float pureFactor = smoothstep(0.75, 1.0, p);

                // ── Noise dissolve ────────────────────────────────────────────
                float dissolveP    = smoothstep(0.30, 0.92, p);
                float n            = smoothNoise(IN.uv * 4.5)  * 0.55
                                   + smoothNoise(IN.uv * 10.0) * 0.45;
                float dissolveMask = step(n, dissolveP);
                float dissolveEdge = step(n, dissolveP + 0.04)
                                   * (1.0 - step(n, dissolveP - 0.01));

                // ── Glitch ──────────────────────────────────────────────────
                float glitchFade = wirePhase * (1.0 - smoothstep(0.82, 1.0, p));
                float bandT      = floor(t * 13.0);
                float bandRow    = floor(IN.uv.y * 30.0);
                float gn         = hash2(float2(bandRow, bandT));
                float xOff       = (hash2(float2(bandRow * 3.1, bandT)) - 0.5)
                                 * 0.05 * step(0.87, gn) * glitchFade;
                float aberr      = 0.004 * glitchFade;
                float2 uvC       = IN.uv + float2(xOff, 0.0);

                // ── Texture sample (with chromatic aberration) ───────────────
                float4 base;
                base.r = SAMPLE_TEXTURE2D(_MainTex, sampler_MainTex, uvC + float2( aberr, 0)).r;
                base.g = SAMPLE_TEXTURE2D(_MainTex, sampler_MainTex, uvC).g;
                base.b = SAMPLE_TEXTURE2D(_MainTex, sampler_MainTex, uvC + float2(-aberr, 0)).b;
                base.a = 1.0;
                base  *= _BaseColor;

                // ── Scanline ──────────────────────────────────────────────────
                float scanline = pow(abs(sin(IN.uv.y * _ScanlineFreq + t * 1.5)), 3.0);
                wireGlow *= lerp(0.8, 1.0, scanline);

                // ── Composite ─────────────────────────────────────────────────
                // clip() を使わず max(dissolveMask, pureFactor) で暗くする。
                // clip() はフェースピクセルを透明にして背景が透けて見えるため NG。
                // p=1(wireframe peak): pureFactor=1 → フェースは暗黒 + wireGlow のみ表示
                // p<0.75: pureFactor=0 → dissolve noise がフェースを徐々に復元
                float3 col = lerp(base.rgb, float3(0.01, 0.03, 0.07), max(dissolveMask, pureFactor));
                // Dissolve-edge spark
                col += _HoloColor.rgb * dissolveEdge * 2.8 * (1.0 - p);
                // Wire glow (wireGlow は wireEdge 込みなのでフェースピクセルは自動的に 0)
                col += wireGlow;

                col = MixFog(col, IN.fogFactor);
                return float4(col, 1.0);
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
                float4 _HoloColor;
                float  _WireGridScale;
                float  _WireGlow;
                float  _ScanlineFreq;
                float  _TransitionProgress;
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