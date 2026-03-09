using System.Collections.Generic;
using UnityEditor;
using UnityEngine;

/// <summary>
/// Custom ShaderGUI for AITuber/CyberpunkToon.
/// Groups properties into collapsible sections ala PotaToon style.
/// </summary>
public class CyberpunkToonGUI : ShaderGUI
{
    // ── Section fold states ───────────────────────────────────────────────
    static readonly Dictionary<string, bool> s_Folds = new();

    static bool Fold(string key, string label)
    {
        if (!s_Folds.ContainsKey(key)) s_Folds[key] = true;
        Color prev = GUI.backgroundColor;
        GUI.backgroundColor = new Color(0.18f, 0.18f, 0.22f);
        s_Folds[key] = EditorGUILayout.Foldout(s_Folds[key], "  " + label,
            true, EditorStyles.foldoutHeader);
        GUI.backgroundColor = prev;
        return s_Folds[key];
    }

    public override void OnGUI(MaterialEditor editor, MaterialProperty[] props)
    {
        Material mat = editor.target as Material;

        // ── Base ─────────────────────────────────────────────────────────
        if (Fold("base", "⬛ Base"))
        {
            editor.ShaderProperty(Find("_BaseMap",    props), "Base (Lit) Map");
            editor.ShaderProperty(Find("_BaseColor",  props), "Base Color");
            editor.ShaderProperty(Find("_ShadeMap",   props), "Shade (Shadow) Map");
            editor.ShaderProperty(Find("_ShadeColor", props), "Shade Color");
        }
        EditorGUILayout.Space(2);

        // ── Toon Step ─────────────────────────────────────────────────────
        if (Fold("step", "🌒 Toon Shadow Step"))
        {
            editor.ShaderProperty(Find("_BaseStep",   props), "Base Step");
            editor.ShaderProperty(Find("_StepSmooth", props), "Step Smoothness");
        }
        EditorGUILayout.Space(2);

        // ── MidTone ───────────────────────────────────────────────────────
        if (Fold("mid", "🟣 MidTone"))
        {
            editor.ShaderProperty(Find("_UseMidTone",      props), "Use MidTone");
            if (mat.GetFloat("_UseMidTone") > 0.5f)
            {
                editor.ShaderProperty(Find("_MidToneColor",      props), "MidTone Color");
                editor.ShaderProperty(Find("_MidToneThickness",  props), "MidTone Thickness");
            }
        }
        EditorGUILayout.Space(2);

        // ── Normal Map ────────────────────────────────────────────────────
        if (Fold("normal", "🗺 Normal Map"))
        {
            editor.ShaderProperty(Find("_UseNormalMap", props), "Use Normal Map");
            if (mat.GetFloat("_UseNormalMap") > 0.5f)
            {
                editor.ShaderProperty(Find("_NormalMap", props), "Normal Map");
                editor.ShaderProperty(Find("_BumpScale", props), "Bump Scale");
            }
        }
        EditorGUILayout.Space(2);

        // ── Rim Light ─────────────────────────────────────────────────────
        if (Fold("rim", "💫 Rim Light (Neon)"))
        {
            editor.ShaderProperty(Find("_UseRimLight",  props), "Use Rim Light");
            if (mat.GetFloat("_UseRimLight") > 0.5f)
            {
                editor.ShaderProperty(Find("_RimColor",     props), "Rim Color");
                editor.ShaderProperty(Find("_RimPower",     props), "Rim Power");
                editor.ShaderProperty(Find("_RimSmooth",    props), "Rim Smoothness");
                editor.ShaderProperty(Find("_RimIntensity", props), "Rim Intensity");
                editor.ShaderProperty(Find("_RimMask",      props), "Rim Mask (R=on)");
            }
        }
        EditorGUILayout.Space(2);

        // ── HighLight ─────────────────────────────────────────────────────
        if (Fold("hl", "✨ HighLight (Specular)"))
        {
            editor.ShaderProperty(Find("_UseHighLight",   props), "Use HighLight");
            if (mat.GetFloat("_UseHighLight") > 0.5f)
            {
                editor.ShaderProperty(Find("_HighLightColor",  props), "HighLight Color");
                editor.ShaderProperty(Find("_HighLightPower",  props), "HighLight Power");
                editor.ShaderProperty(Find("_HighLightSmooth", props), "HighLight Smooth");
                editor.ShaderProperty(Find("_HighLightMask",   props), "HighLight Mask (R=on)");
            }
        }
        EditorGUILayout.Space(2);

        // ── Hair Highlight ────────────────────────────────────────────────
        if (Fold("hh", "💇 Hair Highlight"))
        {
            editor.ShaderProperty(Find("_UseHairHighlight",   props), "Use Hair Highlight");
            if (mat.GetFloat("_UseHairHighlight") > 0.5f)
            {
                editor.ShaderProperty(Find("_HairHighlightColor",  props), "Color");
                editor.ShaderProperty(Find("_HairHighlightPower",  props), "Power");
                editor.ShaderProperty(Find("_HairHighlightSmooth", props), "Smooth");
                editor.ShaderProperty(Find("_HairHighlightShift",  props), "Height Shift");
                editor.ShaderProperty(Find("_HairHighlightMask",   props), "Mask (R=on)");
            }
        }
        EditorGUILayout.Space(2);

        // ── Ambient ───────────────────────────────────────────────────────
        if (Fold("amb", "🌐 Ambient (SH)"))
        {
            editor.ShaderProperty(Find("_AmbientInfluence", props), "Ambient Influence");
        }
        EditorGUILayout.Space(2);

        // ── Color Grading ─────────────────────────────────────────────────
        if (Fold("cg", "🎨 Color Grading"))
        {
            editor.ShaderProperty(Find("_LitSaturation",    props), "Lit Saturation");
            editor.ShaderProperty(Find("_ShadowSaturation", props), "Shadow Saturation");
        }
        EditorGUILayout.Space(2);

        // ── MatCap ────────────────────────────────────────────────────────
        if (Fold("mc", "🔮 MatCap"))
        {
            editor.ShaderProperty(Find("_UseMatCap",   props), "Use MatCap");
            if (mat.GetFloat("_UseMatCap") > 0.5f)
            {
                editor.ShaderProperty(Find("_MatCapMap",    props), "MatCap Map");
                editor.ShaderProperty(Find("_MatCapWeight", props), "Weight");
                editor.ShaderProperty(Find("_MatCapMode",   props), "Mode (Add / Multiply)");
            }
        }
        EditorGUILayout.Space(2);

        // ── Emission ──────────────────────────────────────────────────────
        if (Fold("em", "💡 Emission"))
        {
            editor.ShaderProperty(Find("_EmissionMap",       props), "Emission Map");
            editor.ShaderProperty(Find("_EmissionColor",     props), "Emission Color (HDR)");
            editor.ShaderProperty(Find("_EmissionIntensity", props), "Emission Intensity");
        }
        EditorGUILayout.Space(2);

        // ── Outline ───────────────────────────────────────────────────────
        if (Fold("ol", "🖊 Outline"))
        {
            editor.ShaderProperty(Find("_OutlineColor",          props), "Outline Color");
            editor.ShaderProperty(Find("_OutlineWidth",          props), "Outline Width");
            editor.ShaderProperty(Find("_OutlineLightingDimmer", props), "Lighting Dimmer");
        }
        EditorGUILayout.Space(2);

        // ── Alpha / Render ────────────────────────────────────────────────
        if (Fold("alpha", "⚙ Alpha / Render"))
        {
            editor.ShaderProperty(Find("_UseAlphaCutoff", props), "Alpha Cutoff");
            if (mat.GetFloat("_UseAlphaCutoff") > 0.5f)
                editor.ShaderProperty(Find("_AlphaCutoff", props), "Cutoff Threshold");
            editor.ShaderProperty(Find("_Cull", props), "Cull Mode");
        }
        EditorGUILayout.Space(4);

        editor.RenderQueueField();
        editor.EnableInstancingField();
    }

    static MaterialProperty Find(string name, MaterialProperty[] props)
        => FindProperty(name, props, false);
}
