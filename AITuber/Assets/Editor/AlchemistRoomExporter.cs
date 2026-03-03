// AlchemistRoomExporter.cs
// BK_AlchemistHouse の Scene.unity からルームをプレハブとして書き出す一時ツール。
// Unity メニュー: AITuber > Export AlchemistHouse Room Prefab

using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace AITuber.Editor
{
    public static class AlchemistRoomExporter
    {
        private const string SourceScene  = "Assets/BK_AlchemistHouse/Scenes/Scene.unity";
        private const string OutPrefab    = "Assets/Rooms/Prefabs/BK_AlchemistRoom.prefab";
        private const string ReturnScene  = "Assets/Scenes/SampleScene.unity";

        [MenuItem("AITuber/Export AlchemistHouse Room Prefab")]
        public static void Export()
        {
            EditorSceneManager.SaveCurrentModifiedScenesIfUserWantsTo();

            var scene = EditorSceneManager.OpenScene(SourceScene, OpenSceneMode.Single);

            var root = new GameObject("BK_AlchemistRoom");

            foreach (var go in scene.GetRootGameObjects())
            {
                var name = go.name.ToLower();
                if (name.Contains("camera") || name.Contains("directional"))
                    continue;
                go.transform.SetParent(root.transform, true);
            }

            // Missing Script をすべて削除
            RemoveMissingScripts(root);

            // 全 Renderer のバウンドを計算してルートを原点オフセット
            CenterAtOrigin(root);

            System.IO.Directory.CreateDirectory("Assets/Rooms/Prefabs");

            bool success;
            PrefabUtility.SaveAsPrefabAssetAndConnect(root, OutPrefab, InteractionMode.AutomatedAction, out success);

            if (success)
                Debug.Log($"[AlchemistRoomExporter] Prefab saved to {OutPrefab}");
            else
                Debug.LogError("[AlchemistRoomExporter] Failed to save prefab.");

            EditorSceneManager.OpenScene(ReturnScene, OpenSceneMode.Single);
            AssetDatabase.Refresh();
        }

        private static void CenterAtOrigin(GameObject root)
        {
            // 全 Renderer を収集してワールドバウンド算出
            var renderers = root.GetComponentsInChildren<Renderer>(true);
            if (renderers.Length == 0) return;

            var bounds = renderers[0].bounds;
            foreach (var r in renderers)
                bounds.Encapsulate(r.bounds);

            // X/Z は中心に、Y は床が y=0 になるようオフセット
            var offset = new Vector3(-bounds.center.x, -bounds.min.y, -bounds.center.z);
            foreach (Transform child in root.transform)
                child.position += offset;

            Debug.Log($"[AlchemistRoomExporter] Centered. bounds={bounds}, offset={offset}");
        }

        private static void RemoveMissingScripts(GameObject go)
        {
            // 再帰的に Missing Script を除去
            GameObjectUtility.RemoveMonoBehavioursWithMissingScript(go);
            foreach (Transform child in go.transform)
                RemoveMissingScripts(child.gameObject);
        }
    }
}
