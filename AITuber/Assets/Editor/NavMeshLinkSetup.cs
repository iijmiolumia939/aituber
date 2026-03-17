#if UNITY_EDITOR
// NavMeshLinkSetup.cs — Issue #75 (AI Navigation 設定最適化)
// InteractionSlot 間に NavMeshLink を自動配置するエディタツール。
// RoomDefinition の Zone 間を明示的に NavMesh Link で接続し、
// パスファインディングの品質と信頼性を向上させる。
// SRS refs: FR-ROOM-01, FR-BEHAVIOR-SEQ-01

using System.Collections.Generic;
using Unity.AI.Navigation;
using UnityEditor;
using UnityEngine;
using UnityEngine.AI;
using AITuber.Behavior;

namespace AITuber.Editor
{
    public static class NavMeshLinkSetup
    {
        private const string LinkTag = "AutoNavMeshLink";

        // ── 1. NavMesh 切断エリアに Link を自動配置 ─────────────────

        [MenuItem("AITuber/NavMesh/Links/Auto-Create Links Between Slots")]
        public static void AutoCreateLinks()
        {
            var slots = Object.FindObjectsByType<InteractionSlot>(FindObjectsSortMode.None);
            if (slots.Length < 2)
            {
                Debug.LogWarning("[NavMeshLink] InteractionSlot が 2 つ未満です。Play Mode で実行してください。");
                return;
            }

            int created = 0;
            var path = new NavMeshPath();

            for (int i = 0; i < slots.Length; i++)
            {
                for (int j = i + 1; j < slots.Length; j++)
                {
                    Vector3 from = slots[i].StandPosition;
                    Vector3 to   = slots[j].StandPosition;

                    // NavMesh 上の最寄り点
                    if (!NavMesh.SamplePosition(from, out NavMeshHit hitFrom, 2f, NavMesh.AllAreas)) continue;
                    if (!NavMesh.SamplePosition(to,   out NavMeshHit hitTo,   2f, NavMesh.AllAreas)) continue;

                    // パスが完全なら Link 不要
                    bool ok = NavMesh.CalculatePath(hitFrom.position, hitTo.position, NavMesh.AllAreas, path);
                    if (ok && path.status == NavMeshPathStatus.PathComplete) continue;

                    // パスが不完全 → Link で接続
                    CreateLink(slots[i].slotId, slots[j].slotId, hitFrom.position, hitTo.position);
                    created++;
                }
            }

            if (created > 0)
            {
                Debug.Log($"[NavMeshLink] {created} 本の NavMeshLink を作成しました。NavMesh を Rebake してください。");
                UnityEditor.SceneManagement.EditorSceneManager.MarkSceneDirty(
                    UnityEngine.SceneManagement.SceneManager.GetActiveScene());
            }
            else
            {
                Debug.Log("[NavMeshLink] 全スロット間のパスが到達可能です。追加 Link は不要です。");
            }
        }

        // ── 2. 手動 Link 作成（2つの Transform を選択） ──────────────

        [MenuItem("AITuber/NavMesh/Links/Create Link From Selection (2 objects)")]
        public static void CreateLinkFromSelection()
        {
            var selected = Selection.transforms;
            if (selected.Length != 2)
            {
                Debug.LogWarning("[NavMeshLink] 2 つの GameObject を選択してください。");
                return;
            }

            Vector3 posA = selected[0].position;
            Vector3 posB = selected[1].position;
            string nameA = selected[0].name;
            string nameB = selected[1].name;

            CreateLink(nameA, nameB, posA, posB);

            Debug.Log($"[NavMeshLink] '{nameA}' ↔ '{nameB}' に Link を作成しました。");
            UnityEditor.SceneManagement.EditorSceneManager.MarkSceneDirty(
                UnityEngine.SceneManagement.SceneManager.GetActiveScene());
        }

        // ── 3. 自動生成 Link の全削除 ────────────────────────────────

        [MenuItem("AITuber/NavMesh/Links/Remove All Auto-Links")]
        public static void RemoveAutoLinks()
        {
            var links = Object.FindObjectsByType<NavMeshLink>(FindObjectsSortMode.None);
            int removed = 0;
            foreach (var link in links)
            {
                if (link.gameObject.name.StartsWith(LinkTag))
                {
                    Undo.DestroyObjectImmediate(link.gameObject);
                    removed++;
                }
            }
            Debug.Log($"[NavMeshLink] {removed} 本の自動生成 Link を削除しました。");
            if (removed > 0)
                UnityEditor.SceneManagement.EditorSceneManager.MarkSceneDirty(
                    UnityEngine.SceneManagement.SceneManager.GetActiveScene());
        }

        // ── Internal ────────────────────────────────────────────────

        private static void CreateLink(string nameA, string nameB, Vector3 posA, Vector3 posB)
        {
            var go = new GameObject($"{LinkTag}_{nameA}_to_{nameB}");
            Undo.RegisterCreatedObjectUndo(go, "Create NavMeshLink");
            go.transform.position = (posA + posB) * 0.5f;

            var link = Undo.AddComponent<NavMeshLink>(go);
            link.startTransform = null; // use startPoint offset
            link.endTransform   = null;

            // NavMeshLink のローカル座標系での開始/終了点
            Vector3 center = go.transform.position;
            link.startPoint = posA - center;
            link.endPoint   = posB - center;
            link.width      = 0.5f;
            link.bidirectional = true;

            EditorUtility.SetDirty(go);
        }
    }
}
#endif
