using System.Collections.Generic;
using System.Linq;
using UnityEditor;
using UnityEditor.Animations;
using UnityEngine;

namespace AITuber.Editor
{
    /// <summary>
    /// Assets/Clips/Mixamo/ の FBX クリップを AvatarAnimatorController に
    /// 一括登録する。
    ///
    /// 使用方法: Unity エディタメニュー → [AITuber/Setup Mixamo Gestures]
    /// ※ 再実行しても重複登録しない（べき等）。
    /// </summary>
    public static class AnimatorSetup
    {
        private const string ControllerPath = "Assets/Animations/AvatarAnimatorController.controller";
        private const string MixamoFolder   = "Assets/Clips/Mixamo/";

        // FBX ファイル名 (拡張子なし) → (トリガー名, ループか)
        private static readonly Dictionary<string, (string trigger, bool loop)> ClipMap =
            new Dictionary<string, (string, bool)>
        {
            // 感情・リアクション系
            { "Bashful",              ("Shy",           false) },
            { "Laughing",             ("Laugh",         false) },
            { "Reacting",             ("Surprised",     false) },
            { "Rejected",             ("Rejected",      false) },
            { "Relieved Sigh",        ("Sigh",          false) },
            { "Thankful",             ("Thankful",      false) },

            // 悲しみ系
            { "Sad Idle",             ("SadIdle",       true)  },
            { "Sad Idle kick",        ("SadKick",       false) },

            // 思考系
            { "Thinking",             ("Thinking",      true)  },

            // 代替アイドル
            { "Idle",                 ("IdleAlt",       true)  },

            // 座り系
            // Note: Setup Seated Base Pose rebinds SitIdle to Sitting Idle.fbx so the sustained
            // seated pose remains visually stable after the sit-down transition.
            { "Sitting",              ("SitDown",       false) },
            { "Sitting Idle",         ("SitIdle",       true)  },
            { "Sitting Laughing",     ("SitLaugh",      false) },
            { "Sitting Clap",         ("SitClap",       false) },
            { "Sitting And Pointing", ("SitPoint",      false) },
            { "Sitting Disbelief",    ("SitDisbelief",  false) },
            { "Sitting_kick",         ("SitKick",       false) },

            // ── M4: スタンドアップ追加ジェスチャー (FR-LIFE-01) ──
            { "Bow",                  ("Bow",           false) },
            { "Clapping",             ("Clap",          false) },
            { "Thumbs Up",            ("ThumbsUp",      false) },
            { "Pointing Forward",     ("PointForward",  false) },
            { "Spin",                 ("Spin",          false) },

            // ── M19: 日常生活 Sims-like (FR-LIFE-01) ──
            // Walk chain は SetupWalkStateMachine で管理。ClipMap は Walk ループのみ保持。
            { "Female Walk",          ("Walk",          true)  },
            { "Sitting Reading",      ("SitRead",       true)  },
            { "Sitting Eating",       ("SitEat",        false) },
            { "Sitting Writing",      ("SitWrite",      true)  },
            { "Sleeping",             ("SleepIdle",     true)  },
            { "Stretching",           ("Stretch",       false) },
        };

