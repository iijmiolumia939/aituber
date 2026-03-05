// SciFiLivingRoomExporter.cs
// TirgamesAssets SciFi Living Room の Props シーンからプレハブを書き出す Editor ツール。
// Unity メニュー: AITuber > Export SciFiLivingRoom Prefab
// SRS ref: FR-ROOM-01, FR-ZONE-01

using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace AITuber.Editor
{
    public static class SciFiLivingRoomExporter
    {
        private const string SourceScene = "Assets/TirgamesAssets/SciFiWorld/Scenes/SciFiLivingRoom1A.unity";
        private const string OutPrefab   = "Assets/Rooms/Prefabs/SciFiLivingRoom.prefab";
        private const string ReturnScene = "Assets/Scenes/SampleScene.unity";

        [MenuItem("AITuber/Export SciFiLivingRoom Prefab")]
        public static void Export()
        {
            EditorSceneManager.SaveCurrentModifiedScenesIfUserWantsTo();

            var scene = EditorSceneManager.OpenScene(SourceScene, OpenSceneMode.Single);

            var root = new GameObject("SciFiLivingRoom");

            foreach (var go in scene.GetRootGameObjects())
            {
                var nameLower = go.name.ToLower();
                // カメラ・ライトは除外する（RoomDefinition のカメラ設定を使う）
                if (nameLower.Contains("camera") || nameLower.Contains("directional light"))
                    continue;
                go.transform.SetParent(root.transform, true);
            }

            // Missing Script を削除
            RemoveMissingScripts(root);

            // 原点付近へオフセット（バウンド中心を Y=0 に合わせる）
            CenterAtOrigin(root);

            System.IO.Directory.CreateDirectory("Assets/Rooms/Prefabs");

            bool success;
#if UNITY_2022_2_OR_NEWER
            var prefabGO = PrefabUtility.SaveAsPrefabAsset(root, OutPrefab, out success);
#else
            var prefabGO = PrefabUtility.SaveAsPrefabAsset(root, OutPrefab);
            success      = prefabGO != null;
#endif
            Object.DestroyImmediate(root);

            if (success)
                Debug.Log($"[SciFiLivingRoomExporter] Prefab saved → {OutPrefab}");
            else
                Debug.LogError("[SciFiLivingRoomExporter] SaveAsPrefabAsset FAILED");

            EditorSceneManager.OpenScene(ReturnScene, OpenSceneMode.Single);
            AssetDatabase.Refresh();
        }

        private static void CenterAtOrigin(GameObject root)
        {
            var renderers = root.GetComponentsInChildren<Renderer>();
            if (renderers.Length == 0) return;

            var bounds = renderers[0].bounds;
            foreach (var r in renderers)
                bounds.Encapsulate(r.bounds);

            // X/Z 中心を原点合わせ、Y は床がほぼ 0 になるよう下端基準
            var offset = new Vector3(-bounds.center.x, -bounds.min.y, -bounds.center.z);
            root.transform.position += offset;
        }

        private static void RemoveMissingScripts(GameObject go)
        {
            GameObjectUtility.RemoveMonoBehavioursWithMissingScript(go);
            foreach (Transform child in go.transform)
                RemoveMissingScripts(child.gameObject);
        }
    }
}
