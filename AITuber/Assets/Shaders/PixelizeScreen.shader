// PixelizeScreen.shader
// Full-screen nearest-neighbour blit used by PixelizeFeature.
// Quantises screen UV coordinates to simulate a low-resolution display.
//
// When _AvatarMaskRT is available (avatar-only mode), only pixels where
// mask.r > 0.5 are pixelized; background is passed through unchanged.
// When _AvatarMaskRT is not set, the whole screen is pixelized (fallback).
//
// SRS refs: FR-SHADER-02 (PixelArt mode)

Shader "AITuber/PixelizeScreen"
{
    SubShader
    {
        Tags { "RenderType" = "Opaque" "RenderPipeline" = "UniversalPipeline" }

        Pass
        {
            Name "PixelizePass"
            ZTest Always
            ZWrite Off
            Cull Off

            HLSLPROGRAM
            #pragma vertex Vert
            #pragma fragment Frag
            #pragma target 3.5

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            #include "Packages/com.unity.render-pipelines.core/Runtime/Utilities/Blit.hlsl"

            // Set per-frame by PixelizeFeature.AddRenderPasses from material properties.
            float _ResolutionX;
            float _ResolutionY;

            // Avatar mask RT (R channel = 1 for avatar pixels, 0 for background).
            // Set by AvatarMaskPass via Shader.SetGlobalTexture.
            // If never written, defaults to a 1x1 white texture → full-screen pixelize.
            TEXTURE2D(_AvatarMaskRT);
            SAMPLER(sampler_AvatarMaskRT);

            half4 Frag(Varyings input) : SV_Target
            {
                UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(input);
                float2 uv = input.texcoord;

                // Nearest-neighbour pixelized UV
                float2 pixelUV = (floor(uv * float2(_ResolutionX, _ResolutionY)) + 0.5)
                                / float2(_ResolutionX, _ResolutionY);

                half4 pixelCol = SAMPLE_TEXTURE2D_X(_BlitTexture, sampler_PointClamp,   pixelUV);
                half4 origCol  = SAMPLE_TEXTURE2D_X(_BlitTexture, sampler_LinearClamp,  uv);

                // Avatar mask: 1 = pixelize, 0 = pass-through
                float mask = SAMPLE_TEXTURE2D(_AvatarMaskRT, sampler_AvatarMaskRT, uv).r;

                return lerp(origCol, pixelCol, mask);
            }
            ENDHLSL
        }
    }
}