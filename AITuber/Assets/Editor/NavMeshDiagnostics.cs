#if UNITY_EDITOR
// NavMeshDiagnostics.cs — Issue #75 (AI Navigation 設定最適化)
// NavMesh の品質を検証する診断ツール。
//   1. Agent 設定 vs VRM アバターサイズの整合性チェック
//   2. InteractionSlot 到達性テスト (全ペアパス検証)
//   3. NavMesh カバレッジ概要
//   4. NavMeshSurface 推奨設定チェック
// SRS refs: FR-ROOM-01, FR-BEHAVIOR-SEQ-01

using System.Text;
using Unity.AI.Navigation;
using UnityEditor;
using UnityEngine;
using UnityEngine.AI;
using AITuber.Behavior;

namespace AITuber.Editor
{
    public static class NavMeshDiagnostics
    {
        // ── 1. Agent 設定検証 ──────────────────────────────────────

        [MenuItem("AITuber/NavMesh/Diagnostics/1. Validate Agent Settings")]
        public static void ValidateAgentSettings()
        {
            var sb = new StringBuilder();
            sb.AppendLine("[NavMeshDiag] ═══ Agent Settings Validation ═══");

            // NavMeshAgent を持つ全オブジェクト (非アクティブ含む)
            var agents = Object.FindObjectsByType<NavMeshAgent>(FindObjectsInactive.Include, FindObjectsSortMode.None);
            if (agents.Length == 0)
            {
                sb.AppendLine("  ⚠ NavMeshAgent が見つかりません");
                Debug.LogWarning(sb.ToString());
                return;
            }

            foreach (var agent in agents)
            {
                sb.AppendLine($"\n  Agent: {agent.gameObject.name}");
                sb.AppendLine($"    radius       = {agent.radius:F3}m");
                sb.AppendLine($"    height       = {agent.height:F3}m");
                sb.AppendLine($"    stepHeight   = {agent.agentTypeID}");
                sb.AppendLine($"    speed        = {agent.speed:F2}m/s");
                sb.AppendLine($"    angularSpeed = {agent.angularSpeed:F1}°/s");
                sb.AppendLine($"    acceleration = {agent.acceleration:F1}m/s²");
                sb.AppendLine($"    stoppingDist = {agent.stoppingDistance:F3}m");
                sb.AppendLine($"    autoBraking  = {agent.autoBraking}");
                sb.AppendLine($"    obstacleAvoidanceType = {agent.obstacleAvoidanceType}");
                sb.AppendLine($"    avoidancePriority     = {agent.avoidancePriority}");

                // 推奨値チェック
                if (agent.radius < 0.1f)
                    sb.AppendLine("    ⚠ radius < 0.1m — 壁にめり込む可能性");
                if (agent.radius > 0.5f)
                    sb.AppendLine("    ⚠ radius > 0.5m — 狭い通路を通過できない可能性");
                if (agent.stoppingDistance > 0.5f)
                    sb.AppendLine("    ⚠ stoppingDistance > 0.5m — InteractionSlot から離れすぎる");
                if (!agent.autoBraking)
                    sb.AppendLine("    ⚠ autoBraking=false — 到着時にオーバーシュートする可能性");
                if (agent.obstacleAvoidanceType == ObstacleAvoidanceType.NoObstacleAvoidance)
                    sb.AppendLine("    ⚠ 障害物回避が無効 — 動的障害物とすり抜ける");
            }

            Debug.Log(sb.ToString());
        }

        // ── 2. InteractionSlot 到達性テスト ────────────────────────

        [MenuItem("AITuber/NavMesh/Diagnostics/2. Test Slot Reachability")]
        public static void TestSlotReachability()
        {
            var sb = new StringBuilder();
            sb.AppendLine("[NavMeshDiag] ═══ InteractionSlot Reachability ═══");

            var slots = Object.FindObjectsByType<InteractionSlot>(FindObjectsInactive.Include, FindObjectsSortMode.None);
            if (slots.Length == 0)
            {
                sb.AppendLine("  ⚠ InteractionSlot が見つかりません");
                Debug.LogWarning(sb.ToString());
                return;
            }

            int pass = 0, fail = 0;

            // 各スロットが NavMesh 上にあるか
            sb.AppendLine("\n  ── Slot → NavMesh サンプリング ──");
            foreach (var slot in slots)
            {
                Vector3 pos = slot.StandPosition;
                bool onMesh = NavMesh.SamplePosition(pos, out NavMeshHit hit, 1.0f, NavMesh.AllAreas);
                float dist = onMesh ? Vector3.Distance(pos, hit.position) : -1f;

                if (onMesh && dist < 0.3f)
                {
                    sb.AppendLine($"  ✓ [{slot.slotId}] pos={pos:F3} → NavMesh dist={dist:F3}m");
                    pass++;
                }
                else
                {
                    sb.AppendLine($"  ✗ [{slot.slotId}] pos={pos:F3} → {(onMesh ? $"NavMesh dist={dist:F3}m (遠い)" : "NavMesh 範囲外")}");
                    fail++;
                }
            }

            // スロット間のパス到達性
            sb.AppendLine("\n  ── Slot 間パス到達性 ──");
            var path = new NavMeshPath();
            for (int i = 0; i < slots.Length; i++)
            {
                for (int j = i + 1; j < slots.Length; j++)
                {
                    Vector3 from = slots[i].StandPosition;
                    Vector3 to   = slots[j].StandPosition;

                    // NavMesh 上の最寄り点を取得
                    if (!NavMesh.SamplePosition(from, out NavMeshHit hitFrom, 2f, NavMesh.AllAreas)) continue;
                    if (!NavMesh.SamplePosition(to,   out NavMeshHit hitTo,   2f, NavMesh.AllAreas)) continue;

                    bool ok = NavMesh.CalculatePath(hitFrom.position, hitTo.position, NavMesh.AllAreas, path);
                    string status = ok && path.status == NavMeshPathStatus.PathComplete ? "✓" : "✗";
                    sb.AppendLine($"  {status} [{slots[i].slotId}] → [{slots[j].slotId}] status={path.status}");

                    if (!ok || path.status != NavMeshPathStatus.PathComplete) fail++;
                    else pass++;
                }
            }

            sb.AppendLine($"\n  Summary: {pass} pass / {fail} fail");
            if (fail > 0)
                Debug.LogWarning(sb.ToString());
            else
                Debug.Log(sb.ToString());
        }