        [MenuItem("AITuber/Setup Mixamo Gestures")]
        public static void SetupMixamoGestures()
        {
            var controller = AssetDatabase.LoadAssetAtPath<AnimatorController>(ControllerPath);
            if (controller == null)
            {
                Debug.LogError($"[AnimatorSetup] AnimatorController not found at: {ControllerPath}");
                return;
            }

            var layer = controller.layers[0];
            var sm    = layer.stateMachine;

            // 既存パラメータ・ステート名をキャッシュ
            var existingParams = new HashSet<string>(controller.parameters.Select(p => p.name));
            var existingStates = new HashSet<string>(sm.states.Select(s => s.state.name));

            // Idle ステートへの参照
            AnimatorState idleState = sm.states.FirstOrDefault(s => s.state.name == "Idle").state;

            int added = 0;
            int skipped = 0;

            foreach (var kvp in ClipMap)
            {
                string fbxName = kvp.Key;
                string trigger = kvp.Value.trigger;
                bool   loop    = kvp.Value.loop;

                // ── Trigger パラメータ追加（既存ステートでも必要）
                if (!existingParams.Contains(trigger))
                {
                    controller.AddParameter(trigger, AnimatorControllerParameterType.Trigger);
                    existingParams.Add(trigger);
                }

                AnimatorState state;

                if (existingStates.Contains(trigger))
                {
                    // ── 既存ステート: AnyState 遷移だけ補完する
                    state = sm.states.First(s => s.state.name == trigger).state;
                    skipped++;
                }
                else
                {
                    // ── FBX からクリップ取得
                    string fbxPath = $"{MixamoFolder}{fbxName}.fbx";
                    AnimationClip clip = LoadClipFromFbx(fbxPath);
                    if (clip == null)
                    {
                        Debug.LogWarning($"[AnimatorSetup] Clip not found: {fbxPath}  → Run 'AITuber/Register Gesture Triggers (Stubs)' for placeholder.");
                        continue;
                    }

                    // ── State 追加（グリッド配置）
                    Vector3 pos = GetGridPosition(added);
                    state = sm.AddState(trigger, pos);
                    state.motion             = clip;
                    state.writeDefaultValues = false;

                    // ── 一発再生ならば Idle へ戻る
                    if (!loop && idleState != null)
                    {
                        AnimatorStateTransition exitTrans = state.AddTransition(idleState);
                        exitTrans.hasExitTime  = true;
                        exitTrans.exitTime     = 0.85f;
                        exitTrans.duration     = 0.3f;
                        exitTrans.hasFixedDuration = false;  // normalized time
                    }

                    added++;
                    Debug.Log($"[AnimatorSetup] + {trigger}  ← {fbxName}.fbx  (loop={loop})");
                }

                // ── AnyState → State のトランジション（なければ追加）
                if (!WsmHasAnyStateTo(sm, trigger))
                {
                    AnimatorStateTransition anyTrans = sm.AddAnyStateTransition(state);
                    anyTrans.AddCondition(AnimatorConditionMode.If, 0f, trigger);
                    anyTrans.hasExitTime         = false;
                    anyTrans.duration            = 0.2f;
                    anyTrans.canTransitionToSelf = false;
                    Debug.Log($"[AnimatorSetup] + AnyState → {trigger}  (補完)");
                }
            }

            EditorUtility.SetDirty(controller);
            AssetDatabase.SaveAssets();

            ConfigureSeatedBasePose(controller);

            Debug.Log($"[AnimatorSetup] Done. added={added}, skipped(already exist)={skipped}");
        }

        [MenuItem("AITuber/Setup Seated Base Pose")]
        public static void SetupSeatedBasePose()
        {
            var controller = AssetDatabase.LoadAssetAtPath<AnimatorController>(ControllerPath);
            if (controller == null)
            {
                Debug.LogError($"[AnimatorSetup] AnimatorController not found at: {ControllerPath}");
                return;
            }

            ConfigureSeatedBasePose(controller);
        }

