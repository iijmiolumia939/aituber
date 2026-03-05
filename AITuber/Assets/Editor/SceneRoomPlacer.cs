// SceneRoomPlacer.cs
// SampleScene に全部屋プレハブを事前配置（disabled）する Editor ツール。
// Edit Mode で部屋が見えるようになり、アバター/カメラ位置を Inspector で直接調整可能。
// Unity メニュー: AITuber > Setup Rooms In Scene
// SRS ref: FR-ROOM-01

using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace AITuber.Editor
{
    public static class SceneRoomPlacer
    {
        private static readonly (string prefabPath, string goName)[] RoomEntries =
        {
            ("Assets/Rooms/Prefabs/SciFiLivingRoom.prefab", "Room_living_room"),
            ("Assets/Rooms/Prefabs/AlchemistRoom.prefab",    "Room_alchemist"),
        };

        [MenuItem("AITuber/Setup Rooms In Scene")]
        public static void SetupRooms()
        {
            var scene = UnityEngine.SceneManagement.SceneManager.GetActiveScene();

            foreach (var (prefabPath, goName) in RoomEntries)
            {
                // 既存の GO があれば置き換えない（冪等）
                var existing = GameObject.Find(goName);
                if (existing != null)
                {
                    Debug.Log($"[SceneRoomPlacer] '{goName}' already exists — skipped");
                    continue;
                }

                var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(prefabPath);
                if (prefab == null)
                {
                    Debug.LogWarning($"[SceneRoomPlacer] Prefab not found: {prefabPath}");
                    continue;
                }

                var instance = (GameObject)PrefabUtility.InstantiatePrefab(prefab, scene);
                instance.name = goName;
                instance.SetActive(false);
                Debug.Log($"[SceneRoomPlacer] Placed '{goName}' (inactive) in scene.");
            }

            EditorSceneManager.MarkSceneDirty(scene);
            EditorSceneManager.SaveScene(scene);
            Debug.Log("[SceneRoomPlacer] Scene saved.");
        }
    }
}
