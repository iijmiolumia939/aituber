using UnityEditor;
using UnityEngine;

/// One-shot setup: apply AITuber/CyberpunkToon to all MToon materials in scene.
/// Menu: AITuber/Apply CyberpunkToon to All Scene Materials
public static class CyberpunkToonApplyAll
{
    [MenuItem("AITuber/Apply CyberpunkToon to All Scene Materials")]
static void Run()
    {
        Shader toonShader  = Shader.Find("AITuber/CyberpunkToon");
        Shader glassShader = Shader.Find("Custom/Refraction");
        if (toonShader == null) { Debug.LogError("[CyberpunkToon] Shader not found!"); return; }

        // ── 1. VRM materials: copy _1st_ShadeMap → _ShadeMap ─────────────
        string[] vrmMatPaths = {
            "Assets/QuQu/U/TEX/Face/UFace.mat",
            "Assets/QuQu/U/TEX/costume/Materials/Ucostume.mat",
            "Assets/QuQu/U/TEX/hair/U_Hair.mat"
        };
        foreach (string path in vrmMatPaths)
        {
            Material mat = AssetDatabase.LoadAssetAtPath<Material>(path);
            if (mat == null) { Debug.LogWarning($"[CyberpunkToon] Material not found: {path}"); continue; }
            try
            {
                Texture shadeTex = mat.GetTexture("_1st_ShadeMap");
                Texture existing  = mat.GetTexture("_ShadeMap");
                Debug.Log($"[CyberpunkToon] {mat.name}: _1st_ShadeMap={shadeTex}, _ShadeMap={existing}");
                if (shadeTex != null && existing == null)
                {
                    mat.SetTexture("_ShadeMap", shadeTex);
                    EditorUtility.SetDirty(mat);
                    Debug.Log($"[CyberpunkToon] _ShadeMap fixed on {mat.name}");
                }
                else
                {
                    Debug.Log($"[CyberpunkToon] {mat.name}: _ShadeMap already set or no _1st_ShadeMap.");
                }
            }
            catch (System.Exception ex)
            {
                Debug.LogWarning($"[CyberpunkToon] {mat.name}: {ex.Message}");
            }
        }

        // ── 2. Restore GlassRefraction ────────────────────────────────────
        if (glassShader != null)
        {
            string[] guids = AssetDatabase.FindAssets("GlassRefraction t:Material");
            foreach (string g in guids)
            {
                string p = AssetDatabase.GUIDToAssetPath(g);
                Material m = AssetDatabase.LoadAssetAtPath<Material>(p);
                if (m != null && m.shader == toonShader)
                {
                    m.shader = glassShader;
                    EditorUtility.SetDirty(m);
                    Debug.Log($"[CyberpunkToon] Restored glass shader on {m.name}");
                }
            }
        }

        AssetDatabase.SaveAssets();
        Debug.Log("[CyberpunkToon] Fix pass done.");
    }

    // ─────────────────────────────────────────────────────────────────────
    // Restore all non-avatar materials that accidentally got CyberpunkToon
    // back to URP Lit.
    // ─────────────────────────────────────────────────────────────────────
    [MenuItem("AITuber/Restore Room Materials to URP Lit")]
    static void RestoreRoom()
    {
        Shader toonShader = Shader.Find("AITuber/CyberpunkToon");
        Shader litShader  = Shader.Find("Universal Render Pipeline/Lit");
        if (toonShader == null || litShader == null)
        {
            Debug.LogError("[CyberpunkToon] Shader not found!");
            return;
        }

        // VRM materials we intentionally keep as CyberpunkToon
        System.Collections.Generic.HashSet<string> keep = new()
        {
            "Assets/QuQu/U/TEX/Face/UFace.mat",
            "Assets/QuQu/U/TEX/costume/Materials/Ucostume.mat",
            "Assets/QuQu/U/TEX/hair/U_Hair.mat"
        };

        string[] allMats = AssetDatabase.FindAssets("t:Material");
        int count = 0;
        foreach (string guid in allMats)
        {
            string path = AssetDatabase.GUIDToAssetPath(guid);
            if (keep.Contains(path)) continue;

            Material mat = AssetDatabase.LoadAssetAtPath<Material>(path);
            if (mat != null && mat.shader == toonShader)
            {
                mat.shader = litShader;
                EditorUtility.SetDirty(mat);
                count++;
                Debug.Log($"[CyberpunkToon] Restored to Lit: {mat.name}");
            }
        }

        AssetDatabase.SaveAssets();
        Debug.Log($"[CyberpunkToon] Restored {count} materials to URP Lit.");
    }
}
