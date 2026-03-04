// SetDefaultIdleAltSetup.cs
// Editor utility: rewires AvatarAnimatorController so IdleAlt is the default state
// and gesture states return to IdleAlt (instead of Idle which shows VRM T-pose).
//
// Menu: AITuber/Setup DefaultIdleAlt
//
// What this script does:
//   1. Changes the AnimatorStateMachine's defaultState from "Idle" → "IdleAlt"
//   2. Copies all trigger-based transitions from Idle → IdleAlt
//      (so triggers can fire from IdleAlt just like from Idle)
//   3. Adds an auto-transition Idle → IdleAlt (exitTime=0.05, duration=0.25)
//      so when a gesture completes and returns to Idle it quickly moves to IdleAlt
//   4. Changes IdleAlt's exit transition (was Idle) → IdleAlt self-loop
//   5. Sets Idle.writeDefaultValues = true so the brief Idle pass doesn't T-pose
//
// SRS refs: FR-A7-01 (avatar motion), TC-ANIM-IDLE-01
// Closes: GitHub Issue #11 (default PlayMode idle animation)

#if UNITY_EDITOR
using System.Linq;
using UnityEditor;
using UnityEditor.Animations;
using UnityEngine;

namespace AITuber.Editor
{
    public static class SetDefaultIdleAltSetup
    {
        private const string CtrlPath =
            "Assets/Animations/AvatarAnimatorController.controller";

        [MenuItem("AITuber/Setup DefaultIdleAlt")]
        public static void Run()
        {
            if (UnityEditor.EditorApplication.isPlaying)
            {
                Debug.LogWarning("[SetDefaultIdleAlt] Exit PlayMode first.");
                return;
            }

            var ctrl = AssetDatabase.LoadAssetAtPath<AnimatorController>(CtrlPath);
            if (ctrl == null)
            {
                Debug.LogError($"[SetDefaultIdleAlt] AnimatorController not found: {CtrlPath}");
                return;
            }

            var sm = ctrl.layers[0].stateMachine;

            // ── 1. Find Idle & IdleAlt ────────────────────────────────────────────
            AnimatorState idleState    = null;
            AnimatorState idleAltState = null;
            foreach (var cs in sm.states)
            {
                if (cs.state.name == "Idle")    idleState    = cs.state;
                if (cs.state.name == "IdleAlt") idleAltState = cs.state;
            }
            if (idleState == null || idleAltState == null)
            {
                Debug.LogError("[SetDefaultIdleAlt] Could not find 'Idle' or 'IdleAlt' state.");
                return;
            }

            bool changed = false;

            // ── 2. Change default state ───────────────────────────────────────────
            if (sm.defaultState != idleAltState)
            {
                sm.defaultState = idleAltState;
                Debug.Log("[SetDefaultIdleAlt] defaultState → IdleAlt");
                changed = true;
            }

            // ── 3. Idle.writeDefaultValues = true ────────────────────────────────
            if (!idleState.writeDefaultValues)
            {
                idleState.writeDefaultValues = true;
                Debug.Log("[SetDefaultIdleAlt] Idle.writeDefaultValues → true");
                changed = true;
            }

            // ── 4. Add auto-transition Idle → IdleAlt ─────────────────────────────
            bool autoExists = idleState.transitions.Any(t =>
                t.destinationState == idleAltState &&
                t.conditions.Length == 0);
            if (!autoExists)
            {
                var autoT = idleState.AddTransition(idleAltState);
                autoT.hasExitTime  = true;
                autoT.exitTime     = 0.05f;  // leave Idle after ~5% of its clip
                autoT.duration     = 0.25f;
                autoT.offset       = 0f;
                // no conditions → fires automatically
                Debug.Log("[SetDefaultIdleAlt] Added Idle → IdleAlt auto-transition (exitTime=0.05)");
                changed = true;
            }

            // ── 5. Copy trigger transitions Idle → IdleAlt ───────────────────────
            int copied = 0;
            foreach (var t in idleState.transitions)
            {
                var dst = t.destinationState;
                if (dst == null) continue;                // skip exit/machine transitions
                if (dst == idleAltState) continue;        // already on IdleAlt
                if (dst == idleState)    continue;        // skip self-loops

                // Only copy trigger-based (condition mode != Conditional.ExitTime)
                // i.e. skip pure exit-time transitions we may have added above
                if (t.conditions.Length == 0) continue;

                // Check duplicates by (destination, first condition parameter)
                bool dup = idleAltState.transitions.Any(existing =>
                    existing.destinationState == dst &&
                    existing.conditions.Length > 0 &&
                    existing.conditions[0].parameter == t.conditions[0].parameter);
                if (dup) continue;

                var newT = idleAltState.AddTransition(dst);
                newT.hasExitTime = t.hasExitTime;
                newT.exitTime    = t.exitTime;
                newT.duration    = t.duration;
                newT.offset      = t.offset;
                newT.canTransitionToSelf = t.canTransitionToSelf;
                foreach (var c in t.conditions)
                    newT.AddCondition(c.mode, c.threshold, c.parameter);

                copied++;
            }
            if (copied > 0)
            {
                Debug.Log($"[SetDefaultIdleAlt] Copied {copied} trigger transitions to IdleAlt.");
                changed = true;
            }

            // ── 6. Change IdleAlt exit transition: Idle → IdleAlt (self-loop) ────
            foreach (var t in idleAltState.transitions)
            {
                if (t.destinationState == idleState)
                {
                    t.destinationState = idleAltState;   // loop back to self
                    t.hasExitTime      = true;
                    t.exitTime         = 0.9f;
                    t.duration         = 0.25f;
                    // no conditions → just exit-time loop
                    Debug.Log("[SetDefaultIdleAlt] IdleAlt exit-transition → self (loop)");
                    changed = true;
                }
            }

            // ── 7. Save ──────────────────────────────────────────────────────────
            if (changed)
            {
                EditorUtility.SetDirty(ctrl);
                AssetDatabase.SaveAssets();
                Debug.Log("[SetDefaultIdleAlt] ✅ AvatarAnimatorController updated and saved.");
            }
            else
            {
                Debug.Log("[SetDefaultIdleAlt] No changes needed — already up to date.");
            }
        }
    }
}
#endif
