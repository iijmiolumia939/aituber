// BlendShapeInspector.cs — one-shot tool to log all BlendShape names+indices
// Run via menu: AITuber/Log BlendShapes
using UnityEngine;
using UnityEditor;

namespace AITuber.EditorTools
{
    public static class BlendShapeInspector
    {
        [MenuItem("AITuber/Log BlendShapes")]
        public static void LogAllBlendShapes()
        {
            var smrs = Object.FindObjectsByType<SkinnedMeshRenderer>(FindObjectsSortMode.None);
            if (smrs.Length == 0)
            {
                Debug.Log("[BlendShapeInspector] No SkinnedMeshRenderer found in scene.");
                return;
            }
            foreach (var smr in smrs)
            {
                var mesh = smr.sharedMesh;
                if (mesh == null) continue;
                int count = mesh.blendShapeCount;
                Debug.Log($"[BlendShapeInspector] === {smr.gameObject.name} ({smr.name}) — {count} BlendShapes ===");
                for (int i = 0; i < count; i++)
                {
                    Debug.Log($"[BlendShapeInspector]   [{i}] {mesh.GetBlendShapeName(i)}");
                }
            }
        }
    }
}
