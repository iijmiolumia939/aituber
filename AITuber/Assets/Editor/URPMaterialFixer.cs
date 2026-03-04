// URPMaterialFixer.cs
// AITuber メニュー → Fix URP Materials から実行するエディタツール。
// Built-in Standard / UTS2 など非 URP シェーダーを
// Universal Render Pipeline/Lit シェーダーに一括変換する。
//
// 変換内容:
//   Standard._MainTex   → URP._BaseMap
//   Standard._Color     → URP._BaseColor
//   UTS2._BaseMap       → URP._BaseMap (既にあれば保持)
//   missing shader      → URP._BaseMap + _BaseColor (ピンク解消)

using UnityEditor;
using UnityEngine;

public static class URPMaterialFixer
{
    // ── アバター (Ququ / UTS2 → URP Lit) ─────────────────────────────
    [MenuItem("AITuber/Fix URP Materials (Avatar Ququ)")]
    public static void FixAvatarMaterials()
    {
        FixMaterials(new[] { "Assets/Ququ" },
            label: "アバター(Ququ)",
            convertMissing: true);
    }

    [MenuItem("AITuber/Fix URP Materials (TirgamesAssets)")]
    public static void FixTirgamesAssets()
    {
        FixMaterials(new[] { "Assets/TirgamesAssets" },
            label: "TirgamesAssets",
            convertMissing: false);
    }

    // ── 共通変換ロジック ─────────────────────────────────────────────
    private static void FixMaterials(string[] searchFolders, string label, bool convertMissing = false)
    {
        var urpLitShader = Shader.Find("Universal Render Pipeline/Lit");
        if (urpLitShader == null)
        {
            Debug.LogError("[URPMaterialFixer] 'Universal Render Pipeline/Lit' が見つかりません。");
            return;
        }

        var guids = AssetDatabase.FindAssets("t:Material", searchFolders);
        if (guids.Length == 0)
        {
            Debug.LogWarning($"[URPMaterialFixer] {label} に Material が見つかりません。");
            return;
        }

        int count = 0;
        foreach (var guid in guids)
        {
            var path = AssetDatabase.GUIDToAssetPath(guid);
            var mat  = AssetDatabase.LoadAssetAtPath<Material>(path);
            if (mat == null) continue;

            bool isMissing = mat.shader == null || mat.shader.name == "Hidden/InternalErrorShader";
            bool isURP     = mat.shader != null && mat.shader.name.Contains("Universal Render Pipeline");

            if (isURP) continue;
            if (!convertMissing && !isMissing)
            {
                // Standard シェーダーのみ変換
                if (!mat.shader.name.Contains("Standard")) continue;
            }

            Undo.RecordObject(mat, "Upgrade to URP Lit");

            // ── テクスチャ・カラー退避 ────────────────────────────────
            // UTS2/MToon は _BaseMap が既にセット済みのことが多い
            Texture mainTex  = null;
            if (mat.HasProperty("_BaseMap"))   mainTex = mat.GetTexture("_BaseMap");
            if (mainTex == null && mat.HasProperty("_MainTex")) mainTex = mat.GetTexture("_MainTex");

            Color   color    = Color.white;
            if (mat.HasProperty("_BaseColor"))  color = mat.GetColor("_BaseColor");
            else if (mat.HasProperty("_Color")) color = mat.GetColor("_Color");

            float   metallic = mat.HasProperty("_Metallic")    ? mat.GetFloat("_Metallic")    : 0f;
            float   smooth   = mat.HasProperty("_Smoothness")  ? mat.GetFloat("_Smoothness")  :
                               mat.HasProperty("_Glossiness")  ? mat.GetFloat("_Glossiness")  : 0f;
            Texture normal   = mat.HasProperty("_BumpMap")       ? mat.GetTexture("_BumpMap")      : null;
            Texture emission = mat.HasProperty("_EmissionMap")   ? mat.GetTexture("_EmissionMap")  : null;
            Color   emColor  = mat.HasProperty("_EmissionColor") ? mat.GetColor("_EmissionColor")  : Color.black;
            bool    hasEmit  = mat.IsKeywordEnabled("_EMISSION");

            // ── シェーダー切り替え ────────────────────────────────────
            mat.shader = urpLitShader;

            // ── URP パラメータに転記 ──────────────────────────────────
            if (mainTex != null) mat.SetTexture("_BaseMap", mainTex);
            mat.SetColor("_BaseColor",   color);
            mat.SetFloat("_Metallic",    metallic);
            mat.SetFloat("_Smoothness",  smooth);
            if (normal   != null) mat.SetTexture("_BumpMap",      normal);
            if (emission != null)
            {
                mat.SetTexture("_EmissionMap",  emission);
                mat.SetColor("_EmissionColor", emColor);
                if (hasEmit) mat.EnableKeyword("_EMISSION");
            }

            EditorUtility.SetDirty(mat);
            count++;
        }

        AssetDatabase.SaveAssets();
        AssetDatabase.Refresh();
        Debug.Log($"[URPMaterialFixer] {label}: {count} / {guids.Length} マテリアルを URP Lit に変換しました。");
    }
}