        /// <summary>
        /// Walk チェーン全体をセットアップする。
        ///
        /// 遷移グラフ:
        ///   AnyState ──[Walk]──► WalkStart(一発) ──[exitTime]──► Walk(ループ)
        ///   Walk(ループ) ──[WalkStop]──► WalkStop(一発) ──[exitTime]──► Idle
        ///   AnyState ──[WalkStopStart]──► WalkStopStart(一発) ──[exitTime]──► Walk(ループ)
        ///
        /// 使用方法: AITuber/Setup Walk State Machine
        /// FR-LIFE-01
        /// </summary>
        [MenuItem("AITuber/Setup Walk State Machine")]
        public static void SetupWalkStateMachine()
        {
            var controller = AssetDatabase.LoadAssetAtPath<AnimatorController>(ControllerPath);
            if (controller == null)
            {
                Debug.LogError($"[AnimatorSetup] AnimatorController not found at: {ControllerPath}");
                return;
            }

            var layer = controller.layers[0];
            var sm    = layer.stateMachine;

            AnimatorState idleState = sm.states.FirstOrDefault(s => s.state.name == "Idle").state;

            // ── Load real FBX clips ──
            AnimationClip clipWalk          = LoadClipFromFbx($"{MixamoFolder}Female Walk.fbx");
            AnimationClip clipWalkStart     = LoadClipFromFbx($"{MixamoFolder}Female Start Walking.fbx");
            AnimationClip clipWalkStop      = LoadClipFromFbx($"{MixamoFolder}Female Stop Walking.fbx");
            AnimationClip clipWalkStopStart = LoadClipFromFbx($"{MixamoFolder}Female Stop And Start Walking.fbx");

            // ── Ensure trigger parameters exist ──
            WsmEnsureParam(controller, "Walk",          AnimatorControllerParameterType.Trigger);
            WsmEnsureParam(controller, "WalkStop",      AnimatorControllerParameterType.Trigger);
            WsmEnsureParam(controller, "WalkStopStart", AnimatorControllerParameterType.Trigger);

            // ── Find or create states ──
            AnimatorState walkState          = WsmGetOrCreate(sm, "Walk",          new Vector3(900f, 120f, 0f));
            AnimatorState walkStartState     = WsmGetOrCreate(sm, "WalkStart",     new Vector3(700f, 120f, 0f));
            AnimatorState walkStopState      = WsmGetOrCreate(sm, "WalkStop",      new Vector3(1100f, 120f, 0f));
            AnimatorState walkStopStartState = WsmGetOrCreate(sm, "WalkStopStart", new Vector3(700f, 220f, 0f));

            // ── Assign real clips ──
            if (clipWalk          != null) { walkState.motion          = clipWalk;          Debug.Log("[AnimatorSetup] Walk         ← Female Walk.fbx"); }
            if (clipWalkStart     != null) { walkStartState.motion     = clipWalkStart;     Debug.Log("[AnimatorSetup] WalkStart    ← Female Start Walking.fbx"); }
            if (clipWalkStop      != null) { walkStopState.motion      = clipWalkStop;      Debug.Log("[AnimatorSetup] WalkStop     ← Female Stop Walking.fbx"); }
            if (clipWalkStopStart != null) { walkStopStartState.motion = clipWalkStopStart; Debug.Log("[AnimatorSetup] WalkStopStart← Female Stop And Start Walking.fbx"); }

            walkState.writeDefaultValues          = false;
            walkStartState.writeDefaultValues     = false;
            walkStopState.writeDefaultValues      = false;
            walkStopStartState.writeDefaultValues = false;

            // ── Remove old AnyState → Walk (replaced by → WalkStart) ──
            WsmRemoveAnyStateTo(sm, "Walk");

            // ── AnyState → WalkStart  (trigger: Walk) ──
            if (!WsmHasAnyStateTo(sm, "WalkStart"))
            {
                var t = sm.AddAnyStateTransition(walkStartState);
                t.AddCondition(AnimatorConditionMode.If, 0f, "Walk");
                t.hasExitTime         = false;
                t.duration            = 0.2f;
                t.canTransitionToSelf = false;
            }

            // ── WalkStart → Walk  (auto, exitTime=0.9) ──
            if (!WsmHasTransition(walkStartState, "Walk"))
            {
                var t = walkStartState.AddTransition(walkState);
                t.hasExitTime      = true;
                t.exitTime         = 0.9f;
                t.duration         = 0.2f;
                t.hasFixedDuration = false;
            }

            // ── Walk → WalkStop  (trigger: WalkStop) ──
            if (!WsmHasTransition(walkState, "WalkStop"))
            {
                var t = walkState.AddTransition(walkStopState);
                t.AddCondition(AnimatorConditionMode.If, 0f, "WalkStop");
                t.hasExitTime = false;
                t.duration    = 0.2f;
            }

            // ── WalkStop → Idle  (auto, exitTime=0.9) ──
            if (idleState != null && !WsmHasTransition(walkStopState, "Idle"))
            {
                var t = walkStopState.AddTransition(idleState);
                t.hasExitTime      = true;
                t.exitTime         = 0.9f;
                t.duration         = 0.3f;
                t.hasFixedDuration = false;
            }

            // ── AnyState → WalkStopStart  (trigger: WalkStopStart) ──
            WsmRemoveAnyStateTo(sm, "WalkStopStart");
            {
                var t = sm.AddAnyStateTransition(walkStopStartState);
                t.AddCondition(AnimatorConditionMode.If, 0f, "WalkStopStart");
                t.hasExitTime         = false;
                t.duration            = 0.2f;
                t.canTransitionToSelf = false;
            }

            // ── WalkStopStart → Walk  (auto, exitTime=0.9) ──
            if (!WsmHasTransition(walkStopStartState, "Walk"))
            {
                var t = walkStopStartState.AddTransition(walkState);
                t.hasExitTime      = true;
                t.exitTime         = 0.9f;
                t.duration         = 0.2f;
                t.hasFixedDuration = false;
            }

            EditorUtility.SetDirty(controller);
            AssetDatabase.SaveAssets();

            Debug.Log("[AnimatorSetup] Walk state machine setup complete.");
            Debug.Log("  Walk trigger → WalkStart → Walk(loop)");
            Debug.Log("  WalkStop trigger → WalkStop → Idle");
            Debug.Log("  WalkStopStart trigger → WalkStopStart → Walk(loop)");
        }

