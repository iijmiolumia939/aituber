#ifndef SOBELOUTLINES_INCLUDED
#define SOBELOUTLINES_INCLUDED

// DecodeDepthNormals.hlsl includes URP 17 DeclareNormalsTexture + DeclareDepthTexture
// and exposes: DecodeDepthNormal(float2 uv, out float depth, out float3 normal)
#include "DecodeDepthNormals.hlsl"

// No _DepthNormalsTexture sampler — URP17 built-in textures are used instead.

static float2 sobelSamplePoints[4] = {
    float2(-1, 1), float2(1, 1), float2(-1, -1), float2(1, -1),
};

void GetDepthAndNormal(float2 uv, out float depth, out float3 normal)
{
    DecodeDepthNormal(uv, depth, normal);
}

// Wrapper for Custom Function node in Shader Graph
void CalculateDepthNormal_float(float2 UV, out float Depth, out float3 Normal)
{
    // SampleSceneNormals returns view-space [-1,1] directly in URP 17
    DecodeDepthNormal(UV, Depth, Normal);
}

void NormalsAndDepthSobel_float(float2 UV, float Thickness, out float Normals, out float Depth)
{
    float2 sobelX = 0;
    float2 sobelY = 0;
    float2 sobelZ = 0;
    float2 sobelDepth = 0;
    [unroll] for (int i = 0; i < 4; i++)
    {
        float  depth;
        float3 normal;
        GetDepthAndNormal(UV + sobelSamplePoints[i] * Thickness, depth, normal);
        float2 kernel = sobelSamplePoints[i];
        sobelX     += normal.x * kernel;
        sobelY     += normal.y * kernel;
        sobelZ     += normal.z * kernel;
        sobelDepth += depth    * kernel;
    }
    Normals = max(length(sobelX), max(length(sobelY), length(sobelZ)));
    Depth   = length(sobelDepth);
}

void ViewDirectionFromScreenUV_float(float2 In, out float3 Out)
{
    float2 p11_22 = float2(unity_CameraProjection._11, unity_CameraProjection._22);
    Out = -normalize(float3((In * 2 - 1) / p11_22, -1));
}

#endif
