#ifndef CYBERPUNK_TOON_OUTLINE_PASS_INCLUDED
#define CYBERPUNK_TOON_OUTLINE_PASS_INCLUDED

#include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"
#include "CyberpunkToonInput.hlsl"

// -------------------------------------------------------------------------
// Outline vertex: expand mesh along world-space normals (inverted hull)
// Scales width by distance to keep outline visually constant on screen.
// -------------------------------------------------------------------------
struct OutlineVaryings
{
    float4 positionCS : SV_POSITION;
    float3 positionWS : TEXCOORD0;
    UNITY_VERTEX_OUTPUT_STEREO
};

OutlineVaryings OutlineVertex(Attributes IN)
{
    OutlineVaryings OUT;
    UNITY_SETUP_INSTANCE_ID(IN);
    UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(OUT);

    VertexNormalInputs normInputs = GetVertexNormalInputs(IN.normalOS, IN.tangentOS);

    float3 posWS = TransformObjectToWorld(IN.positionOS.xyz);

    // Scale outline width by camera distance for screen-stable thickness
    float dist = length(GetWorldSpaceViewDir(posWS));
    float3 expandedWS = posWS + normInputs.normalWS * (_OutlineWidth * dist * 0.1);

    OUT.positionCS = TransformWorldToHClip(expandedWS);
    OUT.positionWS = posWS;
    return OUT;
}

// -------------------------------------------------------------------------
// Outline fragment: flat outline color, optionally lit by main light
// -------------------------------------------------------------------------
half4 OutlineFragment(OutlineVaryings IN) : SV_Target
{
    UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(IN);

    half3 outlineColor = _OutlineColor.rgb;

    // Optional: darken outline by main light direction so it feels grounded
    if (_OutlineLightingDimmer > 0.0)
    {
        Light mainLight = GetMainLight();
        float lit = saturate(dot(normalize(mainLight.direction), float3(0, 1, 0)));
        outlineColor = lerp(outlineColor, outlineColor * mainLight.color, _OutlineLightingDimmer * lit);
    }

    return half4(outlineColor, 1.0);
}

#endif // CYBERPUNK_TOON_OUTLINE_PASS_INCLUDED
