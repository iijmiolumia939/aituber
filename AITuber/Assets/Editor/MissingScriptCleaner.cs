// Temporary utility — remove all Missing Script component references from the scene.
// Run via: AITuber/Tools/Remove Missing Script References
// Delete this file after confirming the warnings are gone.
using System.Collections.Generic;
using UnityEditor;
using UnityEngine;

namespace AITuber.Editor
{
    public static class MissingScriptCleaner
    {
        [MenuItem("AITuber/Tools/Remove Missing Script References")]
        public static void RemoveMissingScriptRefs()
        {
            int removed = 0;
            foreach (var go in Resources.FindObjectsOfTypeAll<GameObject>())
            {
                if (!go.scene.isLoaded) continue;  // skip prefabs / non-scene objects
                var count = GameObjectUtility.RemoveMonoBehavioursWithMissingScript(go);
                if (count > 0)
                {
                    Debug.Log($"[MissingScriptCleaner] Removed {count} missing script(s) from '{go.name}'");
                    removed += count;
                }
            }
            if (removed == 0)
                Debug.Log("[MissingScriptCleaner] No missing script references found.");
            else
                Debug.Log($"[MissingScriptCleaner] Total removed: {removed}. Save the scene to persist.");
        }
    }
}
