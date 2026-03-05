using System.Linq;
using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering;

/// <summary>
/// Editor utility: replaces VRM MToon / MToon10 materials on the selected
/// GameObject with AITuber/CyberpunkToon while preserving texture assignments.
/// Menu: AITuber > Apply CyberpunkToon to VRM
/// </summary>
public static class CyberpunkToonApplier
{
    const string SHADER_NAME = "AITuber/CyberpunkToon";

    [MenuItem("AITuber/Apply CyberpunkToon to VRM")]
    static void ApplyToSelected()
    {
        GameObject go = Selection.activeGameObject;
        if (go == null)
        {
            EditorUtility.DisplayDialog("CyberpunkToon", "ヒエラルキーで VRM の GameObject を選択してください。", "OK");
            return;
        }

        Shader toonShader = Shader.Find(SHADER_NAME);
        if (toonShader == null)
        {
            EditorUtility.DisplayDialog("CyberpunkToon",
                $"シェーダー '{SHADER_NAME}' が見つかりません。\nAssets/Shaders/CyberpunkToon.shader が正しくコンパイルされているか確認してください。",
                "OK");
            return;
        }

        int count = 0;
        Renderer[] renderers = go.GetComponentsInChildren<Renderer>(true);

        Undo.RecordObjects(
            renderers.SelectMany(r => r.sharedMaterials).Where(m => m != null).Cast<Object>().ToArray(),
            "Apply CyberpunkToon"
        );

        foreach (Renderer rend in renderers)
        {
            Material[] mats = rend.sharedMaterials;
            bool changed = false;

            for (int i = 0; i < mats.Length; i++)
            {
                Material mat = mats[i];
                if (mat == null) continue;

                string sn = mat.shader != null ? mat.shader.name : "";
                bool isMToon = sn.Contains("MToon") || sn.Contains("VRM") || sn.Contains("UniGLTF");
                if (!isMToon) continue;

                // -- Extract textures before shader swap --
                Texture mainTex    = mat.HasProperty("_MainTex")         ? mat.GetTexture("_MainTex")         : null;
                Texture shadeTex   = mat.HasProperty("_ShadeTexture")    ? mat.GetTexture("_ShadeTexture")    : null;
                Texture normalMap  = mat.HasProperty("_BumpMap")         ? mat.GetTexture("_BumpMap")         :
                                     mat.HasProperty("_NormalMap")        ? mat.GetTexture("_NormalMap")        : null;
                Texture emissionTx = mat.HasProperty("_EmissionMap")     ? mat.GetTexture("_EmissionMap")     : null;

                // Colors
                Color baseCol  = mat.HasProperty("_Color")       ? mat.GetColor("_Color")       : Color.white;
                Color shadeCol = mat.HasProperty("_ShadeColor")  ? mat.GetColor("_ShadeColor")  : new Color(0.35f, 0.25f, 0.45f);
                Color emitCol  = mat.HasProperty("_EmissionColor") ? mat.GetColor("_EmissionColor") : Color.black;

                // -- Swap shader --
                mat.shader = toonShader;

                // -- Re-apply base properties --
                if (mainTex   != null) mat.SetTexture("_BaseMap",    mainTex);
                if (shadeTex  != null) mat.SetTexture("_ShadeMap",   shadeTex);
                if (normalMap != null)
                {
                    mat.SetTexture("_NormalMap", normalMap);
                    mat.SetFloat("_UseNormalMap", 1f);
                }
                if (emissionTx != null) mat.SetTexture("_EmissionMap", emissionTx);

                mat.SetColor("_BaseColor",  baseCol);
                mat.SetColor("_ShadeColor", shadeCol);
                mat.SetColor("_EmissionColor", emitCol);

                // -- Cyberpunk defaults: neon cyan rim, dark outline --
                mat.SetFloat("_UseRimLight",   1f);
                mat.SetColor("_RimColor",      new Color(0f, 1f, 1f, 1f));   // cyan
                mat.SetFloat("_RimPower",      3f);
                mat.SetFloat("_RimIntensity",  1.8f);

                mat.SetColor("_OutlineColor",  new Color(0.04f, 0.02f, 0.08f, 1f));
                mat.SetFloat("_OutlineWidth",  0.003f);

                mat.SetFloat("_UseHighLight",  1f);
                mat.SetColor("_HighLightColor", new Color(0.9f, 0.8f, 1f, 1f));
                mat.SetFloat("_HighLightPower", 64f);

                EditorUtility.SetDirty(mat);
                changed = true;
                count++;
            }

            if (changed)
                EditorUtility.SetDirty(rend);
        }

        AssetDatabase.SaveAssets();
        Debug.Log($"[CyberpunkToon] {count} マテリアルに CyberpunkToon シェーダーを適用しました。");
        EditorUtility.DisplayDialog("CyberpunkToon", $"{count} マテリアルに適用しました。", "OK");
    }

