// NavMeshBakeTool.cs — FR-BEHAVIOR-SEQ-01 Issue #55
// Rebakes the NavMesh for Room_living_room with the corrected agentRadius (0.2m).
// Usage: Tools > Bake NavMesh (Living Room)
//        Tools > Validate NavMesh Path (spawn→sofa)
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.AI;
using Unity.AI.Navigation;
using AITuber.Behavior;

public static class NavMeshBakeTool
{
    [MenuItem("Tools/Bake NavMesh (Living Room)")]
    public static void BakeLivingRoom()
    {
        var go = GameObject.Find("Room_living_room");
        if (go == null) { Debug.LogError("[NavMeshBake] Room_living_room not found in active scene."); return; }

        var surface = go.GetComponent<NavMeshSurface>();
        if (surface == null) { Debug.LogError("[NavMeshBake] NavMeshSurface component not found on Room_living_room."); return; }

        Debug.Log($"[NavMeshBake] Starting bake… agentTypeID={surface.agentTypeID}");
        surface.BuildNavMesh();
        Debug.Log("[NavMeshBake] Bake complete.");

        EditorUtility.SetDirty(surface);
        EditorSceneManager.MarkSceneDirty(go.scene);
    }

    [MenuItem("Tools/Dump Room Furniture Positions")]
    public static void DumpFurniturePositions()
    {
        // Find sofa InteractionSlot position
        InteractionSlot sofaSlot = null;
        foreach (var slot in Object.FindObjectsOfType<InteractionSlot>())
            if (slot.slotId == "sofa") { sofaSlot = slot; break; }

        if (sofaSlot == null) { Debug.LogWarning("[FurnitureDump] sofa slot not found. Enter Play mode first."); return; }

        var sb = new System.Text.StringBuilder();
        sb.AppendLine($"[FurnitureDump] sofa slot worldPos={sofaSlot.transform.position:F3}");

        // Scan all renderers within 4m of sofa to find the sofa furniture
        foreach (var rend in Object.FindObjectsOfType<Renderer>())
        {
            if (rend == null) continue;
            float dist = Vector3.Distance(rend.bounds.center, sofaSlot.transform.position);
            if (dist < 4f)
            {
                sb.AppendLine($"[FurnitureDump] r='{rend.gameObject.name}' parent='{rend.transform.parent?.name}' bnd.c={rend.bounds.center:F3} bnd.min={rend.bounds.min:F3} bnd.max={rend.bounds.max:F3} dist={dist:F2}");
            }
        }
        Debug.Log(sb.ToString());
    }

    [MenuItem("Tools/Dump Avatar Animators")]
    public static void DumpAvatarAnimators()
    {
        var sb = new System.Text.StringBuilder();
        foreach (var a in Object.FindObjectsOfType<Animator>())
        {
            string ctrl = a.runtimeAnimatorController?.name ?? "(none)";
            string parent = a.transform.parent?.name ?? "(root)";
            sb.AppendLine($"[AnimDump] go='{a.gameObject.name}' parent='{parent}' ctrl='{ctrl}' human={a.isHuman} applyRM={a.applyRootMotion} enabled={a.enabled}");
        }
        Debug.Log("[AnimDump all]\n" + sb.ToString());
    }

    [MenuItem("Tools/Dump InteractionSlot Positions")]
    public static void DumpSlotPositions()
    {
        var slots = Object.FindObjectsByType<InteractionSlot>(FindObjectsSortMode.None);
        if (slots.Length == 0) { Debug.LogWarning("[SlotDump] No InteractionSlots found. Enter Play mode first."); return; }
        foreach (var s in slots)
        {
            Debug.Log($"[SlotDump] id='{s.slotId}' worldPos={s.transform.position:F3} standPos={s.StandPosition:F3} standOffset={s.standOffset} faceYaw={s.faceYaw:F1} parent='{s.transform.parent?.name}'");
        }
    }

