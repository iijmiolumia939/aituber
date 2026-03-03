// FixNegativeScaleColliders.cs
// 負のスケールを持つ GameObjectの BoxCollider を削除するユーティリティ。
// Unity メニュー: Tools > Fix Negative Scale Colliders
//
// 背景:
//   BK_AlchemistHouse の本オブジェクト群が negative scale を持っており、
//   "BoxCollider does not support negative scale or size" エラーが大量に発生。
//   強制的に正スケールに変換されたコライダーが予測不能な位置に生成され、
//   CharacterController と衝突してアバターが上空へ押し出される問題の原因。

using UnityEditor;
using UnityEngine;
using System.Collections.Generic;

namespace AITuber.Editor
{
    public static class FixNegativeScaleColliders
    {
        [MenuItem("Tools/Fix Negative Scale Colliders")]
        public static void Run()
        {
            var removed = new List<string>();

            // シーン内の全 BoxCollider を走査
            var allBoxColliders = Object.FindObjectsByType<BoxCollider>(
                FindObjectsInactive.Include,
                FindObjectsSortMode.None);

            foreach (var bc in allBoxColliders)
            {
                var ls = bc.transform.lossyScale;
                bool hasNegative = ls.x < 0f || ls.y < 0f || ls.z < 0f;
                if (!hasNegative) continue;

                var path = GetPath(bc.transform);
                removed.Add(path);

                // Undo に登録してから削除
                Undo.DestroyObjectImmediate(bc);
            }

            if (removed.Count == 0)
            {
                Debug.Log("[FixNegativeScaleColliders] 負スケールの BoxCollider は見つかりませんでした。");
                EditorUtility.DisplayDialog(
                    "Fix Negative Scale Colliders",
                    "負スケールの BoxCollider は見つかりませんでした。",
                    "OK");
                return;
            }

            Debug.Log($"[FixNegativeScaleColliders] {removed.Count} 件の BoxCollider を削除しました:\n"
                      + string.Join("\n", removed));

            EditorUtility.DisplayDialog(
                "Fix Negative Scale Colliders",
                $"{removed.Count} 件の BoxCollider を削除しました。\nConsole で詳細を確認してください。",
                "OK");
        }

        // ── Validate: Play Mode 中は無効化 ────────────────────────────
        [MenuItem("Tools/Fix Negative Scale Colliders", true)]
        private static bool Validate() => !Application.isPlaying;

        // ── Helper ─────────────────────────────────────────────────────
        private static string GetPath(Transform t)
        {
            var parts = new List<string>();
            while (t != null)
            {
                parts.Insert(0, t.name);
                t = t.parent;
            }
            return string.Join("/", parts);
        }
    }
}
