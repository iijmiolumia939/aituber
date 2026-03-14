// SCSSApplier.cs
// Editor utility: applies Silent's Cel Shading Shader (SCSS) to MToon/URP materials
// on the selected GameObject (QuQu U.fbx avatar) while preserving texture and colour assignments.
// Note: SCSS is a Built-in RP shader. In URP projects it will show pink unless
//       a URP-compatible fork is used. Provided for Built-in RP / VRChat workflows.
//
// SRS refs: FR-SHADER-02
// SCSS package: Silent's Cel Shading Shader v1.11 (MIT)
// Available variants:
//   "Silent's Cel Shading/Lightramp"
//   "Silent's Cel Shading/Lightramp (Outline)"
//   "Silent's Cel Shading/Crosstone"
//   "Silent's Cel Shading/Crosstone (Outline)"

using System.Linq;
using UnityEditor;
using UnityEngine;

/// <summary>
/// One-click Editor tool to swap MToon/URP materials to SCSS on the selected avatar.
/// Use at Edit-time before enabling Runtime dynamic switching via AppearanceController.
/// Note: SCSS v1.11 targets Built-in RP. In URP projects materials will appear pink.
/// </summary>
public static class SCSSApplier
{
    // ── Shader variant menus ────────────────────────────────────────────────

    [MenuItem("AITuber/SCSS/Apply Lightramp (Outline) to Selected")]
    static void ApplyLightrampOutline() =>
        ApplyToSelected("Silent's Cel Shading/Lightramp (Outline)");

    [MenuItem("AITuber/SCSS/Apply Lightramp to Selected")]
    static void ApplyLightramp() =>
        ApplyToSelected("Silent's Cel Shading/Lightramp");

    [MenuItem("AITuber/SCSS/Apply Crosstone (Outline) to Selected")]
    static void ApplyCrosstoneOutline() =>
        ApplyToSelected("Silent's Cel Shading/Crosstone (Outline)");

    [MenuItem("AITuber/SCSS/Apply Crosstone to Selected")]
    static void ApplyCrosstone() =>
        ApplyToSelected("Silent's Cel Shading/Crosstone");

    [MenuItem("AITuber/SCSS/Apply Lightramp (Outline) to Selected", validate = true)]
    [MenuItem("AITuber/SCSS/Apply Lightramp to Selected",           validate = true)]
    [MenuItem("AITuber/SCSS/Apply Crosstone (Outline) to Selected", validate = true)]
    [MenuItem("AITuber/SCSS/Apply Crosstone to Selected",           validate = true)]
    static bool Validate() => Selection.activeGameObject != null;

    // ── Core implementation ─────────────────────────────────────────────────

    /// <summary>
    /// Applies the specified SCSS shader variant to all MToon/URP materials
    /// on the selected GameObject, preserving _MainTex, normal map, colours, etc.
    /// </summary>
    static void ApplyToSelected(string shaderName)
    {
        GameObject go = Selection.activeGameObject;
        if (go == null)
        {
            EditorUtility.DisplayDialog("SCSS", "ヒエラルキーで GameObject を選択してください。", "OK");
            return;
        }

        Shader scssShader = Shader.Find(shaderName);
        if (scssShader == null)
        {
            EditorUtility.DisplayDialog("SCSS",
                $"シェーダー '{shaderName}' が見つかりません。\n" +
                "「Silent's Shader v1.11 Package.unitypackage」を Assets にインポートしてから再実行してください。",
                "OK");
            return;
        }

        Renderer[] renderers = go.GetComponentsInChildren<Renderer>(true);
        var allMats = renderers
            .SelectMany(r => r.sharedMaterials)
            .Where(m => m != null)
            .Distinct()
            .Cast<Object>()
            .ToArray();

        if (allMats.Length == 0)
        {
            EditorUtility.DisplayDialog("SCSS", "対象マテリアルが見つかりませんでした。", "OK");
            return;
        }

        Undo.RecordObjects(allMats, $"Apply SCSS {shaderName}");

        int count = 0;
        foreach (Renderer rend in renderers)
        {
            Material[] mats = rend.sharedMaterials;
            bool changed = false;

            for (int i = 0; i < mats.Length; i++)
            {
                Material mat = mats[i];
                if (mat == null) continue;

                // Skip materials that are already using the target shader
                if (mat.shader == scssShader) continue;

                // ── Extract properties before shader swap ──────────────────

                Texture mainTex   = mat.HasProperty("_MainTex")      ? mat.GetTexture("_MainTex")      : null;
                Texture normalMap = mat.HasProperty("_BumpMap")       ? mat.GetTexture("_BumpMap")       :
                                    mat.HasProperty("_NormalMap")     ? mat.GetTexture("_NormalMap")     : null;
                Texture shadeTex  = mat.HasProperty("_ShadeTexture")  ? mat.GetTexture("_ShadeTexture")  : null;
                Texture emitTex   = mat.HasProperty("_EmissionMap")   ? mat.GetTexture("_EmissionMap")   : null;

                Color baseColor  = mat.HasProperty("_Color")         ? mat.GetColor("_Color")        : Color.white;
                Color shadeColor = mat.HasProperty("_ShadeColor")     ? mat.GetColor("_ShadeColor")   : new Color(0.7f, 0.7f, 0.8f, 1f);
                Color emitColor  = mat.HasProperty("_EmissionColor")  ? mat.GetColor("_EmissionColor") : Color.black;

                // ── Swap shader ───────────────────────────────────────────

                mat.shader = scssShader;

                // ── Re-apply base properties ──────────────────────────────
                // SCSS Lightramp/Crosstone use "_MainTex" for albedo

                if (mainTex   != null) mat.SetTexture("_MainTex", mainTex);
                if (shadeTex  != null) mat.SetTexture("_ShadingGradeMap", shadeTex);
                if (normalMap != null) mat.SetTexture("_BumpMap",  normalMap);
                if (emitTex   != null) mat.SetTexture("_EmissionMap", emitTex);

                mat.SetColor("_Color",          baseColor);
                mat.SetColor("_ShadowColor",    shadeColor);
                mat.SetColor("_EmissionColor",  emitColor);

                // SCSS: enable normal map if we assigned one
                if (normalMap != null)
                    mat.SetFloat("_BumpScale", 1f);

                EditorUtility.SetDirty(mat);
                changed = true;
                count++;
            }

            if (changed)
                EditorUtility.SetDirty(rend);
        }

        AssetDatabase.SaveAssets();
        Debug.Log($"[SCSSApplier] {count} マテリアルに '{shaderName}' を適用しました。");
        EditorUtility.DisplayDialog("SCSS", $"{count} マテリアルに適用しました。\n({shaderName})", "OK");
    }
}