        // ── Walk State Machine helpers ─────────────────────────────────────

        private static void WsmEnsureParam(AnimatorController ctrl, string name, AnimatorControllerParameterType type)
        {
            if (!ctrl.parameters.Any(p => p.name == name))
                ctrl.AddParameter(name, type);
        }

        private static AnimatorState WsmGetOrCreate(AnimatorStateMachine sm, string name, Vector3 pos)
        {
            var found = sm.states.FirstOrDefault(s => s.state.name == name);
            if (found.state != null) return found.state;
            return sm.AddState(name, pos);
        }

        private static bool WsmHasAnyStateTo(AnimatorStateMachine sm, string stateName) =>
            sm.anyStateTransitions.Any(t => t.destinationState?.name == stateName);

        private static void WsmRemoveAnyStateTo(AnimatorStateMachine sm, string stateName)
        {
            foreach (var t in sm.anyStateTransitions
                                 .Where(t => t.destinationState?.name == stateName)
                                 .ToList())
                sm.RemoveAnyStateTransition(t);
        }

        private static bool WsmHasTransition(AnimatorState from, string toStateName) =>
            from.transitions.Any(t => t.destinationState?.name == toStateName);

        private static void ConfigureSeatedBasePose(AnimatorController controller)
        {
            var layer = controller.layers[0];
            var sm = layer.stateMachine;

            var sitIdleState = sm.states.FirstOrDefault(s => s.state.name == "SitIdle").state;
            if (sitIdleState == null)
            {
                Debug.LogWarning("[AnimatorSetup] SitIdle state not found; seated base pose setup skipped.");
                return;
            }

            AnimationClip seatedBaseClip = LoadClipFromFbx($"{MixamoFolder}Sitting Idle.fbx");
            if (seatedBaseClip == null)
            {
                Debug.LogWarning("[AnimatorSetup] Sitting Idle.fbx not found; seated base pose setup skipped.");
                return;
            }

            sitIdleState.motion = seatedBaseClip;
            sitIdleState.writeDefaultValues = false;

            // SitIdle 自身の exit 遷移をすべて除去（ループ維持 — 他トリガーでのみ離脱可能）
            foreach (var t in sitIdleState.transitions
                .Where(t => t.hasExitTime)
                .ToList())
            {
                string destName = t.destinationState != null ? t.destinationState.name : "(exit)";
                sitIdleState.RemoveTransition(t);
                Debug.Log($"[AnimatorSetup] Removed SitIdle → {destName} exit transition (loop state should not auto-exit).");
            }

            foreach (var stateName in new[] { "SitDown", "SitLaugh", "SitClap", "SitPoint", "SitDisbelief", "SitKick", "SitEat" })
            {
                var state = sm.states.FirstOrDefault(s => s.state.name == stateName).state;
                if (state == null)
                    continue;

                // SitIdle 以外への exit 遷移を除去（Idle, IdleAlt, LocoBlend 等）
                foreach (var transition in state.transitions
                    .Where(t => t.hasExitTime && t.destinationState?.name != "SitIdle")
                    .ToList())
                    state.RemoveTransition(transition);

                if (!WsmHasTransition(state, "SitIdle"))
                {
                    var exitTrans = state.AddTransition(sitIdleState);
                    exitTrans.hasExitTime = true;
                    exitTrans.exitTime = 0.85f;
                    exitTrans.duration = 0.2f;
                    exitTrans.hasFixedDuration = false;
                }
            }

            EditorUtility.SetDirty(controller);
            AssetDatabase.SaveAssets();
            Debug.Log("[AnimatorSetup] Seated base pose configured: SitIdle now uses Sitting Idle.fbx and seated one-shots return to SitIdle.");
        }

