using UnityEngine;
using UnityEditor;
using System.IO;

public static class CreateSketchMaterialTool
{
    [MenuItem("Tools/Create SketchEffect Material")]
    public static void CreateMaterial()
    {
        string dir = "Assets/SketchEffect/Materials";
        if (!AssetDatabase.IsValidFolder(dir))
            AssetDatabase.CreateFolder("Assets/SketchEffect", "Materials");

        string matPath = dir + "/SE_Avatar.mat";

        Shader shader = Shader.Find("Shader Graphs/SketchEffect");
        if (shader == null) { Debug.LogError("Shader not found: Shader Graphs/SketchEffect"); return; }

        Material mat = new Material(shader);

        Texture2D hatch0 = AssetDatabase.LoadAssetAtPath<Texture2D>("Assets/SketchEffect/Textures/Hatch/darkest.png");
        Texture2D hatch1 = AssetDatabase.LoadAssetAtPath<Texture2D>("Assets/SketchEffect/Textures/Hatch/brightest.png");
        if (hatch0 != null) mat.SetTexture("_Hatch0", hatch0);
        else Debug.LogWarning("darkest.png not found");
        if (hatch1 != null) mat.SetTexture("_Hatch1", hatch1);
        else Debug.LogWarning("brightest.png not found");

        AssetDatabase.CreateAsset(mat, matPath);
        AssetDatabase.SaveAssets();
        AssetDatabase.Refresh();
        Debug.Log("SE_Avatar.mat created at " + matPath);

        GameObject[] all = Resources.FindObjectsOfTypeAll<GameObject>();
        foreach (var go in all)
        {
            if (go.name == "Body")
            {
                var smr = go.GetComponent<SkinnedMeshRenderer>();
                if (smr != null)
                {
                    smr.sharedMaterial = AssetDatabase.LoadAssetAtPath<Material>(matPath);
                    Debug.Log("Applied SE_Avatar material to Body SkinnedMeshRenderer");
                }
            }
        }
    }
}
