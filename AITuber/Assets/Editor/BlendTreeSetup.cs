// BlendTreeSetup.cs
// Adds a "LocoBlend" Blend Tree state to AvatarAnimatorController.
// Blends between IdleAlt (speed=0) and Walk (speed=1) via a "speed" Float parameter.
// Makes LocoBlend the default state; rewires non-loop gesture exits to LocoBlend.
//
// L-3 / Issue #49 / FR-BEHAVIOR-SEQ-01 (VirtualHome continuous locomotion)
//
// Usage: Unity Editor menu → [AITuber/Setup Loco Blend Tree]

using System.Collections.Generic;
using System.Linq;
using UnityEditor;
using UnityEditor.Animations;
using UnityEngine;

namespace AITuber.Editor
{
    public static class BlendTreeSetup
    {
        private const string ControllerPath = "Assets/Animations/AvatarAnimatorController.controller";

        [MenuItem("AITuber/Setup Loco Blend Tree")]
        public static void SetupLocoBlendTree()
        {
            var controller = AssetDatabase.LoadAssetAtPath<AnimatorController>(ControllerPath);
            if (controller == null)
            {
                Debug.LogError($"[BlendTreeSetup] Controller not found: {ControllerPath}");
                return;
            }

            var layer = controller.layers[0];
            var sm    = layer.stateMachine;

            // ── 既存 LocoBlend をスキップ（べき等）──────────────────────────
            if (sm.states.Any(s => s.state.name == "LocoBlend"))
            {
                Debug.Log("[BlendTreeSetup] LocoBlend already exists — skipping.");
                return;
            }

            // ── IdleAlt / Walk のクリップを取得 ────────────────────────────
            AnimatorState idleAltState = sm.states.FirstOrDefault(s => s.state.name == "IdleAlt").state;
            AnimatorState walkState    = sm.states.FirstOrDefault(s => s.state.name == "Walk").state;

            if (idleAltState == null)
            {
                Debug.LogError("[BlendTreeSetup] IdleAlt state not found.");
                return;
            }
            if (walkState == null)
            {
                Debug.LogError("[BlendTreeSetup] Walk state not found.");
                return;
            }

            AnimationClip idleClip = idleAltState.motion as AnimationClip;
            AnimationClip walkClip = walkState.motion as AnimationClip;

            if (idleClip == null)
            {
                Debug.LogError("[BlendTreeSetup] IdleAlt has no AnimationClip motion.");
                return;
            }
            if (walkClip == null)
            {
                Debug.LogError("[BlendTreeSetup] Walk has no AnimationClip motion.");
                return;
            }

            // ── "speed" Float パラメータ追加（なければ）─────────────────────
            bool hasSpeed = controller.parameters.Any(p => p.name == "speed");
            if (!hasSpeed)
            {
                controller.AddParameter("speed", AnimatorControllerParameterType.Float);
                Debug.Log("[BlendTreeSetup] Added Float parameter: speed");
            }
            else
            {
                Debug.Log("[BlendTreeSetup] Parameter 'speed' already exists — skipping add.");
            }

            // ── Blend Tree 作成 ─────────────────────────────────────────────
            // AnimatorController.CreateBlendTreeInController は内部 AssetDB に正しく登録する
            AnimatorState locoState = controller.CreateBlendTreeInController(
                "LocoBlend",
                out BlendTree blendTree,
                0  // layer index
            );

            blendTree.blendType      = BlendTreeType.Simple1D;
            blendTree.blendParameter = "speed";
            blendTree.name           = "LocoBlend";

            blendTree.AddChild(idleClip, 0f);  // speed=0 → IdleAlt clip
            blendTree.AddChild(walkClip, 1f);  // speed=1 → Walk clip

            locoState.motion             = blendTree;
            locoState.writeDefaultValues = true;
            locoState.speed              = 1f;

            Debug.Log($"[BlendTreeSetup] Created LocoBlend state (idle={idleClip.name}, walk={walkClip.name})");

            // ── LocoBlend をデフォルトステートに ─────────────────────────────
            sm.defaultState = locoState;
            Debug.Log("[BlendTreeSetup] LocoBlend set as default state.");

            // ── 非ループジェスチャーの exit → LocoBlend に変更 ────────────────
            // (従来 Idle/IdleAlt を向いていた exit トランジションを LocoBlend へ)
            int rewired = 0;
            foreach (var sChild in sm.states)
            {
                var st = sChild.state;
                // Skip LocoBlend itself, Walk chain states, and IdleAlt
                if (st == locoState || st == idleAltState || st == walkState
                    || st.name == "WalkStart" || st.name == "WalkStop" || st.name == "WalkStopStart"
                    || st.name == "Idle")
                    continue;

                foreach (var tr in st.transitions)
                {
                    if (tr.destinationState == idleAltState)
                    {
                        tr.destinationState = locoState;
                        rewired++;
                    }
                }
            }
            Debug.Log($"[BlendTreeSetup] Rewired {rewired} exit transition(s) → LocoBlend.");

            // ── 保存 ─────────────────────────────────────────────────────────
            EditorUtility.SetDirty(controller);
            AssetDatabase.SaveAssets();
            AssetDatabase.Refresh();

            Debug.Log("[BlendTreeSetup] Done. Run PlayMode to verify LocoBlend transitions.");
        }
    }
}
