// SetupShaderTransition.cs
// Editor utility: one-click setup for the ShaderTransitionGrid renderer feature
// and the PixelizeScreen renderer feature.
//
// Usage: AITuber > Shader Transition > Setup (add to Renderer)
//
// What it does:
//   1. Creates Assets/Shaders/ShaderTransitionGrid.mat from the grid shader.
//   2. Finds PC_Renderer.asset (UniversalRendererData) in the project.
//   3. Creates and adds a ShaderTransitionFeature with the material, if not already present.
//   4. Creates Assets/Shaders/PixelizeScreen.mat and adds PixelizeFeature, if not present.
//
// SRS refs: FR-SHADER-TRANSITION-01, FR-SHADER-02 (PixelArt mode)

using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering.Universal;
using AITuber.Rendering;

public static class SetupShaderTransition
{
    const string ShaderPath           = "Assets/Shaders/ShaderTransitionGrid.shader";
    const string MatPath              = "Assets/Shaders/ShaderTransitionGrid.mat";
    const string AvatarShaderPath     = "Assets/Shaders/ShaderTransitionAvatar.shader";
    const string AvatarMatPath        = "Assets/Shaders/ShaderTransitionAvatar.mat";
    const string PixelizeShaderPath      = "Assets/Shaders/PixelizeScreen.shader";
    const string PixelizeMatPath         = "Assets/Shaders/PixelizeScreen.mat";
    const string AvatarMaskShaderPath    = "Assets/Shaders/AvatarMaskWrite.shader";
    const string AvatarMaskMatPath       = "Assets/Shaders/AvatarMaskWrite.mat";
    const string FeatureName             = "ShaderTransitionGrid";
    const string PixelizeFeatureName     = "PixelizeScreen";