    [MenuItem("AITuber/Apply CyberpunkToon to VRM", validate = true)]
    static bool ApplyValidate() => Selection.activeGameObject != null;

    /// <summary>
    /// Applies CyberpunkToon shader to every material under Assets/QuQu/U/TEX/
    /// without requiring a selected GameObject.  FR-SHADER-01.
    /// </summary>
    [MenuItem("AITuber/Apply CyberpunkToon to All VRM Materials")]
    public static void ApplyToAllVrmMaterials()
    {
        const string SearchFolder = "Assets/QuQu/U/TEX";
        Shader toonShader = Shader.Find(SHADER_NAME);
        if (toonShader == null)
        {
            Debug.LogError($"[CyberpunkToon] Shader not found: {SHADER_NAME}");
            return;
        }

        var guids = AssetDatabase.FindAssets("t:Material", new[] { SearchFolder });
        if (guids.Length == 0)
        {
            Debug.LogWarning($"[CyberpunkToon] No materials found in {SearchFolder}");
            return;
        }

        int converted = 0;
        foreach (var guid in guids)
        {
            var path = AssetDatabase.GUIDToAssetPath(guid);
            var mat  = AssetDatabase.LoadAssetAtPath<Material>(path);
            if (mat == null) continue;
            if (mat.shader != null && mat.shader.name == SHADER_NAME)
            {
                Debug.Log($"  SKIP {path} (already CyberpunkToon)");
                continue;
            }

            // Snapshot
            Texture mainTex   = mat.HasProperty("_MainTex")       ? mat.GetTexture("_MainTex")       :
                                 mat.HasProperty("_BaseMap")       ? mat.GetTexture("_BaseMap")       : null;
            Texture shadeTex  = mat.HasProperty("_ShadeTexture")  ? mat.GetTexture("_ShadeTexture")  : null;
            Texture normalMap = mat.HasProperty("_BumpMap")        ? mat.GetTexture("_BumpMap")       :
                                mat.HasProperty("_NormalMap")      ? mat.GetTexture("_NormalMap")     : null;
            Texture emisTex   = mat.HasProperty("_EmissionMap")   ? mat.GetTexture("_EmissionMap")   : null;
            Color baseCol     = mat.HasProperty("_Color")         ? mat.GetColor("_Color")           :
                                mat.HasProperty("_BaseColor")      ? mat.GetColor("_BaseColor")       : Color.white;
            Color shadeCol    = mat.HasProperty("_ShadeColor")    ? mat.GetColor("_ShadeColor")      : new Color(0.35f, 0.25f, 0.45f);
            Color emitCol     = mat.HasProperty("_EmissionColor") ? mat.GetColor("_EmissionColor")   : Color.black;

            // Swap
            mat.shader = toonShader;

            if (mainTex   != null) mat.SetTexture("_BaseMap",    mainTex);
            if (shadeTex  != null) mat.SetTexture("_ShadeMap",   shadeTex);
            if (normalMap != null) { mat.SetTexture("_NormalMap", normalMap); mat.SetFloat("_UseNormalMap", 1f); }
            if (emisTex   != null) mat.SetTexture("_EmissionMap", emisTex);

            mat.SetColor("_BaseColor",    baseCol);
            mat.SetColor("_ShadeColor",   shadeCol);
            mat.SetColor("_EmissionColor",emitCol);

            // Cyberpunk defaults
            mat.SetFloat("_UseRimLight",  1f);
            mat.SetColor("_RimColor",     new Color(0f, 1f, 1f, 1f));
            mat.SetFloat("_RimPower",     3f);
            mat.SetFloat("_RimIntensity", 1.8f);
            mat.SetColor("_OutlineColor", new Color(0.04f, 0.02f, 0.08f, 1f));
            mat.SetFloat("_OutlineWidth", 0.003f);
            mat.SetFloat("_UseHighLight", 1f);
            mat.SetColor("_HighLightColor", new Color(0.9f, 0.8f, 1f, 1f));
            mat.SetFloat("_HighLightPower", 64f);

            EditorUtility.SetDirty(mat);
            Debug.Log($"  APPLIED {path}");
            converted++;
        }

        AssetDatabase.SaveAssets();
        Debug.Log($"[CyberpunkToon] FR-SHADER-01 complete: {converted}/{guids.Length} マテリアルに適用しました。");
        EditorUtility.DisplayDialog("CyberpunkToon", $"FR-SHADER-01: {converted} マテリアルに適用しました。", "OK");
    }
}
