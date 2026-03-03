// BK_MaterialUpgrader.cs
// BK_AlchemistHouse フォルダ内の Standard シェーダーマテリアルを
// URP Lit に一括アップグレードするエディタツール。
// Unity メニュー: AITuber > Upgrade BK Materials to URP

using UnityEditor;
using UnityEngine;

namespace AITuber.Editor
{
    public static class BK_MaterialUpgrader
    {
        private const string SearchFolder = "Assets/BK_AlchemistHouse";

        [MenuItem("AITuber/Upgrade BK Materials to URP")]
        public static void Upgrade()
        {
            var guids = AssetDatabase.FindAssets("t:Material", new[] { SearchFolder });
            var urpLit = Shader.Find("Universal Render Pipeline/Lit");

            if (urpLit == null)
            {
                Debug.LogError("[BK_MaterialUpgrader] 'Universal Render Pipeline/Lit' not found. Is URP installed?");
                return;
            }

            int count = 0;
            foreach (var guid in guids)
            {
                var path = AssetDatabase.GUIDToAssetPath(guid);
                var mat  = AssetDatabase.LoadAssetAtPath<Material>(path);
                if (mat == null) continue;
                if (mat.shader == null) continue;
                if (!mat.shader.name.StartsWith("Standard") && !mat.shader.name.StartsWith("Legacy")) continue;

                // テクスチャ・プロパティを Standard から URP Lit へマッピング
                var albedo    = mat.HasProperty("_MainTex")        ? mat.GetTexture("_MainTex")        : null;
                var baseColor = mat.HasProperty("_Color")          ? mat.GetColor("_Color")            : Color.white;
                var normal    = mat.HasProperty("_BumpMap")        ? mat.GetTexture("_BumpMap")        : null;
                var occl      = mat.HasProperty("_OcclusionMap")   ? mat.GetTexture("_OcclusionMap")   : null;
                var emission  = mat.HasProperty("_EmissionColor")  ? mat.GetColor("_EmissionColor")    : Color.black;
                var emMap     = mat.HasProperty("_EmissionMap")    ? mat.GetTexture("_EmissionMap")    : null;
                var metallic  = mat.HasProperty("_Metallic")       ? mat.GetFloat("_Metallic")         : 0f;
                var gloss     = mat.HasProperty("_Glossiness")     ? mat.GetFloat("_Glossiness")       : 0.5f;
                var metMap    = mat.HasProperty("_MetallicGlossMap") ? mat.GetTexture("_MetallicGlossMap") : null;

                mat.shader = urpLit;

                if (albedo  != null) mat.SetTexture("_BaseMap",      albedo);
                mat.SetColor("_BaseColor", baseColor);
                if (normal  != null) mat.SetTexture("_BumpMap",      normal);
                if (occl    != null) mat.SetTexture("_OcclusionMap", occl);
                mat.SetColor("_EmissionColor", emission);
                if (emMap   != null) mat.SetTexture("_EmissionMap",  emMap);
                mat.SetFloat("_Metallic",    metallic);
                mat.SetFloat("_Smoothness",  gloss);
                if (metMap  != null) mat.SetTexture("_MetallicGlossMap", metMap);

                EditorUtility.SetDirty(mat);
                count++;
            }

            AssetDatabase.SaveAssets();
            AssetDatabase.Refresh();
            Debug.Log($"[BK_MaterialUpgrader] Upgraded {count} materials in {SearchFolder}");
        }
    }
}