    [MenuItem("AITuber/Shader Transition/Setup (add to Renderer)")]
    static void Setup()
    {
        // ── 1. Shader ─────────────────────────────────────────────────────
        var shader = AssetDatabase.LoadAssetAtPath<Shader>(ShaderPath);
        if (shader == null)
        {
            Debug.LogError($"[SetupShaderTransition] Shader not found at '{ShaderPath}'. " +
                           "Make sure ShaderTransitionGrid.shader exists.");
            return;
        }

        // ── 2. Material ───────────────────────────────────────────────────
        var mat = AssetDatabase.LoadAssetAtPath<Material>(MatPath);
        if (mat == null)
        {
            mat = new Material(shader) { name = FeatureName };
            AssetDatabase.CreateAsset(mat, MatPath);
            AssetDatabase.SaveAssets();
            Debug.Log($"[SetupShaderTransition] Created material at '{MatPath}'.");
        }

        // ── 2b. Avatar transition material ───────────────────────────────────────
        var avatarShader = AssetDatabase.LoadAssetAtPath<Shader>(AvatarShaderPath);
        if (avatarShader == null)
        {
            Debug.LogWarning($"[SetupShaderTransition] Avatar shader not found at '{AvatarShaderPath}'. " +
                             "Assign ShaderTransitionAvatar.mat to AppearanceController manually.");
        }
        else if (AssetDatabase.LoadAssetAtPath<Material>(AvatarMatPath) == null)
        {
            var avatarMat = new Material(avatarShader) { name = "ShaderTransitionAvatar" };
            AssetDatabase.CreateAsset(avatarMat, AvatarMatPath);
            AssetDatabase.SaveAssets();
            Debug.Log($"[SetupShaderTransition] Created avatar material at '{AvatarMatPath}'.");
        }

        // ── 2c. PixelizeScreen material ─────────────────────────────────────────
        var pixelizeShader = AssetDatabase.LoadAssetAtPath<Shader>(PixelizeShaderPath);
        if (pixelizeShader == null)
        {
            Debug.LogWarning($"[SetupShaderTransition] PixelizeScreen shader not found at '{PixelizeShaderPath}'.");
        }
        else if (AssetDatabase.LoadAssetAtPath<Material>(PixelizeMatPath) == null)
        {
            var pixelizeMat = new Material(pixelizeShader) { name = "PixelizeScreen" };
            AssetDatabase.CreateAsset(pixelizeMat, PixelizeMatPath);
            AssetDatabase.SaveAssets();
            Debug.Log($"[SetupShaderTransition] Created pixelize material at '{PixelizeMatPath}'.");
        }
        // ── 2d. AvatarMaskWrite material ────────────────────────────────────────
        var avatarMaskShader = AssetDatabase.LoadAssetAtPath<Shader>(AvatarMaskShaderPath);
        if (avatarMaskShader == null)
        {
            Debug.LogWarning($"[SetupShaderTransition] AvatarMaskWrite shader not found at '{AvatarMaskShaderPath}'.");
        }
        else if (AssetDatabase.LoadAssetAtPath<Material>(AvatarMaskMatPath) == null)
        {
            var maskMat = new Material(avatarMaskShader) { name = "AvatarMaskWrite" };
            AssetDatabase.CreateAsset(maskMat, AvatarMaskMatPath);
            AssetDatabase.SaveAssets();
            Debug.Log($"[SetupShaderTransition] Created avatar mask material at '{AvatarMaskMatPath}'.");
        }
        // ── 3. Find renderer data ─────────────────────────────────────────
        var renderer = FindRenderer();
        if (renderer == null)
        {
            Debug.LogError("[SetupShaderTransition] Could not find UniversalRendererData " +
                           "(looking for 'PC_Renderer'). Assign manually in the Renderer inspector.");
            return;
        }

        // ── 4. Add ShaderTransitionGrid feature if not present ───────────────
        bool hasTransition = false;
        foreach (var f in renderer.rendererFeatures)
        {
            if (f != null && f.name == FeatureName) { hasTransition = true; break; }
        }
        if (!hasTransition)
        {
            var feature = ScriptableObject.CreateInstance<ShaderTransitionFeature>();
            feature.name         = FeatureName;
            feature.passMaterial = mat;
            AssetDatabase.AddObjectToAsset(feature, renderer);
            renderer.rendererFeatures.Add(feature);
            EditorUtility.SetDirty(renderer);
            Debug.Log($"[SetupShaderTransition] '{FeatureName}' added to renderer '{renderer.name}'.");
        }
        else
        {
            Debug.Log("[SetupShaderTransition] ShaderTransitionGrid already exists — skipped.");
        }

        // ── 5. Add PixelizeScreen feature if not present ──────────────────────
        bool hasPixelize = false;
        foreach (var f in renderer.rendererFeatures)
        {
            if (f is PixelizeFeature) { hasPixelize = true; break; }
        }
        if (!hasPixelize)
        {
            var pixelizeMat = AssetDatabase.LoadAssetAtPath<Material>(PixelizeMatPath);
            var maskMat     = AssetDatabase.LoadAssetAtPath<Material>(AvatarMaskMatPath);
            if (pixelizeMat == null)
            {
                Debug.LogWarning($"[SetupShaderTransition] PixelizeScreen.mat not found at '{PixelizeMatPath}'. " +
                                 "Run Setup again after PixelizeScreen.shader is imported.");
            }
            else
            {
                var pixelizeFeature = ScriptableObject.CreateInstance<PixelizeFeature>();
                pixelizeFeature.name         = PixelizeFeatureName;
                pixelizeFeature.passMaterial = pixelizeMat;
                pixelizeFeature.maskMaterial = maskMat; // may be null at first import; reassign after re-run
                AssetDatabase.AddObjectToAsset(pixelizeFeature, renderer);
                renderer.rendererFeatures.Add(pixelizeFeature);
                EditorUtility.SetDirty(renderer);
                Debug.Log($"[SetupShaderTransition] '{PixelizeFeatureName}' added to renderer '{renderer.name}'.");
            }
        }
        else
        {
            // Feature already exists — update maskMaterial if it was missing (first run had no AvatarMaskWrite.mat)
            var maskMat = AssetDatabase.LoadAssetAtPath<Material>(AvatarMaskMatPath);
            if (maskMat != null)
            {
                foreach (var f in renderer.rendererFeatures)
                {
                    if (f is PixelizeFeature pf && pf.maskMaterial == null)
                    {
                        pf.maskMaterial = maskMat;
                        EditorUtility.SetDirty(renderer);
                        Debug.Log("[SetupShaderTransition] Assigned AvatarMaskWrite.mat to existing PixelizeFeature.");
                    }
                }
            }
            Debug.Log("[SetupShaderTransition] PixelizeScreen feature already exists — skipped.");
        }

        AssetDatabase.SaveAssets();
        Debug.Log("[SetupShaderTransition] Setup complete.");
    }

    static UniversalRendererData FindRenderer()
    {
        // Prefer a renderer named "PC_Renderer".
        var guids = AssetDatabase.FindAssets("t:UniversalRendererData");
        UniversalRendererData fallback = null;

        foreach (var guid in guids)
        {
            var path = AssetDatabase.GUIDToAssetPath(guid);
            var data = AssetDatabase.LoadAssetAtPath<UniversalRendererData>(path);
            if (data == null) continue;
            if (path.Contains("PC_Renderer")) return data;
            fallback = data;
        }
        return fallback;
    }
}