        // ── 3. NavMeshSurface 設定チェック ─────────────────────────

        [MenuItem("AITuber/NavMesh/Diagnostics/3. Check Surface Settings")]
        public static void CheckSurfaceSettings()
        {
            var sb = new StringBuilder();
            sb.AppendLine("[NavMeshDiag] ═══ NavMeshSurface Settings ═══");

            var surfaces = Object.FindObjectsByType<NavMeshSurface>(FindObjectsInactive.Include, FindObjectsSortMode.None);
            if (surfaces.Length == 0)
            {
                sb.AppendLine("  ⚠ NavMeshSurface が見つかりません。");
                sb.AppendLine("  → Room の親 GameObject に NavMeshSurface コンポーネントを追加してください。");
                Debug.LogWarning(sb.ToString());
                return;
            }

            foreach (var surface in surfaces)
            {
                sb.AppendLine($"\n  Surface: {surface.gameObject.name}");
                sb.AppendLine($"    collectObjects = {surface.collectObjects}");
                sb.AppendLine($"    useGeometry    = {surface.useGeometry}");
                sb.AppendLine($"    defaultArea    = {NavMesh.GetAreaNames()[surface.defaultArea]}");
                sb.AppendLine($"    layerMask      = {surface.layerMask.value}");

                // 推奨設定チェック
                if (surface.collectObjects == CollectObjects.All)
                    sb.AppendLine("    💡 collectObjects=All — Children に限定するとベイク範囲を制御しやすい");
                if (surface.useGeometry == NavMeshCollectGeometry.PhysicsColliders)
                    sb.AppendLine("    💡 useGeometry=PhysicsColliders — Collider のない装飾メッシュが NavMesh に含まれない");
            }

            // NavMeshModifier 統計
            var modifiers = Object.FindObjectsByType<NavMeshModifier>(FindObjectsInactive.Include, FindObjectsSortMode.None);
            int ignored = 0, areaOverride = 0;
            foreach (var mod in modifiers)
            {
                if (mod.ignoreFromBuild) ignored++;
                if (mod.overrideArea) areaOverride++;
            }
            sb.AppendLine($"\n  NavMeshModifier: {modifiers.Length} total");
            sb.AppendLine($"    ignoreFromBuild = {ignored}");
            sb.AppendLine($"    overrideArea    = {areaOverride}");

            // NavMeshModifierVolume 統計
            var volumes = Object.FindObjectsByType<NavMeshModifierVolume>(FindObjectsInactive.Include, FindObjectsSortMode.None);
            sb.AppendLine($"\n  NavMeshModifierVolume: {volumes.Length} total");
            if (volumes.Length == 0)
                sb.AppendLine("    💡 NavMeshModifierVolume を使うとボックス範囲で精密にエリアを制御できます");

            // NavMeshLink 統計
            var links = Object.FindObjectsByType<NavMeshLink>(FindObjectsInactive.Include, FindObjectsSortMode.None);
            sb.AppendLine($"\n  NavMeshLink: {links.Length} total");
            if (links.Length == 0)
                sb.AppendLine("    💡 NavMeshLink で段差・ドア・部屋間の接続を明示できます");

            Debug.Log(sb.ToString());
        }

        // ── 4. 全診断一括実行 ───────────────────────────────────────

        [MenuItem("AITuber/NavMesh/Diagnostics/Run All Diagnostics")]
        public static void RunAll()
        {
            Debug.Log("[NavMeshDiag] ═══════════════════════════════════════════");
            Debug.Log("[NavMeshDiag] Running all NavMesh diagnostics…");
            Debug.Log("[NavMeshDiag] ═══════════════════════════════════════════");
            ValidateAgentSettings();
            TestSlotReachability();
            CheckSurfaceSettings();
            Debug.Log("[NavMeshDiag] ═══ All diagnostics complete ═══");
        }
    }
}
#endif
