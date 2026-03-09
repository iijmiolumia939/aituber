#ifndef CYBERPUNK_TOON_FORWARD_PASS_INCLUDED
#define CYBERPUNK_TOON_FORWARD_PASS_INCLUDED

#include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"
#include "CyberpunkToonInput.hlsl"

// -------------------------------------------------------------------------
// Vertex
// -------------------------------------------------------------------------
Varyings ToonVertex(Attributes IN)
{
    Varyings OUT;
    UNITY_SETUP_INSTANCE_ID(IN);
    UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(OUT);

    VertexPositionInputs posInputs  = GetVertexPositionInputs(IN.positionOS.xyz);
    VertexNormalInputs   normInputs = GetVertexNormalInputs(IN.normalOS, IN.tangentOS);

    OUT.positionCS    = posInputs.positionCS;
    OUT.positionWS    = posInputs.positionWS;
    OUT.normalWS      = normInputs.normalWS;
    OUT.tangentWS     = normInputs.tangentWS;
    OUT.bitangentWS   = normInputs.bitangentWS;
    OUT.uv            = TRANSFORM_TEX(IN.uv, _BaseMap);
    OUT.fogFactor     = ComputeFogFactor(posInputs.positionCS.z);
    return OUT;
}

// -------------------------------------------------------------------------
// Helper: MatCap UV from view-space normal
// -------------------------------------------------------------------------
float2 MatCapUV(float3 normalWS)
{
    float3 normalVS = TransformWorldToViewDir(normalWS, true);
    return normalVS.xy * 0.5 + 0.5;
}

