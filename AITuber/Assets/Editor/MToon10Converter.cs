using UnityEditor;
using UnityEngine;
using System.Collections.Generic;

/// <summary>
/// Converts CyberpunkToon materials under Assets/QuQu/U/TEX/ to MToon10 URP shader.
/// Property mapping:
///   _MainTex / _BaseMap  →  _MainTex
///   _1st_ShadeMap / _ShadeTexture  →  _ShadeTex
///   _ShadeColor  →  _ShadeColor
///   _BumpMap  →  _BumpMap
///   _EmissionMap  →  _EmissionMap
///   _EmissionColor  →  _EmissionColor
///   _Color / _BaseColor  →  _Color
///   _ShadeToony  →  _ShadingToonyFactor
///   _ShadeShift  →  _ShadingShiftFactor
///   _Outline_Color / _OutlineColor  →  _OutlineColor
///   _Outline_Width / _OutlineWidth  →  _OutlineWidth
/// </summary>
public static class MToon10Converter
{
    private const string SearchFolder = "Assets/QuQu/U/TEX";
    private const string MToon10ShaderName = "VRM10/Universal Render Pipeline/MToon10";

    [MenuItem("AITuber/Convert Materials to MToon10 URP")]
    public static void ConvertAll()
    {
        var shader = Shader.Find(MToon10ShaderName);
        if (shader == null)
        {
            Debug.LogError($"[MToon10Converter] Shader not found: {MToon10ShaderName}");
            return;
        }

        var guids = AssetDatabase.FindAssets("t:Material", new[] { SearchFolder });
        if (guids.Length == 0)
        {
            Debug.LogWarning($"[MToon10Converter] No materials found in {SearchFolder}");
            return;
        }

        int converted = 0;
        var results = new List<string>();

        foreach (var guid in guids)
        {
            var path = AssetDatabase.GUIDToAssetPath(guid);
            var mat = AssetDatabase.LoadAssetAtPath<Material>(path);
            if (mat == null) continue;

            // Skip if already MToon10
            if (mat.shader != null && mat.shader.name == MToon10ShaderName)
            {
                results.Add($"  SKIP  {path} (already MToon10)");
                continue;
            }

            // ---- Snapshot values from current shader ----
            Texture mainTex  = GetTex(mat, "_MainTex", "_BaseMap");
            Texture shadeTex = GetTex(mat, "_1st_ShadeMap", "_ShadeTexture", "_ShadeMap");
            Texture bumpMap  = GetTex(mat, "_BumpMap");
            Texture emisTex  = GetTex(mat, "_EmissionMap");
            Texture outlineWidthTex = GetTex(mat, "_OutlineTex", "_OutlineWidthTexture");

            Color baseColor  = GetColor(mat, "_Color", "_BaseColor");
            Color shadeColor = GetColor(mat, "_ShadeColor", "_1st_ShadeColor");
            Color emisColor  = GetColor(mat, "_EmissionColor", "_Emissive_Color");
            Color outlineColor = GetColor(mat, "_Outline_Color", "_OutlineColor");
            Color rimColor   = GetColor(mat, "_RimColor", "_RimLightColor");

            float toony  = GetFloat(mat, "_ShadeToony",   defaultVal: 0.9f);
            float shift  = GetFloat(mat, "_ShadeShift",   defaultVal: -0.05f);
            float outlineWidth = GetFloat(mat, "_Outline_Width", "_OutlineWidth", defaultVal: 0f);
            float rimFresnelPower = GetFloat(mat, "_RimFresnelPower", defaultVal: 5f);
            float rimLift  = GetFloat(mat, "_RimLift", defaultVal: 0f);
            float bumpScale = GetFloat(mat, "_BumpScale", defaultVal: 1f);

            // ---- Switch shader ----
            mat.shader = shader;

            // ---- Apply textures ----
            if (mainTex  != null) mat.SetTexture("_MainTex",  mainTex);
            if (shadeTex != null) mat.SetTexture("_ShadeTex", shadeTex);
            if (bumpMap  != null) mat.SetTexture("_BumpMap",  bumpMap);
            if (emisTex  != null) mat.SetTexture("_EmissionMap", emisTex);
            if (outlineWidthTex != null) mat.SetTexture("_OutlineWidthTex", outlineWidthTex);

            // ---- Apply colors ----
            mat.SetColor("_Color",      baseColor);
            mat.SetColor("_ShadeColor", shadeColor);
            mat.SetColor("_EmissionColor", emisColor);
            mat.SetColor("_OutlineColor", outlineColor);
            mat.SetColor("_RimColor",   rimColor);

            // ---- Apply floats ----
            mat.SetFloat("_ShadingToonyFactor", Mathf.Clamp01(toony));
            mat.SetFloat("_ShadingShiftFactor", Mathf.Clamp(shift, -1f, 1f));
            mat.SetFloat("_OutlineWidth", Mathf.Clamp(outlineWidth / 100f, 0f, 0.05f)); // convert cm→m approx
            mat.SetFloat("_RimFresnelPower", rimFresnelPower);
            mat.SetFloat("_RimLift", rimLift);
            mat.SetFloat("_BumpScale", bumpScale);

            // MToon10 keywords
            if (bumpMap != null)
                mat.EnableKeyword("_NORMALMAP");
            if (emisTex != null || emisColor != Color.black)
                mat.EnableKeyword("_MTOON_EMISSIVEMAP");

            EditorUtility.SetDirty(mat);
            converted++;
            results.Add($"  OK    {path}");
            Debug.Log($"[MToon10Converter] Converted: {path}");
        }

        AssetDatabase.SaveAssets();
        AssetDatabase.Refresh();

        var summary = $"[MToon10Converter] Done. Converted {converted}/{guids.Length} materials.\n" + string.Join("\n", results);
        Debug.Log(summary);
    }

    // ---- Helpers ----
    private static Texture GetTex(Material mat, params string[] names)
    {
        foreach (var n in names)
        {
            if (!mat.HasProperty(n)) continue;
            var t = mat.GetTexture(n);
            if (t != null) return t;
        }
        return null;
    }

    private static Color GetColor(Material mat, params string[] names)
    {
        foreach (var n in names)
        {
            if (!mat.HasProperty(n)) continue;
            return mat.GetColor(n);
        }
        return Color.white;
    }

    private static float GetFloat(Material mat, string name, string fallback = null, float defaultVal = 0f)
    {
        if (mat.HasProperty(name)) return mat.GetFloat(name);
        if (fallback != null && mat.HasProperty(fallback)) return mat.GetFloat(fallback);
        return defaultVal;
    }

    private static float GetFloat(Material mat, string name, float defaultVal)
        => mat.HasProperty(name) ? mat.GetFloat(name) : defaultVal;
}
