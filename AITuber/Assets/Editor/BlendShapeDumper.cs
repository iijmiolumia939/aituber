using UnityEditor;
using UnityEngine;

/// <summary>
/// シーン内の SkinnedMeshRenderer のブレンドシェイプ名一覧をコンソールに出力する。
/// AITuber/Dump BlendShape Names を実行してください。
/// </summary>
public static class BlendShapeDumper
{
    [MenuItem("AITuber/Dump BlendShape Names (Selected or All)")]
    public static void DumpAll()
    {
        var renderers = Object.FindObjectsByType<SkinnedMeshRenderer>(FindObjectsSortMode.None);
        if (renderers.Length == 0)
        {
            Debug.LogWarning("[BlendShapeDumper] No SkinnedMeshRenderer found in scene.");
            return;
        }

        var allSb = new System.Text.StringBuilder();
        foreach (var smr in renderers)
        {
            if (smr.sharedMesh == null) continue;
            int count = smr.sharedMesh.blendShapeCount;
            if (count == 0) continue;

            var sb = new System.Text.StringBuilder();
            sb.AppendLine($"=== {smr.name} ({smr.gameObject.GetInstanceID()}) : {count} blend shapes ===");
            for (int idx = 0; idx < count; idx++)
            {
                string n = smr.sharedMesh.GetBlendShapeName(idx);
                float w = smr.GetBlendShapeWeight(idx);
                string tag = "";
                string nl = n.ToLower();
                if (nl.Contains("mth") || nl.Contains("mouth") || nl.Contains("_a") || nl == "a"
                    || nl == "i" || nl == "u" || nl == "e" || nl == "o"
                    || nl.EndsWith("_a") || nl.EndsWith("_i") || nl.EndsWith("_u")
                    || nl.EndsWith("_e") || nl.EndsWith("_o")
                    || nl.Contains("vrc.v_"))
                    tag = " *** MOUTH/VRC";
                if (nl.Contains("blink") || nl.Contains("eye"))
                    tag = " --- EYE/BLINK";
                sb.AppendLine($"  [{idx:D3}] {n}{tag}");
            }
            Debug.Log(sb.ToString());
            allSb.Append(sb.ToString());
        }

        // Write to file so it can be read externally
        string outPath = System.IO.Path.Combine(
            System.IO.Path.GetDirectoryName(Application.dataPath),
            "Temp", "blendshape_dump.txt");
        System.IO.File.WriteAllText(outPath, allSb.ToString());
        Debug.Log($"[BlendShapeDumper] Written to: {outPath}");
    }
}
