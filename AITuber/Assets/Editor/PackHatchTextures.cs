using System.IO;
using UnityEngine;
using UnityEditor;

/// <summary>
/// hatch_0..5.png を 2枚のRGB packed テクスチャに変換して SE_Avatar.mat に割り当てる
/// Hatch0 = R:hatch_0, G:hatch_1, B:hatch_2
/// Hatch1 = R:hatch_3, G:hatch_4, B:hatch_5
/// </summary>
public static class PackHatchTextures
{
    [MenuItem("Tools/Pack Hatch Textures and Apply")]
    public static void PackAndApply()
    {
        string hatchDir = "Assets/SketchEffect/Textures/Hatch";
        string outDir   = "Assets/SketchEffect/Textures";

        string[] srcPaths = new string[6];
        for (int i = 0; i < 6; i++)
            srcPaths[i] = $"{hatchDir}/hatch_{i}.png";

        // ---- pack into 2 RGB textures ----
        Texture2D hatchPacked0 = PackRGB(srcPaths[0], srcPaths[1], srcPaths[2]);
        Texture2D hatchPacked1 = PackRGB(srcPaths[3], srcPaths[4], srcPaths[5]);

        if (hatchPacked0 == null || hatchPacked1 == null) { Debug.LogError("[PackHatch] source textures not found"); return; }

        string out0 = outDir + "/Hatch0_packed.png";
        string out1 = outDir + "/Hatch1_packed.png";

        File.WriteAllBytes(Application.dataPath.Substring(0, Application.dataPath.Length - 6) + out0, hatchPacked0.EncodeToPNG());
        File.WriteAllBytes(Application.dataPath.Substring(0, Application.dataPath.Length - 6) + out1, hatchPacked1.EncodeToPNG());

        AssetDatabase.Refresh();

        // Force linear (no sRGB) for hatch textures
        SetLinear(out0);
        SetLinear(out1);

        AssetDatabase.Refresh();

        // ---- assign to SE_Avatar.mat ----
        string matPath = "Assets/SketchEffect/Materials/SE_Avatar.mat";
        Material mat = AssetDatabase.LoadAssetAtPath<Material>(matPath);
        if (mat == null) { Debug.LogError($"[PackHatch] material not found at {matPath}"); return; }

        Texture2D tex0 = AssetDatabase.LoadAssetAtPath<Texture2D>(out0);
        Texture2D tex1 = AssetDatabase.LoadAssetAtPath<Texture2D>(out1);

        mat.SetTexture("Texture2D_f5b1096f690a40c3a67e1389086d2a11",   tex0);  // Hatch0
        mat.SetTexture("Texture2D_f5b1096f690a40c3a67e1389086d2a11_1", tex1);  // Hatch1
        EditorUtility.SetDirty(mat);
        AssetDatabase.SaveAssets();

        Debug.Log("[PackHatch] Done — Hatch0_packed.png / Hatch1_packed.png assigned to SE_Avatar.mat");
    }

    static Texture2D PackRGB(string rPath, string gPath, string bPath)
    {
        Texture2D tR = LoadReadable(rPath);
        Texture2D tG = LoadReadable(gPath);
        Texture2D tB = LoadReadable(bPath);
        if (tR == null || tG == null || tB == null) return null;

        int w = tR.width, h = tR.height;
        Texture2D packed = new Texture2D(w, h, TextureFormat.RGB24, false, true);
        Color[] pixels = new Color[w * h];
        for (int i = 0; i < pixels.Length; i++)
        {
            pixels[i] = new Color(
                tR.GetPixel(i % w, i / w).r,
                tG.GetPixel(i % w, i / w).r,
                tB.GetPixel(i % w, i / w).r,
                1f);
        }
        packed.SetPixels(pixels);
        packed.Apply();
        return packed;
    }

    static Texture2D LoadReadable(string assetPath)
    {
        string absPath = Application.dataPath.Substring(0, Application.dataPath.Length - 6) + assetPath;
        if (!File.Exists(absPath)) { Debug.LogError($"[PackHatch] not found: {absPath}"); return null; }
        byte[] bytes = File.ReadAllBytes(absPath);
        Texture2D t = new Texture2D(2, 2, TextureFormat.ARGB32, false);
        t.LoadImage(bytes);
        return t;
    }

    static void SetLinear(string assetPath)
    {
        TextureImporter imp = AssetImporter.GetAtPath(assetPath) as TextureImporter;
        if (imp == null) return;
        imp.sRGBTexture = false;
        imp.wrapMode = TextureWrapMode.Repeat;
        imp.filterMode = FilterMode.Bilinear;
        imp.SaveAndReimport();
    }
}
