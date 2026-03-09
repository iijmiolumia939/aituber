#if UNITY_EDITOR
// NavMeshFurnitureSetup.cs
// One-shot editor utility:
//   1. "Log Mesh Positions" — lists every MeshRenderer with its world-space Y bounds
//      so you can verify which objects are furniture vs floor.
//   2. "Mark Furniture Not Walkable" — adds NavMeshModifier(Not Walkable) to any
//      MeshRenderer whose AABB bottom is >= kFurnitureMinY. Then rebakes.
//   3. "Rebake NavMesh" — rebakes only.
//
// HOW TO USE:
//   a) Run "AITuber/NavMesh / Log Mesh Positions" and check the Console output.
//   b) If the listed furniture Y values look right, run
//      "AITuber/NavMesh / Mark Furniture Not Walkable + Rebake".
//   c) Play the scene, verify avatar walks correctly.
//
// SRS: FR-ROOM-01

using System.Text;
using Unity.AI.Navigation;
using UnityEditor;
using UnityEngine;
using UnityEngine.AI;

namespace AITuber.Editor
{
    public static class NavMeshFurnitureSetup
    {
        // Floor panels in this scene are extremely thin mesh panels (size.y ≈ 0).
        //   e.g. MFloor03-700x700-1  bottomY=0.035  topY=0.035  size.y≈0
        // All other objects (walls, furniture, props) have size.y > 0.05m and will
        // be marked Not Walkable. Walls and ceilings are vertical/overhead so they
        // don't produce walkable NavMesh even when included in the bake, but marking
        // them explicitly keeps the NavMesh clean and prevents edge-cases.
        //
        // Key offender identified by "1. Log Mesh Positions":
        //   CoffeeTable03_1  bottomY=0.035  topY=0.568  size.y=0.533
        //   → its top surface at y≈0.558 was baked as Walkable  (#warp-bug)
        private const float kFloorMaxSizeY  = 0.05f;  // panels thinner than this = floor
        private const float kFloorMaxBottomY = 0.05f; // floor panels sit near y=0

        // ------------------------------------------------------------------ //
        [MenuItem("AITuber/NavMesh/1. Log Mesh Positions")]
        public static void LogMeshPositions()
        {
            var renderers = Object.FindObjectsByType<MeshRenderer>(FindObjectsSortMode.None);
            var sb = new StringBuilder();
            sb.AppendLine($"[NavMeshSetup] MeshRenderer scan  (floor = sizeY < {kFloorMaxSizeY}m AND bottomY < {kFloorMaxBottomY}m):");
            sb.AppendLine($"  {"Name",-45} {"bottomY",8}  {"topY",8}  {"sizeY",7}  {"NavMesh area"}   [tag]");
            sb.AppendLine($"  {new string('-', 100)}");
            foreach (var mr in renderers)
            {
                float  bottomY = mr.bounds.min.y;
                float  topY    = mr.bounds.max.y;
                float  sizeY   = mr.bounds.size.y;
                var    mod     = mr.GetComponent<NavMeshModifier>();
                string area    = mod != null && mod.overrideArea
                    ? NavMesh.GetAreaNames()[mod.area]
                    : "(default)";
                bool   isFloor = sizeY < kFloorMaxSizeY && bottomY < kFloorMaxBottomY;
                string tag     = isFloor ? "FLOOR (keep)" : "NOT-WALKABLE";
                sb.AppendLine($"  {mr.gameObject.name,-45} {bottomY,8:F3}  {topY,8:F3}  {sizeY,7:F3}  {area,-18}  [{tag}]");
            }
            Debug.Log(sb.ToString());
        }

        // ------------------------------------------------------------------ //
        [MenuItem("AITuber/NavMesh/2. Mark Furniture Not Walkable + Rebake")]
        public static void MarkFurnitureAndRebake()
        {
            // CORRECT APPROACH: ignoreFromBuild = true (not Not Walkable area).
            //
            // Why NOT NavMeshModifier(area=Not Walkable):
            //   Furniture with bottomY at floor level (e.g. pilasters, wardrobes) would CARVE
            //   holes in the floor NavMesh. The agent spawn point (or the eat slot) can land in
            //   a hole → agent.isOnNavMesh=false → agent.Warp() jumps to hole edge → visible warp.
            //
            // Why ignoreFromBuild = true:
            //   The object is excluded from the NavMesh bake entirely.
            //   Floor panels (MFloor*) continue to contribute Walkable NavMesh uninterrupted.
            //   Furniture/walls don't contribute any surface — no sofa top, no holes in floor. ✓
            //   CharacterController / physical colliders prevent actual penetration. ✓

            int modified = 0;
            var renderers = Object.FindObjectsByType<MeshRenderer>(FindObjectsSortMode.None);
            foreach (var mr in renderers)
            {
                // Floor panels: very thin (size.y < 0.05m) and sitting at ground level → keep baked
                float sizeY   = mr.bounds.size.y;
                float bottomY = mr.bounds.min.y;
                bool  isFloor = sizeY < kFloorMaxSizeY && bottomY < kFloorMaxBottomY;
                if (isFloor) continue;

                var go  = mr.gameObject;
                var mod = go.GetComponent<NavMeshModifier>();
                if (mod == null)
                    mod = Undo.AddComponent<NavMeshModifier>(go);

                Undo.RecordObject(mod, "NavMesh: Exclude Furniture From Bake");
                mod.ignoreFromBuild = true;   // exclude entirely — never carves the floor
                mod.overrideArea    = false;   // clear any previous Not Walkable setting
                EditorUtility.SetDirty(go);

                Debug.Log($"[NavMeshSetup] '{go.name}'  sizeY={sizeY:F3} → ignoreFromBuild=true");
                modified++;
            }

            Debug.Log($"[NavMeshSetup] Excluded {modified} objects from NavMesh bake (ignoreFromBuild=true).");

            // Rebake all NavMeshSurfaces in the scene
            RebakeAll();
        }

        // ------------------------------------------------------------------ //
        [MenuItem("AITuber/NavMesh/3. Rebake NavMesh Only")]
        public static void RebakeAll()
        {
            var surfaces = Object.FindObjectsByType<NavMeshSurface>(FindObjectsSortMode.None);
            if (surfaces.Length == 0)
            {
                Debug.LogWarning("[NavMeshSetup] No NavMeshSurface found in scene.");
                return;
            }
            foreach (var s in surfaces)
            {
                s.BuildNavMesh();
                EditorUtility.SetDirty(s);
                Debug.Log($"[NavMeshSetup] NavMeshSurface '{s.gameObject.name}' rebaked.");
            }
            UnityEditor.SceneManagement.EditorSceneManager.MarkSceneDirty(
                UnityEngine.SceneManagement.SceneManager.GetActiveScene());
            Debug.Log("[NavMeshSetup] All NavMesh surfaces rebaked. Save the scene to persist.");
        }
    }
}
#endif
