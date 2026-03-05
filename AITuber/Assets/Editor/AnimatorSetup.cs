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
            { "Sitting",              ("SitDown",       false) },  // 座る動作 (1回)
            { "Sitting Idle",         ("SitIdle",       true)  },  // 座りアイドル (ループ)
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
            { "Walking",              ("Walk",          true)  },
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

                // ── 既に登録済みならスキップ
                if (existingStates.Contains(trigger))
                {
                    skipped++;
                    continue;
                }

                // ── FBX からクリップ取得
                string fbxPath = $"{MixamoFolder}{fbxName}.fbx";
                AnimationClip clip = LoadClipFromFbx(fbxPath);
                if (clip == null)
                {
                    Debug.LogWarning($"[AnimatorSetup] Clip not found: {fbxPath}  → Run 'AITuber/Register Gesture Triggers (Stubs)' for placeholder.");
                    continue;
                }

                // ── Trigger パラメータ追加
                if (!existingParams.Contains(trigger))
                {
                    controller.AddParameter(trigger, AnimatorControllerParameterType.Trigger);
                    existingParams.Add(trigger);
                }

                // ── State 追加（グリッド配置）
                Vector3 pos = GetGridPosition(added);
                AnimatorState state = sm.AddState(trigger, pos);
                state.motion             = clip;
                state.writeDefaultValues = false;

                // ── Any State → 新 State のトランジション
                AnimatorStateTransition anyTrans = sm.AddAnyStateTransition(state);
                anyTrans.AddCondition(AnimatorConditionMode.If, 0f, trigger);
                anyTrans.hasExitTime         = false;
                anyTrans.duration            = 0.2f;
                anyTrans.canTransitionToSelf = false;

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

            EditorUtility.SetDirty(controller);
            AssetDatabase.SaveAssets();

            Debug.Log($"[AnimatorSetup] Done. added={added}, skipped(already exist)={skipped}");
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