// -------------------------------------------------------------------------
// Fragment
// -------------------------------------------------------------------------
half4 ToonFragment(Varyings IN) : SV_Target
{
    UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(IN);

    float2 uv = IN.uv;

    // --- Base / Shade textures ---
    half4 baseSample  = SAMPLE_TEXTURE2D(_BaseMap,  sampler_BaseMap,  uv);
    half4 shadeSample = SAMPLE_TEXTURE2D(_ShadeMap, sampler_ShadeMap, uv);
    half4 baseColor   = baseSample  * _BaseColor;
    half3 shadeColor  = shadeSample.rgb * _ShadeColor.rgb;

    // Alpha cutoff
    if (_UseAlphaCutoff > 0.5 && baseColor.a < _AlphaCutoff) discard;

    // --- Normal ---
    float3 N = normalize(IN.normalWS);
    if (_UseNormalMap > 0.5)
    {
        half4 normalSample = SAMPLE_TEXTURE2D(_NormalMap, sampler_NormalMap, uv);
        float3 normalTS    = UnpackNormalScale(normalSample, _BumpScale);
        float3x3 TBN       = float3x3(
            normalize(IN.tangentWS),
            normalize(IN.bitangentWS),
            normalize(IN.normalWS)
        );
        N = normalize(mul(normalTS, TBN));
    }

    float3 V = normalize(GetWorldSpaceViewDir(IN.positionWS));

    // =========================================================
    // MAIN LIGHT
    // =========================================================
    float4 shadowCoord = TransformWorldToShadowCoord(IN.positionWS);
    Light  mainLight   = GetMainLight(shadowCoord);

    float3 L        = normalize(mainLight.direction);
    float3 H        = normalize(L + V);
    float  NdotL    = dot(N, L);
    float  shadowA  = mainLight.shadowAttenuation * mainLight.distanceAttenuation;

    // ── Half-Lambert (lilToon/PotaToon compatible) ──────────────────────
    // Map NdotL from [-1,1] to [0,1] for soft anime shadows.
    // Shadow attenuation dims the value so cast shadows still show.
    float  hlLit    = (NdotL * 0.5 + 0.5) * saturate(shadowA);

    // Toon step: _BaseStep is in [-1,1] space – remap to [0,1] to match hlLit.
    float  stepC    = (_BaseStep + 1.0) * 0.5;  // e.g. _BaseStep=0 → stepC=0.5
    float  toonT    = smoothstep(
        stepC - max(_StepSmooth, 0.001),
        stepC + max(_StepSmooth, 0.001),
        hlLit
    );

    // SH Ambient: bleeds into shadow so dark areas are not pure flat colour
    half3 ambient      = max(half3(0, 0, 0), SampleSH(N)) * _AmbientInfluence;
    half3 shadeWithAmb = shadeColor + ambient * baseColor.rgb;

    // Apply light color separately to direct/indirect (lilToon key technique).
    // min() prevents shadow region from glowing brighter than the lit region.
    half3 directCol   = baseColor.rgb   * mainLight.color;
    half3 indirectCol = shadeWithAmb    * mainLight.color;
    indirectCol       = min(indirectCol, directCol);

    // MidTone boundary gradient (also in [0,1] space)
    half3 litCol = lerp(indirectCol, directCol, toonT);
    if (_UseMidTone > 0.5)
    {
        float hw  = max(_MidToneThickness * 0.5, 0.001);
        float mLo = smoothstep(stepC - hw, stepC,      hlLit);
        float mHi = smoothstep(stepC,      stepC + hw, hlLit);
        float mB  = mLo * (1.0 - mHi);   // peaks at the boundary
        half3 midCol = lerp(indirectCol, _MidToneColor.rgb * baseColor.rgb * mainLight.color, 0.5);
        litCol = lerp(litCol, midCol, mB);
    }

    // HighLight (stylized specular) under main light
    half3 highlight = half3(0, 0, 0);
    if (_UseHighLight > 0.5)
    {
        float NdotH   = saturate(dot(N, H));
        float specRaw = pow(NdotH, max(_HighLightPower, 1.0));
        float specT   = smoothstep(
            0.5 - max(_HighLightSmooth, 0.001),
            0.5 + max(_HighLightSmooth, 0.001),
            specRaw
        );
        specT *= toonT; // only in lit area
        half hlMask   = SAMPLE_TEXTURE2D(_HighLightMask, sampler_HighLightMask, uv).r;
        highlight    += specT * _HighLightColor.rgb * mainLight.color * hlMask;
    }

    // Hair Highlight (upward-shifted specular, camera-elevation modulated)
    if (_UseHairHighlight > 0.5)
    {
        float3 shiftedN  = normalize(N + float3(0, _HairHighlightShift, 0));
        float  NdotHhair = saturate(dot(shiftedN, H));
        float  hairSpec  = pow(NdotHhair, max(_HairHighlightPower, 1.0));
        float  hairT     = smoothstep(
            0.5 - max(_HairHighlightSmooth, 0.001),
            0.5 + max(_HairHighlightSmooth, 0.001),
            hairSpec
        );
        hairT *= toonT; // only in lit area
        // Stronger when camera is above (V.y→1), softer from front (V.y→0)
        float viewUp = saturate(dot(normalize(V), float3(0, 1, 0)) * 0.5 + 0.75);
        half  hhMask = SAMPLE_TEXTURE2D(_HairHighlightMask, sampler_HairHighlightMask, uv).r;
        highlight += hairT * _HairHighlightColor.rgb * mainLight.color * hhMask * viewUp;
    }

    // =========================================================
    // ADDITIONAL LIGHTS
    // =========================================================
    half3 addCol = half3(0, 0, 0);

    #ifdef _ADDITIONAL_LIGHTS
    uint lightCount = GetAdditionalLightsCount();
    LIGHT_LOOP_BEGIN(lightCount)
    {
        Light addLight  = GetAdditionalLight(lightIndex, IN.positionWS, half4(1,1,1,1));
        float3 La       = normalize(addLight.direction);
        float3 Ha       = normalize(La + V);
        float  NdotLa   = dot(N, La);
        float  attA     = addLight.distanceAttenuation * addLight.shadowAttenuation;
        // Half-Lambert for additional lights too
        float  hlLitA   = (NdotLa * 0.5 + 0.5) * saturate(attA);

        float toonTA = smoothstep(
            stepC - max(_StepSmooth, 0.001),
            stepC + max(_StepSmooth, 0.001),
            hlLitA
        );
        half3 dirA   = baseColor.rgb   * addLight.color;
        half3 indA   = shadeWithAmb    * addLight.color;
        indA         = min(indA, dirA);
        half3 diffA  = lerp(indA, dirA, toonTA);
        addCol += diffA * 0.5;

        if (_UseHighLight > 0.5)
        {
            float NdotHa  = saturate(dot(N, Ha));
            float specRawA= pow(NdotHa, max(_HighLightPower, 1.0));
            float specTA  = smoothstep(
                0.5 - max(_HighLightSmooth, 0.001),
                0.5 + max(_HighLightSmooth, 0.001),
                specRawA
            ) * toonTA;
            half hlMaskA  = SAMPLE_TEXTURE2D(_HighLightMask, sampler_HighLightMask, uv).r;
            highlight += specTA * _HighLightColor.rgb * addLight.color * hlMaskA;
        }
    }
    LIGHT_LOOP_END
    #endif

    // =========================================================
    // RIM LIGHT (Neon / Fresnel)
    // =========================================================
    half3 rim = half3(0, 0, 0);
    if (_UseRimLight > 0.5)
    {
        float NdotV   = saturate(dot(N, V));
        float rimRaw  = pow(1.0 - NdotV, max(_RimPower, 0.01));
        float rimT    = smoothstep(
            0.5 - max(_RimSmooth, 0.001),
            0.5 + max(_RimSmooth, 0.001),
            rimRaw
        );
        half rimMask  = SAMPLE_TEXTURE2D(_RimMask, sampler_RimMask, uv).r;
        rim = rimT * _RimColor.rgb * _RimIntensity * rimMask;
    }

    // =========================================================
    // MATCAP
    // =========================================================
    half3 matcap = half3(0, 0, 0);
    if (_UseMatCap > 0.5)
    {
        float2 mcUV   = MatCapUV(N);
        half3  mcSample = SAMPLE_TEXTURE2D(_MatCapMap, sampler_MatCapMap, mcUV).rgb;
        if (_MatCapMode < 0.5)
            matcap = mcSample * _MatCapWeight;         // Add
        // Multiply is applied after assembly below
    }

    // =========================================================
    // EMISSION
    // =========================================================
    half3 emission = SAMPLE_TEXTURE2D(_EmissionMap, sampler_EmissionMap, uv).rgb
                     * _EmissionColor.rgb * _EmissionIntensity;

    // =========================================================
    // COMBINE
    // =========================================================
    half3 col = litCol + addCol + highlight + rim + matcap + emission;

    // MatCap Multiply mode
    if (_UseMatCap > 0.5 && _MatCapMode > 0.5)
    {
        float2 mcUV  = MatCapUV(N);
        half3 mcSamp = SAMPLE_TEXTURE2D(_MatCapMap, sampler_MatCapMap, mcUV).rgb;
        col = lerp(col, col * mcSamp, _MatCapWeight);
    }

    // Color Grading: boost saturation in lit region, pull back in shadow
    {
        float satFactor = lerp(_ShadowSaturation, _LitSaturation, toonT);
        float lum = dot(col, float3(0.299, 0.587, 0.114));
        col = lerp(half3(lum, lum, lum), col, satFactor);
    }

    // Fog
    col = MixFog(col, IN.fogFactor);

    return half4(col, baseColor.a);
}

#endif // CYBERPUNK_TOON_FORWARD_PASS_INCLUDED
