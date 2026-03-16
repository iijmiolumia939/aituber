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
using UnityEngine.SceneManagement;

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
        //   X=0 (幅方向中央), Y=0.34 (座面高さ), Z=0.3 (奥行き方向・前縁から中央付近)
        //   ※ Unity Editor の Scene view でドラッグして微調整してください
        var seat = CreateSeatAnchor(
            furniture: sofa,
            seatName: "SofaSeat",
            slotId: "sofa",
            localPosition: new Vector3(0f, 0.34f, 0.3f),
            colliderSize: new Vector3(0.9f, 0.10f, 0.55f),
            faceYaw: oldSlot != null ? oldSlot.faceYaw : -1f);

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
                  "Adjust local position / collider size in Inspector to center the avatar on the sofa cushion.");
    }

    [MenuItem("Tools/Setup WorkSeat InteractionSlot")]
    public static void SetupWorkSeat()
    {
        Vector3 defaultLocalSeatPosition = new Vector3(0f, 0.42f, -0.10f);
        var scene = EditorSceneManager.OpenScene("Assets/Scenes/SampleScene.unity", OpenSceneMode.Single);
        AITuber.Editor.SceneRoomPlacer.SetupRooms();

        var chair = FindGameObjectIncludingInactive("DeskChair02 (1)")
            ?? FindGameObjectIncludingInactive("DeskChair02");
        if (chair == null)
        {
            Debug.LogError("[WorkSeat] Desk chair not found in SampleScene. Make sure Room_living_room is placed.");
            return;
        }

        InteractionSlot oldSlot = null;
        foreach (var s in Object.FindObjectsByType<InteractionSlot>(FindObjectsSortMode.None))
            if (s.slotId == "sit_work") { oldSlot = s; break; }

        var existingChild = chair.transform.Find("WorkSeat");
        if (existingChild != null)
        {
            Object.DestroyImmediate(existingChild.gameObject);
            Debug.Log("[WorkSeat] Removed existing WorkSeat child.");
        }

        Vector3 localSeatPosition = defaultLocalSeatPosition;
        if (oldSlot != null)
        {
            localSeatPosition = chair.transform.InverseTransformPoint(oldSlot.transform.position);
            localSeatPosition.z = defaultLocalSeatPosition.z;
        }

        if (TryResolveSeatSupportLocalY(chair, localSeatPosition, out float sampledSeatLocalY))
            localSeatPosition.y = sampledSeatLocalY;
        else
            localSeatPosition.y = 0.42f;

        var seat = CreateSeatAnchor(
            furniture: chair,
            seatName: "WorkSeat",
            slotId: "sit_work",
            localPosition: localSeatPosition,
            colliderSize: new Vector3(0.46f, 0.10f, 0.46f),
            faceYaw: oldSlot != null ? oldSlot.faceYaw : -1f);

        if (oldSlot != null)
        {
            var oldGo = oldSlot.gameObject;
            Object.DestroyImmediate(oldSlot);
            if (oldGo != chair && oldGo.GetComponents<Component>().Length <= 1)
                Object.DestroyImmediate(oldGo);
            Debug.Log("[WorkSeat] Removed old sit_work InteractionSlot.");
        }

        EditorUtility.SetDirty(seat);
        EditorSceneManager.MarkSceneDirty(scene);
        EditorSceneManager.SaveScene(scene);

        Debug.Log($"[WorkSeat] ✓ WorkSeat created at {seat.transform.position:F3} (world). " +
                  $"Adjusted local Z to {localSeatPosition.z:F3} so AvatarRoot sits deeper on the chair cushion. " +
                  "Adjust local position / collider size in Inspector if the chair mesh differs.");
    }

    private static GameObject CreateSeatAnchor(
        GameObject furniture,
        string seatName,
        string slotId,
        Vector3 localPosition,
        Vector3 colliderSize,
        float faceYaw)
    {
        var seat = new GameObject(seatName);
        seat.transform.SetParent(furniture.transform, false);
        seat.transform.localPosition = localPosition;
        seat.transform.localRotation = Quaternion.identity;

        var collider = seat.AddComponent<BoxCollider>();
        collider.size = colliderSize;
        collider.center = new Vector3(0f, -colliderSize.y * 0.5f, 0f);
        collider.isTrigger = false;

        var slot = seat.AddComponent<InteractionSlot>();
        slot.slotId = slotId;
        slot.faceYaw = faceYaw;
        slot.standOffset = Vector3.zero;

        return seat;
    }

    private static bool TryResolveSeatSupportLocalY(GameObject furniture, Vector3 localProbePosition, out float localSupportY)
    {
        Vector3 worldProbe = furniture.transform.TransformPoint(new Vector3(localProbePosition.x, localProbePosition.y + 0.5f, localProbePosition.z));
        Collider bestCollider = null;
        float bestSurfaceY = float.NegativeInfinity;

        foreach (var collider in Object.FindObjectsByType<Collider>(FindObjectsSortMode.None))
        {
            if (collider == null || collider.isTrigger)
                continue;

            if (!collider.gameObject.scene.IsValid())
                continue;

            if (Vector3.Distance(collider.bounds.center, worldProbe) > 1.2f)
                continue;

            var bounds = collider.bounds;
            bool withinX = worldProbe.x >= bounds.min.x - 0.05f && worldProbe.x <= bounds.max.x + 0.05f;
            bool withinZ = worldProbe.z >= bounds.min.z - 0.05f && worldProbe.z <= bounds.max.z + 0.05f;
            if (!withinX || !withinZ)
                continue;

            if (bounds.max.y > bestSurfaceY)
            {
                bestSurfaceY = bounds.max.y;
                bestCollider = collider;
            }
        }

        if (bestCollider == null)
        {
            localSupportY = 0f;
            return false;
        }

        localSupportY = furniture.transform.InverseTransformPoint(new Vector3(worldProbe.x, bestSurfaceY, worldProbe.z)).y;
        Debug.Log($"[WorkSeat] Sampled support collider '{bestCollider.name}' at worldY={bestSurfaceY:F3} -> localY={localSupportY:F3}");
        return true;
    }

    private static GameObject FindGameObjectIncludingInactive(string name)
    {
        foreach (var candidate in Resources.FindObjectsOfTypeAll<GameObject>())
        {
            if (!candidate.scene.IsValid())
                continue;
            if (candidate.name == name)
                return candidate;
        }

        return null;
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
