#if UNITY_EDITOR
// NavMeshLinkSetup.cs — Issue #75 (AI Navigation 設定最適化)
// NavMesh 島間の隙間を検出し、最短距離の NavMeshLink を自動配置するエディタツール。
// SRS refs: FR-ROOM-01, FR-BEHAVIOR-SEQ-01

using System.Collections.Generic;
using System.Text;
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
        private const float ProbeStep = 0.15f;   // NavMesh 境界探索のステップ幅
        private const float MaxLinkDist = 3.0f;   // これ以上離れた隙間にはリンクを作らない

        // ── 1. NavMesh 島間ギャップに最短 Link を自動配置 ─────────────

        [MenuItem("AITuber/NavMesh/Links/Auto-Create Links Between Slots")]
        public static void AutoCreateLinks()
        {
            var slots = Object.FindObjectsByType<InteractionSlot>(
                FindObjectsInactive.Include, FindObjectsSortMode.None);
            if (slots.Length < 2)
            {
                Debug.LogWarning("[NavMeshLink] InteractionSlot が 2 つ未満です。");
                return;
            }

            // Step 1: Identify disconnected slot pairs
            var disconnectedPairs = new List<(InteractionSlot a, InteractionSlot b)>();
            var path = new NavMeshPath();

            for (int i = 0; i < slots.Length; i++)
            {
                for (int j = i + 1; j < slots.Length; j++)
                {
                    Vector3 from = slots[i].StandPosition;
                    Vector3 to   = slots[j].StandPosition;

                    if (!NavMesh.SamplePosition(from, out NavMeshHit hitFrom, 2f, NavMesh.AllAreas)) continue;
                    if (!NavMesh.SamplePosition(to,   out NavMeshHit hitTo,   2f, NavMesh.AllAreas)) continue;

                    bool ok = NavMesh.CalculatePath(hitFrom.position, hitTo.position, NavMesh.AllAreas, path);
                    if (!ok || path.status != NavMeshPathStatus.PathComplete)
                        disconnectedPairs.Add((slots[i], slots[j]));
                }
            }

            if (disconnectedPairs.Count == 0)
            {
                Debug.Log("[NavMeshLink] 全スロット間のパスが到達可能です。追加 Link は不要です。");
                return;
            }

            // Step 2: For each disconnected pair, probe from each side to find gap edges.
            // Use the pair with the shortest gap per island-group as the bridge point.
            var createdBridges = new HashSet<string>();
            int created = 0;
            var sb = new StringBuilder();
            sb.AppendLine("[NavMeshLink] ═══ Auto-Link Gap Detection ═══");

            foreach (var (slotA, slotB) in disconnectedPairs)
            {
                // Check if this pair is already bridged by a previous link
                NavMesh.SamplePosition(slotA.StandPosition, out NavMeshHit checkA, 2f, NavMesh.AllAreas);
                NavMesh.SamplePosition(slotB.StandPosition, out NavMeshHit checkB, 2f, NavMesh.AllAreas);
                bool alreadyBridged = NavMesh.CalculatePath(checkA.position, checkB.position, NavMesh.AllAreas, path)
                    && path.status == NavMeshPathStatus.PathComplete;
                if (alreadyBridged) continue;

                // Probe from A toward B and from B toward A to find NavMesh edges
                Vector3 posA = checkA.position;
                Vector3 posB = checkB.position;

                Vector3 edgeA = ProbeNavMeshEdge(posA, posB);
                Vector3 edgeB = ProbeNavMeshEdge(posB, posA);

                float gapDist = Vector3.Distance(edgeA, edgeB);
                string bridgeKey = $"{Mathf.Min(edgeA.GetHashCode(), edgeB.GetHashCode())}_{Mathf.Max(edgeA.GetHashCode(), edgeB.GetHashCode())}";

                // Skip if gap is too large (probably a wall, not a floor gap)
                if (gapDist > MaxLinkDist)
                {
                    sb.AppendLine($"  ─ [{slotA.slotId}]↔[{slotB.slotId}] gap={gapDist:F2}m > {MaxLinkDist}m → スキップ");
                    continue;
                }

                // Skip duplicate bridges (same edge pair)
                if (!createdBridges.Add(bridgeKey)) continue;

                CreateLink($"{slotA.slotId}_gap", $"{slotB.slotId}_gap", edgeA, edgeB);
                sb.AppendLine($"  ✓ [{slotA.slotId}]↔[{slotB.slotId}] edgeA={edgeA:F3} edgeB={edgeB:F3} gap={gapDist:F2}m");
                created++;
            }

            sb.AppendLine($"\n  {created} 本の NavMeshLink を作成しました。");
            Debug.Log(sb.ToString());

            if (created > 0)
            {
                UnityEditor.SceneManagement.EditorSceneManager.MarkSceneDirty(
                    UnityEngine.SceneManagement.SceneManager.GetActiveScene());
            }
        }

        /// <summary>
        /// NavMesh の境界エッジを探索する。from から toward 方向にステップしながら
        /// NavMesh 上にいる最後の位置を返す。
        /// </summary>
        private static Vector3 ProbeNavMeshEdge(Vector3 from, Vector3 toward)
        {
            Vector3 dir = (toward - from).normalized;
            float totalDist = Vector3.Distance(from, toward);
            Vector3 lastOnMesh = from;

            for (float d = ProbeStep; d < totalDist; d += ProbeStep)
            {
                Vector3 probe = from + dir * d;
                if (NavMesh.SamplePosition(probe, out NavMeshHit hit, 0.3f, NavMesh.AllAreas))
                {
                    // Still on NavMesh — check it's still the same island
                    var testPath = new NavMeshPath();
                    bool connected = NavMesh.CalculatePath(from, hit.position, NavMesh.AllAreas, testPath)
                        && testPath.status == NavMeshPathStatus.PathComplete;
                    if (connected)
                        lastOnMesh = hit.position;
                    else
                        break;  // Reached a different island
                }
                else
                {
                    break;  // Off NavMesh — this is the edge
                }
            }

            // Refine using FindClosestEdge for precision
            if (NavMesh.FindClosestEdge(lastOnMesh, out NavMeshHit edgeHit, NavMesh.AllAreas))
            {
                // Only use edge if it's closer to the target direction
                Vector3 toEdge = edgeHit.position - from;
                if (Vector3.Dot(toEdge.normalized, dir) > 0.3f)
                    return edgeHit.position;
            }

            return lastOnMesh;
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
            var links = Object.FindObjectsByType<NavMeshLink>(
                FindObjectsInactive.Include, FindObjectsSortMode.None);
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
            link.startTransform = null;
            link.endTransform   = null;

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
