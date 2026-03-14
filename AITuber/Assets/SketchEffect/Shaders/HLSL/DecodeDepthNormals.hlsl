// URP 17 (Unity 6) compatible depth/normals sampling.
// Uses URP built-in DeclareNormalsTexture + DeclareDepthTexture.
// Requires in URP Renderer Asset:
//   Depth Texture: Enabled
//   Normals: any feature that requests ScriptableRenderPassInput.Normal
//            (e.g. SSAO, Depth Priming Mode != Disabled)

#ifndef DECODEDEPTHNORMALS_INCLUDED
#define DECODEDEPTHNORMALS_INCLUDED

#include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/DeclareNormalsTexture.hlsl"
#include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/DeclareDepthTexture.hlsl"

// depth  : raw depth buffer value (0..1)
// normal : view-space normal in [-1, 1]
inline void DecodeDepthNormal(float2 uv, out float depth, out float3 normal)
{
    depth  = SampleSceneDepth(uv);
    normal = SampleSceneNormals(uv);   // returns view-space [-1, 1]
}

#endif
