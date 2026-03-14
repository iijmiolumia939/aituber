// AvatarMaskWrite.shader
// Avatar geometry をマスク RT (R チャンネル = 1.0) として描画するための
// オーバーライドマテリアル用シェーダー。
//
// ColorMask R のみ書き込み。Cull Back + ZTest Always で前面ピクセルを全マーク。
// PixelizeFeature.AvatarMaskPass がこのシェーダーを override material として使用。
//
// SRS refs: FR-SHADER-02 (PixelArt mode)

Shader "AITuber/AvatarMaskWrite"
{
    SubShader
    {
        Tags { "RenderType" = "Opaque" "RenderPipeline" = "UniversalPipeline" "Queue" = "Geometry" }

        Pass
        {
            Name "AvatarMaskWrite"
            Tags { "LightMode" = "UniversalForward" }
            ZTest  Always   // シーン深度テスト不要（アバターは常に前景）
            ZWrite Off
            Cull   Back     // 自己裏面を除外
            ColorMask R     // R チャンネルにマスク値だけ書き込む

            HLSLPROGRAM
            #pragma vertex   Vert
            #pragma fragment Frag
            #pragma multi_compile_instancing

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"

            struct Attribs
            {
                float4 positionOS : POSITION;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                UNITY_VERTEX_OUTPUT_STEREO
            };

            Varyings Vert(Attribs IN)
            {
                UNITY_SETUP_INSTANCE_ID(IN);
                Varyings OUT;
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(OUT);
                OUT.positionCS = TransformObjectToHClip(IN.positionOS.xyz);
                return OUT;
            }

            // R=1 を書き込む → PixelizeScreen がマスクとして読む
            half4 Frag(Varyings IN) : SV_Target { return half4(1, 0, 0, 1); }
            ENDHLSL
        }
    }
}
