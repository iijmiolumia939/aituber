using UnityEngine;
using UnityEditor;
using UnityEditor.SceneManagement;

/// <summary>
/// SE_Avatar.mat を Body の SkinnedMeshRenderer に適用してシーンを保存する
/// </summary>
public static class ApplySketchMaterial
{
    [MenuItem("Tools/Apply Sketch Material to Body (Save Scene)")]
    public static void Apply()
    {
        string matPath = "Assets/SketchEffect/Materials/SE_Avatar.mat";
        Material mat = AssetDatabase.LoadAssetAtPath<Material>(matPath);
        if (mat == null) { Debug.LogError("[ApplySketch] SE_Avatar.mat not found"); return; }

        int applied = 0;
        SkinnedMeshRenderer[] allSMR = Resources.FindObjectsOfTypeAll<SkinnedMeshRenderer>();
        foreach (var smr in allSMR)
        {
            if (smr.gameObject.name == "Body")
            {
                Undo.RecordObject(smr, "Apply SE_Avatar material");
                // Replace all material slots
                Material[] mats = smr.sharedMaterials;
                for (int i = 0; i < mats.Length; i++)
                    mats[i] = mat;
                smr.sharedMaterials = mats;
                EditorUtility.SetDirty(smr);
                Debug.Log($"[ApplySketch] Applied to {smr.gameObject.name} ({mats.Length} slots)");
                applied++;
            }
        }

        if (applied == 0) { Debug.LogError("[ApplySketch] No 'Body' SkinnedMeshRenderer found in scene"); return; }

        EditorSceneManager.SaveOpenScenes();
        Debug.Log($"[ApplySketch] Scene saved. Applied to {applied} SMR(s).");
    }
}
