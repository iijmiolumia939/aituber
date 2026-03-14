// ShaderTransitionGrid.shader
// Full-screen URP blit shader used by ShaderTransitionFeature.
// Overlays an animated cyan wireframe grid that peaks at _ShaderTransitionProgress = 0.5,
// allowing AppearanceController to switch shaders at the visual midpoint.
//
// SRS refs: FR-SHADER-TRANSITION-01
// Used with: FullScreenPassRendererFeature (injection: AfterRenderingPostProcessing)

Shader "AITuber/TransitionGrid"
{
    // No serialised properties — all driven by global shader properties at runtime.
    SubShader
    {
        Tags
        {
            "RenderType" = "Opaque"
            "RenderPipeline" = "UniversalPipeline"
        }

        Pass
        {
            Name "TransitionGrid"
            ZTest Always
            ZWrite Off
            Cull Off
            // No blending — we write directly to the color buffer (handled by blit).

            HLSLPROGRAM
            #pragma vertex Vert
            #pragma fragment Frag
            #pragma target 3.5

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            #include "Packages/com.unity.render-pipelines.core/Runtime/Utilities/Blit.hlsl"

            // Set each frame by AppearanceController.TransitionCoroutine.
            //   0.0 = not transitioning (pass-through)
            //   0.5 = peak grid (shader switch happens here)
            //   1.0 = not transitioning (pass-through)
            float _ShaderTransitionProgress;

            half4 Frag(Varyings input) : SV_Target
            {
                UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(input);
                float2 uv = input.texcoord;

                // Source color from the current scene render.
                half4 src = SAMPLE_TEXTURE2D_X(_BlitTexture, sampler_LinearClamp, uv);

                // Envelope: 0 at p=0 and p=1, peaking at p=0.5.
                float p = _ShaderTransitionProgress;
                float env = 1.0 - abs(p * 2.0 - 1.0);
                env = smoothstep(0.0, 0.35, env);

                // Fast path: no visible effect — avoid any per-pixel work.
                if (env < 0.004) return src;

                // ── Wireframe grid (screen-space, ~28 px cell size) ────────
                float2 px   = uv * _ScreenParams.xy;
                float2 cell = frac(px / 28.0);
                float2 edge = abs(cell - 0.5) * 2.0;      // 0 at centre, 1 at border
                float  grid = smoothstep(0.86, 1.0, max(edge.x, edge.y));

                // ── CRT scanline flicker (thin horizontal lines) ───────────
                float scanline = step(0.97, frac(uv.y * _ScreenParams.y * 0.5)) * 0.25;

                // ── Colour ────────────────────────────────────────────────
                // Slightly desaturate and darken the source at peak.
                half luma = dot(src.rgb, half3(0.299, 0.587, 0.114));
                half3 desaturated = lerp(src.rgb, half3(luma, luma, luma), env * 0.55);
                desaturated *= (1.0 - env * 0.18);

                // Cyan grid lines.
                half3 cyan = half3(0.15, 0.82, 1.0);
                half3 result = desaturated
                             + cyan * grid   * env * 0.95
                             + cyan * scanline * env;

                return half4(result, 1.0);
            }
            ENDHLSL
        }
    }
}
