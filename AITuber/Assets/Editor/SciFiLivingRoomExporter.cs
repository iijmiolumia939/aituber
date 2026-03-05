// SciFiLivingRoomExporter.cs
// TirgamesAssets SciFi Living Room 1A シーンからプレハブを書き出す Editor ツール。
// 保存後に RoomDefinition ScriptableObject の roomPrefab を自動更新する。
// Unity メニュー: AITuber > Export SciFiLivingRoom Prefab
// SRS ref: FR-ROOM-01, FR-ZONE-01

using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using AITuber.Room;

namespace AITuber.Editor
{
    public static class SciFiLivingRoomExporter
    {
        private const string SourceScene  = "Assets/TirgamesAssets/SciFiWorld/Scenes/SciFiLivingRoom1A.unity";
        private const string OutPrefab    = "Assets/Rooms/Prefabs/SciFiLivingRoom.prefab";
        private const string RoomDefPath  = "Assets/Rooms/Definitions/SciFiLivingRoom.asset";
        private const string ReturnScene  = "Assets/Scenes/SampleScene.unity";

        [MenuItem("AITuber/Export SciFiLivingRoom Prefab")]
        public static void Export()
        {
            EditorSceneManager.SaveCurrentModifiedScenesIfUserWantsTo();

            var scene = EditorSceneManager.OpenScene(SourceScene, OpenSceneMode.Single);

            var root = new GameObject("SciFiLivingRoom");

            foreach (var go in scene.GetRootGameObjects())
            {
                var nameLower = go.name.ToLower();
                // カメラ・ライトは除外（RoomDefinition のカメラ設定を使う）
                if (nameLower.Contains("camera") || nameLower.Contains("directional light"))
                    continue;
                go.transform.SetParent(root.transform, true);
            }

            // Missing Script を削除
            RemoveMissingScripts(root);

            // 原点付近へオフセット
            CenterAtOrigin(root);

            System.IO.Directory.CreateDirectory("Assets/Rooms/Prefabs");

            bool success;
            GameObject prefabGO;
#if UNITY_2022_2_OR_NEWER
            prefabGO = PrefabUtility.SaveAsPrefabAsset(root, OutPrefab, out success);
#else
            prefabGO = PrefabUtility.SaveAsPrefabAsset(root, OutPrefab);
            success  = prefabGO != null;
#endif
            Object.DestroyImmediate(root);

            if (!success)
            {
                Debug.LogError("[SciFiLivingRoomExporter] SaveAsPrefabAsset FAILED");
                EditorSceneManager.OpenScene(ReturnScene, OpenSceneMode.Single);
                return;
            }

            Debug.Log($"[SciFiLivingRoomExporter] Prefab saved → {OutPrefab}");

            // ── RoomDefinition の roomPrefab を自動更新 ────────────────
            AssetDatabase.Refresh();
            var roomDef = AssetDatabase.LoadAssetAtPath<RoomDefinition>(RoomDefPath);
            if (roomDef != null && prefabGO != null)
            {
                Undo.RecordObject(roomDef, "Update SciFiLivingRoom roomPrefab");
                roomDef.roomPrefab = prefabGO;
                EditorUtility.SetDirty(roomDef);
                AssetDatabase.SaveAssets();
                Debug.Log($"[SciFiLivingRoomExporter] RoomDefinition.roomPrefab を更新しました。");
            }
            else
            {
                Debug.LogWarning($"[SciFiLivingRoomExporter] RoomDefinition が見つかりません: {RoomDefPath}");
            }

            EditorSceneManager.OpenScene(ReturnScene, OpenSceneMode.Single);
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
