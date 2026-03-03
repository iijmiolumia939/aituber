#ifndef CYBERPUNK_TOON_INPUT_INCLUDED
#define CYBERPUNK_TOON_INPUT_INCLUDED

// SurfaceInput.hlsl already includes Core.hlsl and declares:
//   TEXTURE2D(_BaseMap), SAMPLER(sampler_BaseMap)
//   TEXTURE2D(_BumpMap),  SAMPLER(sampler_BumpMap)
//   TEXTURE2D(_EmissionMap), SAMPLER(sampler_EmissionMap)
#include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/SurfaceInput.hlsl"

// -------------------------------------------------------------------------
// Custom textures not declared in SurfaceInput.hlsl
// -------------------------------------------------------------------------
TEXTURE2D(_ShadeMap);      SAMPLER(sampler_ShadeMap);
TEXTURE2D(_NormalMap);     SAMPLER(sampler_NormalMap);
TEXTURE2D(_MatCapMap);     SAMPLER(sampler_MatCapMap);
TEXTURE2D(_HighLightMask); SAMPLER(sampler_HighLightMask);
TEXTURE2D(_RimMask);       SAMPLER(sampler_RimMask);

// -------------------------------------------------------------------------
// Per-Material CBUFFER  (must be IDENTICAL across every pass that uses SRP Batcher)
// -------------------------------------------------------------------------
CBUFFER_START(UnityPerMaterial)
    // Base
    float4 _BaseMap_ST;
    float4 _BaseColor;
    float4 _ShadeColor;

    // Toon shadow step
    float  _BaseStep;
    float  _StepSmooth;

    // MidTone
    float  _UseMidTone;
    float4 _MidToneColor;
    float  _MidToneThickness;

    // Normal map
    float  _UseNormalMap;
    float  _BumpScale;

    // Rim Light
    float  _UseRimLight;
    float4 _RimColor;
    float  _RimPower;
    float  _RimSmooth;
    float  _RimIntensity;

    // HighLight (stylized specular)
    float  _UseHighLight;
    float4 _HighLightColor;
    float  _HighLightPower;
    float  _HighLightSmooth;

    // MatCap
    float  _UseMatCap;
    float  _MatCapWeight;
    float  _MatCapMode;     // 0 = Add, 1 = Multiply

    // Emission
    float4 _EmissionColor;
    float  _EmissionIntensity;

    // Outline
    float4 _OutlineColor;
    float  _OutlineWidth;
    float  _OutlineLightingDimmer;

    // Alpha
    float  _AlphaCutoff;
    float  _UseAlphaCutoff;
CBUFFER_END


// -------------------------------------------------------------------------
// Shared vertex structures
// -------------------------------------------------------------------------
struct Attributes
{
    float4 positionOS : POSITION;
    float3 normalOS   : NORMAL;
    float4 tangentOS  : TANGENT;
    float2 uv         : TEXCOORD0;
    UNITY_VERTEX_INPUT_INSTANCE_ID
};

struct Varyings
{
    float4 positionCS  : SV_POSITION;
    float2 uv          : TEXCOORD0;
    float3 normalWS    : TEXCOORD1;
    float3 tangentWS   : TEXCOORD2;
    float3 bitangentWS : TEXCOORD3;
    float3 positionWS  : TEXCOORD4;
    float  fogFactor   : TEXCOORD5;
    UNITY_VERTEX_OUTPUT_STEREO
};

#endif // CYBERPUNK_TOON_INPUT_INCLUDED
