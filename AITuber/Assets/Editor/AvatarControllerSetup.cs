// AvatarControllerSetup.cs — auto-wire AvatarController BlendShape indices
// Run via menu: AITuber/Setup AvatarController BlendShapes
// Body mesh BlendShape indices discovered 2026-03-04 via BlendShapeInspector tool.
//
// SRS refs: FR-A7-01, FR-LIPSYNC-01, FR-LIPSYNC-02

using UnityEngine;
using UnityEditor;
using AITuber.Avatar;

namespace AITuber.EditorTools
{
    public static class AvatarControllerSetup
    {
        [MenuItem("AITuber/Setup AvatarController BlendShapes")]
        public static void SetupBlendShapes()
        {
            // If in play mode, stop it and reschedule
            if (EditorApplication.isPlaying)
            {
                Debug.Log("[AvatarControllerSetup] Stopping PlayMode to apply BlendShape setup...");
                EditorApplication.isPlaying = false;
                EditorApplication.playModeStateChanged += OnPlayModeExited;
                return;
            }
            ApplySetup();
        }

        private static void OnPlayModeExited(PlayModeStateChange state)
        {
            if (state == PlayModeStateChange.EnteredEditMode)
            {
                EditorApplication.playModeStateChanged -= OnPlayModeExited;
                ApplySetup();
            }
        }

        private static void ApplySetup()
        {
            var ac = Object.FindFirstObjectByType<AvatarController>();
            if (ac == null)
            {
                Debug.LogError("[AvatarControllerSetup] AvatarController not found in scene.");
                return;
            }

            // --- Wire _faceMesh to "Body" SkinnedMeshRenderer ---
            var smrs = Object.FindObjectsByType<SkinnedMeshRenderer>(FindObjectsSortMode.None);
            SkinnedMeshRenderer bodyMesh = null;
            foreach (var s in smrs)
            {
                if (s.name == "Body")
                {
                    bodyMesh = s;
                    break;
                }
            }
            if (bodyMesh == null)
            {
                Debug.LogError("[AvatarControllerSetup] SkinnedMeshRenderer 'Body' not found.");
                return;
            }

            var so = new SerializedObject(ac);
            so.Update();

            // Wire face mesh reference
            so.FindProperty("_faceMesh").objectReferenceValue = bodyMesh;

            // ─── Expression BlendShape Indices ───────────────────────────
            so.FindProperty("_mouthOpenBlendIndex").intValue  = 78;  // jawOpen
            so.FindProperty("_joyBlendIndex").intValue        = 43;  // 笑い
            so.FindProperty("_angryBlendIndex").intValue      =  9;  // 怒り
            so.FindProperty("_sorrowBlendIndex").intValue     =  4;  // 困る
            so.FindProperty("_surprisedBlendIndex").intValue  =  8;  // びっくり
            so.FindProperty("_thinkingBlendIndex").intValue   = 21;  // えー
            so.FindProperty("_blinkBlendIndex").intValue      = 13;  // まばたき

            // ─── VRM Viseme Indices (jp_basic_8) ─────────────────────────
            so.FindProperty("_visemeAIndex").intValue         = 23;  // あ
            so.FindProperty("_visemeIIndex").intValue         = 24;  // い
            so.FindProperty("_visemeUIndex").intValue         = 25;  // う
            so.FindProperty("_visemeEIndex").intValue         = 27;  // え
            so.FindProperty("_visemeOIndex").intValue         = 26;  // お

            // ─── ARKit PerfectSync Mouth Indices ─────────────────────────
            so.FindProperty("_jawOpenIndex").intValue         = 78;  // jawOpen
            so.FindProperty("_mouthFunnelIndex").intValue     = 82;  // mouthFunnel
            so.FindProperty("_mouthPuckerIndex").intValue     = 83;  // mouthPucker
            so.FindProperty("_mouthLeftIndex").intValue       = 84;  // mouthLeft
            so.FindProperty("_mouthRightIndex").intValue      = 85;  // mouthRight
            so.FindProperty("_mouthRollUpperIndex").intValue  = 86;  // mouthRollUpper
            so.FindProperty("_mouthRollLowerIndex").intValue  = 87;  // mouthRollLower
            so.FindProperty("_mouthShrugUpperIndex").intValue = 88;  // mouthShrugUpper
            so.FindProperty("_mouthShrugLowerIndex").intValue = 89;  // mouthShrugLower
            so.FindProperty("_mouthCloseIndex").intValue      = 90;  // mouthClose
            so.FindProperty("_mouthSmileLIndex").intValue     = 91;  // mouthSmile_L
            so.FindProperty("_mouthSmileRIndex").intValue     = 92;  // mouthSmile_R
            so.FindProperty("_mouthFrownLIndex").intValue     = 93;  // mouthFrown_L
            so.FindProperty("_mouthFrownRIndex").intValue     = 94;  // mouthFrown_R
            so.FindProperty("_mouthLowerDownLIndex").intValue = 99;  // mouthLowerDown_L
            so.FindProperty("_mouthLowerDownRIndex").intValue =100;  // mouthLowerDown_R
            so.FindProperty("_mouthStretchLIndex").intValue   =103;  // mouthStretch_L
            so.FindProperty("_mouthStretchRIndex").intValue   =104;  // mouthStretch_R

            so.ApplyModifiedProperties();
            EditorUtility.SetDirty(ac);

            // Save scene (edit mode only)
            if (!EditorApplication.isPlaying)
            {
                var scene = UnityEditor.SceneManagement.EditorSceneManager.GetActiveScene();
                UnityEditor.SceneManagement.EditorSceneManager.SaveScene(scene);
            }

            Debug.Log($"[AvatarControllerSetup] ✅ AvatarController BlendShape indices set and scene saved.\n" +
                      $"  faceMesh   = {bodyMesh.name} ({bodyMesh.gameObject.name})\n" +
                      $"  joy={43}(笑い) angry={9}(怒り) sorrow={4}(困る) surprised={8}(びっくり) thinking={21}(えー)\n" +
                      $"  blink={13}(まばたき) mouthOpen={78}(jawOpen)\n" +
                      $"  viseme A={23} I={24} U={25} E={27} O={26}");
        }
    }
}