    // ── SofaSeat セットアップ ─────────────────────────────────────────────────
    // Issue #1 Fix: ソファ座面中央に子 GameObject "SofaSeat" を作成し、
    // Sofa03_1 直下の InteractionSlot(sofa) をそちらに移動する。
    [MenuItem("Tools/Setup SofaSeat InteractionSlot")]
    public static void SetupSofaSeat()
    {
        // ── 1. Sofa03_1 を探す
        var sofa = GameObject.Find("Sofa03_1");
        if (sofa == null) { Debug.LogError("[SofaSeat] Sofa03_1 not found. Make sure the scene is open."); return; }

        // ── 2. 既存の sofa InteractionSlot(slotId="sofa") をすべて取得
        InteractionSlot oldSlot = null;
        foreach (var s in Object.FindObjectsByType<InteractionSlot>(FindObjectsSortMode.None))
            if (s.slotId == "sofa") { oldSlot = s; break; }

        // ── 3. 既存の SofaSeat があれば削除
        var existingChild = sofa.transform.Find("SofaSeat");
        if (existingChild != null)
        {
            Object.DestroyImmediate(existingChild.gameObject);
            Debug.Log("[SofaSeat] Removed existing SofaSeat child.");
        }

        // ── 4. SofaSeat 子 GameObject を作成
        //   ソファ座面中央のローカル座標 (Sofa03_1 ローカル空間):
        //   X=0 (幅方向中央), Y=0 (床レベル), Z=0.3 (奥行き方向・前縁から中央付近)
        //   ※ Unity Editor の Scene view でドラッグして微調整してください
        var seat = new GameObject("SofaSeat");
        seat.transform.SetParent(sofa.transform, false);
        seat.transform.localPosition = new Vector3(0f, 0f, 0.3f);
        seat.transform.localRotation = Quaternion.identity;

        // ── 5. InteractionSlot コンポーネントを追加・設定
        var slot = seat.AddComponent<InteractionSlot>();
        slot.slotId = "sofa";
        slot.faceYaw = oldSlot != null ? oldSlot.faceYaw : -1f;

        // ── 6. 旧 InteractionSlot を削除
        if (oldSlot != null)
        {
            var oldGo = oldSlot.gameObject;
            Object.DestroyImmediate(oldSlot);
            // 旧スロットが独立した空 GameObject だった場合は削除
            if (oldGo != sofa && oldGo.GetComponents<Component>().Length <= 1)
                Object.DestroyImmediate(oldGo);
            Debug.Log("[SofaSeat] Removed old sofa InteractionSlot.");
        }

        // ── 7. シーンをダーティにしてセーブ対象にする
        EditorUtility.SetDirty(seat);
        EditorSceneManager.MarkSceneDirty(sofa.scene);

        Debug.Log($"[SofaSeat] ✓ SofaSeat created at {seat.transform.position:F3} (world). " +
                  "Adjust local Z in Inspector to center the avatar on the sofa cushion.");
    }

    [MenuItem("Tools/Validate NavMesh Path (spawn→sofa)")]
    public static void ValidateSofaPath()
    {
        // Spawn position from RoomManager logs: (1.50, 0.07, 0.00)
        var spawnPos = new Vector3(1.5f, 0.07f, 0f);

        // Find sofa InteractionSlot in the scene
        InteractionSlot sofaSlot = null;
        foreach (var slot in Object.FindObjectsByType<InteractionSlot>(FindObjectsSortMode.None))
        {
            if (slot.slotId == "sofa") { sofaSlot = slot; break; }
        }

        if (sofaSlot == null)
        {
            Debug.LogError("[NavMeshValidate] No InteractionSlot with slotId='sofa' found. Enter Play mode or ensure room is in scene.");
            return;
        }

        var dest = sofaSlot.transform.position;
        Debug.Log($"[NavMeshValidate] Testing path: spawn={spawnPos} → sofa={dest}");

        // Snap both points onto the NavMesh (agentTypeID=0)
        if (!NavMesh.SamplePosition(spawnPos, out var srcHit, 2f, NavMesh.AllAreas))
        {
            Debug.LogError($"[NavMeshValidate] spawn position {spawnPos} not on NavMesh (radius 2m).");
            return;
        }
        if (!NavMesh.SamplePosition(dest, out var dstHit, 2f, NavMesh.AllAreas))
        {
            Debug.LogError($"[NavMeshValidate] sofa position {dest} not on NavMesh (radius 2m).");
            return;
        }

        var path = new NavMeshPath();
        bool found = NavMesh.CalculatePath(srcHit.position, dstHit.position, NavMesh.AllAreas, path);
        Debug.Log($"[NavMeshValidate] CalculatePath found={found} status={path.status} corners={path.corners.Length}");

        if (path.status == NavMeshPathStatus.PathComplete)
            Debug.Log("[NavMeshValidate] ✓ PATH COMPLETE — sofa is reachable from spawn.");
        else if (path.status == NavMeshPathStatus.PathPartial)
            Debug.LogWarning("[NavMeshValidate] △ PATH PARTIAL — sofa is only partially reachable (gap still blocked?).");
        else
            Debug.LogError("[NavMeshValidate] ✗ PATH INVALID — sofa is NOT reachable. Rebake needed.");
    }
}