        // FBX から AnimationClip を1つ取得
        private static AnimationClip LoadClipFromFbx(string fbxPath)
        {
            Object[] assets = AssetDatabase.LoadAllAssetsAtPath(fbxPath);
            if (assets == null) return null;
            return assets.OfType<AnimationClip>()
                         .FirstOrDefault(c => !c.name.StartsWith("__preview__"));
        }

        // State をグリッド状に配置するヘルパー
        private static Vector3 GetGridPosition(int index)
        {
            const float startX = 300f;
            const float startY = -200f;
            const float stepX  = 250f;
            const float stepY  = 70f;
            const int   cols   = 3;

            int col = index % cols;
            int row = index / cols;
            return new Vector3(startX + col * stepX, startY + row * stepY, 0f);
        }

        /// <summary>
        /// FBX クリップが未用意でも、トリガーパラメータとスタブステート(Idle モーション)を
        /// まとめて登録する。Mixamo FBX 入手後に SetupMixamoGestures を実行することで
        /// 正規クリップに差し替え可能。
        ///
        /// 使用方法: AITuber/Register Gesture Triggers (Stubs)
        /// FR-LIFE-01
        /// </summary>
        [MenuItem("AITuber/Register Gesture Triggers (Stubs)")]
        public static void RegisterGestureTriggersAsStubs()
        {
            var controller = AssetDatabase.LoadAssetAtPath<AnimatorController>(ControllerPath);
            if (controller == null)
            {
                Debug.LogError($"[AnimatorSetup] AnimatorController not found at: {ControllerPath}");
                return;
            }

            var layer     = controller.layers[0];
            var sm        = layer.stateMachine;
            var existingParams = new HashSet<string>(controller.parameters.Select(p => p.name));
            var existingStates = new HashSet<string>(sm.states.Select(s => s.state.name));

            AnimatorState idleState = sm.states.FirstOrDefault(s => s.state.name == "Idle").state;

            // Idle モーションをスタブクリップとして流用
            AnimationClip stubClip = idleState?.motion as AnimationClip;
            if (stubClip == null)
            {
                string idleFbxPath = $"{MixamoFolder}Idle.fbx";
                stubClip = LoadClipFromFbx(idleFbxPath);
            }

            int added = 0, skipped = 0;
            foreach (var kvp in ClipMap)
            {
                string trigger = kvp.Value.trigger;
                bool   loop    = kvp.Value.loop;

                if (existingStates.Contains(trigger))
                {
                    skipped++;
                    continue;
                }

                // Trigger パラメータ追加
                if (!existingParams.Contains(trigger))
                {
                    controller.AddParameter(trigger, AnimatorControllerParameterType.Trigger);
                    existingParams.Add(trigger);
                }

                // スタブステート追加（Idle モーションを仮用）
                Vector3 pos   = GetGridPosition(added);
                AnimatorState state = sm.AddState(trigger, pos);
                state.motion             = stubClip;  // placeholder — replace with proper FBX later
                state.writeDefaultValues = false;

                // AnyState → stub state
                AnimatorStateTransition anyTrans = sm.AddAnyStateTransition(state);
                anyTrans.AddCondition(AnimatorConditionMode.If, 0f, trigger);
                anyTrans.hasExitTime         = false;
                anyTrans.duration            = 0.2f;
                anyTrans.canTransitionToSelf = false;

                // stub state → Idle（即時リターン）
                if (!loop && idleState != null)
                {
                    AnimatorStateTransition exitTrans = state.AddTransition(idleState);
                    exitTrans.hasExitTime      = true;
                    exitTrans.exitTime         = 0.85f;
                    exitTrans.duration         = 0.3f;
                    exitTrans.hasFixedDuration = false;
                }

                added++;
                Debug.Log($"[AnimatorSetup] +stub {trigger}  (loop={loop})  ← replace motion with Mixamo FBX later");
            }

            EditorUtility.SetDirty(controller);
            AssetDatabase.SaveAssets();

            Debug.Log($"[AnimatorSetup] Stubs done. added={added}, skipped={skipped}");
        }
    }
}
