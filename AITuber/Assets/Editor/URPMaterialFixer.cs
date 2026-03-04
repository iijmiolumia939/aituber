// URPMaterialFixer.cs
// AITuber メニュー → Fix URP Materials (TirgamesAssets) から実行するエディタツール。
// Built-in Standard シェーダーを使用したマテリアル（ピンク表示）を
// Universal Render Pipeline/Lit シェーダーに一括変換する。
//
// 変換内容:
//   Standard._MainTex   → URP._BaseMap
//   Standard._Color     → URP._BaseColor
//   Standard._Metallic  → URP._Metallic (そのまま)
//   Standard._Glossiness→ URP._Smoothness
//   Standard._BumpMap   → URP._BumpMap (そのまま)
//   Standard._EmissionMap/Color → URP._EmissionMap/Color (そのまま)

using System.Linq;
using UnityEditor;
using UnityEngine;

public static class URPMaterialFixer
{
    [MenuItem("AITuber/Fix URP Materials (TirgamesAssets)")]
    public static void FixTirgamesAssets()
    {
        var urpLitShader = Shader.Find("Universal Render Pipeline/Lit");
        if (urpLitShader == null)
        {
            Debug.LogError("[URPMaterialFixer] 'Universal Render Pipeline/Lit' シェーダーが見つかりません。" +
                           "URP がインストールされているか確認してください。");
            return;
        }

        var guids = AssetDatabase.FindAssets("t:Material", new[] { "Assets/TirgamesAssets" });
        if (guids.Length == 0)
        {
            Debug.LogWarning("[URPMaterialFixer] Assets/TirgamesAssets に Material が見つかりません。");
            return;
        }

        int count = 0;
        foreach (var guid in guids)
        {
            var path = AssetDatabase.GUIDToAssetPath(guid);
            var mat  = AssetDatabase.LoadAssetAtPath<Material>(path);
            if (mat == null) continue;

            // すでに URP シェーダーなら何もしない
            if (mat.shader != null && mat.shader.name.Contains("Universal Render Pipeline")) continue;

            Undo.RecordObject(mat, "Upgrade to URP Lit");

            // ── Standard → URP プロパティ退避 ──────────────────────
            Texture mainTex  = mat.HasProperty("_MainTex")      ? mat.GetTexture("_MainTex")      : null;
            Color   color    = mat.HasProperty("_Color")         ? mat.GetColor("_Color")          : Color.white;
            float   metallic = mat.HasProperty("_Metallic")      ? mat.GetFloat("_Metallic")       : 0f;
            float   smooth   = mat.HasProperty("_Glossiness")    ? mat.GetFloat("_Glossiness")     : 0.5f;
            Texture normal   = mat.HasProperty("_BumpMap")       ? mat.GetTexture("_BumpMap")      : null;
            Texture emission = mat.HasProperty("_EmissionMap")   ? mat.GetTexture("_EmissionMap")  : null;
            Color   emColor  = mat.HasProperty("_EmissionColor") ? mat.GetColor("_EmissionColor")  : Color.black;
            bool    hasEmit  = mat.IsKeywordEnabled("_EMISSION");

            // ── シェーダー切り替え ──────────────────────────────────
            mat.shader = urpLitShader;

            // ── URP パラメータに転記 ────────────────────────────────
            if (mainTex != null) mat.SetTexture("_BaseMap",   mainTex);
            mat.SetColor("_BaseColor", color);
            mat.SetFloat("_Metallic",  metallic);
            mat.SetFloat("_Smoothness", smooth);
            if (normal != null) mat.SetTexture("_BumpMap", normal);
            if (emission != null)
            {
                mat.SetTexture("_EmissionMap",   emission);
                mat.SetColor("_EmissionColor", emColor);
                if (hasEmit) mat.EnableKeyword("_EMISSION");
            }

            EditorUtility.SetDirty(mat);
            count++;
        }

        AssetDatabase.SaveAssets();
        AssetDatabase.Refresh();
        Debug.Log($"[URPMaterialFixer] {count} / {guids.Length} マテリアルを URP Lit に変換しました。" +
                  "\nAITuber メニュー → Fix URP Materials (TirgamesAssets) で再実行可能。");
    }
}
