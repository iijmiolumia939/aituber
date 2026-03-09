// Assets/Editor/AnimationGenerator.cs
// エディタ上で Idle + ジェスチャー AnimationClip を一括生成するユーティリティ。
// メニュー: AITuber > Generate Animation Clips

#if UNITY_EDITOR
using UnityEditor;
using UnityEditor.Animations;
using UnityEngine;
using System.IO;

namespace AITuber.Editor
{
    public static class AnimationGenerator
    {
        private const string OutputDir = "Assets/Animations/Clips";
        private const string ControllerPath = "Assets/Animations/AvatarAnimatorController.controller";

        [MenuItem("AITuber/Generate Animation Clips")]
        public static void GenerateAll()
        {
            if (!Directory.Exists(OutputDir))
                Directory.CreateDirectory(OutputDir);

            // ── Idle (呼吸モーション) ──────────────────────────────
            var idle = CreateIdleBreathing();
            SaveClip(idle, $"{OutputDir}/Idle_Breathing.anim");

            // ── ジェスチャー ──────────────────────────────────────
            var nod   = CreateNod();
            var shake = CreateShake();
            var wave  = CreateWave();
            var cheer = CreateCheer();
            var shrug = CreateShrug();
            var facepalm = CreateFacepalm();
            var laugh = CreateLaugh();

            SaveClip(nod,      $"{OutputDir}/Gesture_Nod.anim");
            SaveClip(shake,    $"{OutputDir}/Gesture_Shake.anim");
            SaveClip(wave,     $"{OutputDir}/Gesture_Wave.anim");
            SaveClip(cheer,    $"{OutputDir}/Gesture_Cheer.anim");
            SaveClip(shrug,    $"{OutputDir}/Gesture_Shrug.anim");
            SaveClip(facepalm, $"{OutputDir}/Gesture_Facepalm.anim");
            SaveClip(laugh,    $"{OutputDir}/Gesture_Laugh.anim");

            // ── AnimatorController に組み込み ─────────────────────
            // 先に SaveAssets + Refresh して GUID を確定させてから参照する
            AssetDatabase.SaveAssets();
            AssetDatabase.Refresh();

            SetupAnimatorController(
                $"{OutputDir}/Idle_Breathing.anim",
                $"{OutputDir}/Gesture_Nod.anim",
                $"{OutputDir}/Gesture_Shake.anim",
                $"{OutputDir}/Gesture_Wave.anim",
                $"{OutputDir}/Gesture_Cheer.anim",
                $"{OutputDir}/Gesture_Shrug.anim",
                $"{OutputDir}/Gesture_Facepalm.anim",
                $"{OutputDir}/Gesture_Laugh.anim");

            AssetDatabase.SaveAssets();
            AssetDatabase.Refresh();
            Debug.Log("[AnimationGenerator] All clips generated and AnimatorController updated.");
        }

        // ── Idle: 呼吸 (Spine 上下 + 微小回転) ─────────────────

        private static AnimationClip CreateIdleBreathing()
        {
            var clip = new AnimationClip();
            clip.name = "Idle_Breathing";
            clip.frameRate = 30f;

            // Spine Front-Back — 呼吸で体が微小に前後
            var spineY = new AnimationCurve();
            spineY.AddKey(new Keyframe(0f,   0f));
            spineY.AddKey(new Keyframe(1.5f, 0.4f));  // 吸気ピーク
            spineY.AddKey(new Keyframe(3.0f, 0f));       // 元に戻る
            SmoothCurve(spineY);
            clip.SetCurve("", typeof(Animator), "Spine Front-Back", spineY);

            // Chest 微小回転 X (前後の揺れ)
            var chestRotX = new AnimationCurve();
            chestRotX.AddKey(new Keyframe(0f,   0f));
            chestRotX.AddKey(new Keyframe(1.5f, 0.5f));
            chestRotX.AddKey(new Keyframe(3.0f, 0f));
            SmoothCurve(chestRotX);
            clip.SetCurve("", typeof(Animator), "Chest Front-Back", chestRotX);

            // ループ設定
            var settings = AnimationUtility.GetAnimationClipSettings(clip);
            settings.loopTime = true;
            settings.loopBlend = true;
            AnimationUtility.SetAnimationClipSettings(clip, settings);

            return clip;
        }

        // ── Nod: 頭を上下 ──────────────────────────────────────

        private static AnimationClip CreateNod()
        {
            var clip = new AnimationClip();
            clip.name = "Gesture_Nod";
            clip.frameRate = 30f;

            // Humanoid muscle 正規化値 -1〜+1 を使用
            // Head Nod Down-Up: 負値=頭が前(下)に傾く, 正値=頭が後ろに反る
            var headX = new AnimationCurve();
            headX.AddKey(new Keyframe(0f,    0f));
            headX.AddKey(new Keyframe(0.30f, -0.4f));  // 下を向く
            headX.AddKey(new Keyframe(0.60f,  0.1f));  // 少し上
            headX.AddKey(new Keyframe(1.00f, -0.35f)); // もう一度下
            headX.AddKey(new Keyframe(1.40f,  0f));    // 元に戻る
            SmoothCurve(headX);
            clip.SetCurve("", typeof(Animator), "Head Nod Down-Up", headX);

            SetOneShot(clip);
            return clip;
        }

        // ── Shake: 頭を左右 ────────────────────────────────────

        private static AnimationClip CreateShake()
        {
            var clip = new AnimationClip();
            clip.name = "Gesture_Shake";
            clip.frameRate = 30f;

            // Head Turn Left-Right: 正規化値 -1〜+1
            var headY = new AnimationCurve();
            headY.AddKey(new Keyframe(0f,    0f));
            headY.AddKey(new Keyframe(0.30f, -0.5f));
            headY.AddKey(new Keyframe(0.70f,  0.5f));
            headY.AddKey(new Keyframe(1.10f, -0.4f));
            headY.AddKey(new Keyframe(1.40f,  0f));
            SmoothCurve(headY);
            clip.SetCurve("", typeof(Animator), "Head Turn Left-Right", headY);

            SetOneShot(clip);
            return clip;
        }

        // ── Wave: 右手を振る ────────────────────────────────────

        private static AnimationClip CreateWave()
        {
            var clip = new AnimationClip();
            clip.name = "Gesture_Wave";
            clip.frameRate = 30f;

            // Humanoid muscle 正規化値 -1〜+1 を使用
            // Right Arm Down-Up: +1 = 腕が上方向, -1 = 腕が下方向
            // Wave では腕を上げる (正値)
            var armZ = new AnimationCurve();
            armZ.AddKey(new Keyframe(0f,    0f));
            armZ.AddKey(new Keyframe(0.4f,  0.9f));  // 腕を上げる (正規化 +0.9)
            armZ.AddKey(new Keyframe(1.6f,  0.9f));  // キープ
            armZ.AddKey(new Keyframe(2.0f,  0f));    // 戻す
            SmoothCurve(armZ);
            clip.SetCurve("", typeof(Animator), "Right Arm Down-Up", armZ);

            // Right Hand を左右に振る (正規化 ±0.5)
            var handY = new AnimationCurve();
            handY.AddKey(new Keyframe(0.4f,  0f));
            handY.AddKey(new Keyframe(0.70f, 0.5f));
            handY.AddKey(new Keyframe(1.00f, -0.5f));
            handY.AddKey(new Keyframe(1.30f, 0.5f));
            handY.AddKey(new Keyframe(1.60f, 0f));
            SmoothCurve(handY);
            clip.SetCurve("", typeof(Animator), "Right Hand In-Out", handY);

            SetOneShot(clip);
            return clip;
        }

        // ── Cheer: 両手を上げる ─────────────────────────────────

        private static AnimationClip CreateCheer()
        {
            var clip = new AnimationClip();
            clip.name = "Gesture_Cheer";
            clip.frameRate = 30f;

            // 両腕を上げる (正規化値 -1〜+1, +1 = 腕が上方向)
            var leftArmZ = new AnimationCurve();
            leftArmZ.AddKey(new Keyframe(0f,    0f));
            leftArmZ.AddKey(new Keyframe(0.50f, 0.8f));
            leftArmZ.AddKey(new Keyframe(1.40f, 0.8f));
            leftArmZ.AddKey(new Keyframe(2.0f,  0f));
            SmoothCurve(leftArmZ);
            clip.SetCurve("", typeof(Animator), "Left Arm Down-Up", leftArmZ);

            var rightArmZ = new AnimationCurve();
            rightArmZ.AddKey(new Keyframe(0f,    0f));
            rightArmZ.AddKey(new Keyframe(0.50f, 0.8f));
            rightArmZ.AddKey(new Keyframe(1.40f, 0.8f));
            rightArmZ.AddKey(new Keyframe(2.0f,  0f));
            SmoothCurve(rightArmZ);
            clip.SetCurve("", typeof(Animator), "Right Arm Down-Up", rightArmZ);

            SetOneShot(clip);
            return clip;
        }

        // ── Shrug: 肩をすくめる ─────────────────────────────────

        private static AnimationClip CreateShrug()
        {
            var clip = new AnimationClip();
            clip.name = "Gesture_Shrug";
            clip.frameRate = 30f;

            // 正規化値 -1〜+1。肩: +1 = 肩が上方向
            var leftShoulder = new AnimationCurve();
            leftShoulder.AddKey(new Keyframe(0f,   0f));
            leftShoulder.AddKey(new Keyframe(0.4f, 0.7f));
            leftShoulder.AddKey(new Keyframe(1.2f, 0.7f));
            leftShoulder.AddKey(new Keyframe(1.6f, 0f));
            SmoothCurve(leftShoulder);
            clip.SetCurve("", typeof(Animator), "Left Shoulder Down-Up", leftShoulder);

            var rightShoulder = new AnimationCurve();
            rightShoulder.AddKey(new Keyframe(0f,   0f));
            rightShoulder.AddKey(new Keyframe(0.4f, 0.7f));
            rightShoulder.AddKey(new Keyframe(1.2f, 0.7f));
            rightShoulder.AddKey(new Keyframe(1.6f, 0f));
            SmoothCurve(rightShoulder);
            clip.SetCurve("", typeof(Animator), "Right Shoulder Down-Up", rightShoulder);

            // 両手を少し広げる (腕を少し上へ)
            var leftArmZ = new AnimationCurve();
            leftArmZ.AddKey(new Keyframe(0f,   0f));
            leftArmZ.AddKey(new Keyframe(0.4f, 0.2f));
            leftArmZ.AddKey(new Keyframe(1.2f, 0.2f));
            leftArmZ.AddKey(new Keyframe(1.6f, 0f));
            SmoothCurve(leftArmZ);
            clip.SetCurve("", typeof(Animator), "Left Arm Down-Up", leftArmZ);

            var rightArmZ = new AnimationCurve();
            rightArmZ.AddKey(new Keyframe(0f,   0f));
            rightArmZ.AddKey(new Keyframe(0.4f, 0.2f));
            rightArmZ.AddKey(new Keyframe(1.2f, 0.2f));
            rightArmZ.AddKey(new Keyframe(1.6f, 0f));
            SmoothCurve(rightArmZ);
            clip.SetCurve("", typeof(Animator), "Right Arm Down-Up", rightArmZ);

            SetOneShot(clip);
            return clip;
        }

        // ── Facepalm: 右手で顔を覆う ────────────────────────────

        private static AnimationClip CreateFacepalm()
        {
            var clip = new AnimationClip();
            clip.name = "Gesture_Facepalm";
            clip.frameRate = 30f;

            // 正規化値 -1〜+1
            // Right Arm Down-Up: +1 = 腕が上方向。顔の位置まで上げる
            var armZ = new AnimationCurve();
            armZ.AddKey(new Keyframe(0f,   0f));
            armZ.AddKey(new Keyframe(0.6f, 0.5f));
            armZ.AddKey(new Keyframe(1.6f, 0.5f));
            armZ.AddKey(new Keyframe(2.2f, 0f));
            SmoothCurve(armZ);
            clip.SetCurve("", typeof(Animator), "Right Arm Down-Up", armZ);

            // 前腕を曲げて顔に近づける (Right Forearm Stretch: -1 = 完全に肘曲げ)
            var forearmX = new AnimationCurve();
            forearmX.AddKey(new Keyframe(0f,   0f));
            forearmX.AddKey(new Keyframe(0.6f, -0.8f));
            forearmX.AddKey(new Keyframe(1.6f, -0.8f));
            forearmX.AddKey(new Keyframe(2.2f, 0f));
            SmoothCurve(forearmX);
            clip.SetCurve("", typeof(Animator), "Right Forearm Stretch", forearmX);

            // 少し頭を下げる (Head Nod Down-Up: 負値 = 頭が前/下に傾く)
            var headX = new AnimationCurve();
            headX.AddKey(new Keyframe(0f,   0f));
            headX.AddKey(new Keyframe(0.6f, -0.2f));
            headX.AddKey(new Keyframe(1.6f, -0.2f));
            headX.AddKey(new Keyframe(2.2f, 0f));
            SmoothCurve(headX);
            clip.SetCurve("", typeof(Animator), "Head Nod Down-Up", headX);

            SetOneShot(clip);
            return clip;
        }

        // ── Helpers ──────────────────────────────────────────────
        /// <summary>
        /// 全キーフレームのタンジェントを ClampedAuto（滑らか話）に設定する。
        /// これを呼ばないと slope=0 水平タンジェントになりアニメがステップ状になる。
        /// </summary>
        private static void SmoothCurve(AnimationCurve curve)
        {
            for (int i = 0; i < curve.length; i++)
            {
                AnimationUtility.SetKeyLeftTangentMode(curve, i, AnimationUtility.TangentMode.ClampedAuto);
                AnimationUtility.SetKeyRightTangentMode(curve, i, AnimationUtility.TangentMode.ClampedAuto);
            }
        }

        /// <summary>
        /// AnimatorController にトリガーパラメータが存在しなければ追加する。
        /// </summary>
        private static void EnsureTrigger(AnimatorController controller, string paramName)
        {
            foreach (var p in controller.parameters)
            {
                if (p.name == paramName) return;
            }
            controller.AddParameter(paramName, AnimatorControllerParameterType.Trigger);
        }

        // ── Laugh: 笑いの抜け感 (胸・肩が飛び跳ねる) ─────────

        private static AnimationClip CreateLaugh()
        {
            var clip = new AnimationClip();
            clip.name = "Gesture_Laugh";
            clip.frameRate = 30f;

            // 正規化値 -1〜+1。Chest Front-Back: +1 = 胸が前に出る
            var chest = new AnimationCurve();
            chest.AddKey(new Keyframe(0f,    0f));
            chest.AddKey(new Keyframe(0.20f,  0.35f));
            chest.AddKey(new Keyframe(0.40f, -0.05f));
            chest.AddKey(new Keyframe(0.70f,  0.4f));
            chest.AddKey(new Keyframe(1.00f, -0.05f));
            chest.AddKey(new Keyframe(1.30f,  0.3f));
            chest.AddKey(new Keyframe(1.60f,  0f));
            SmoothCurve(chest);
            clip.SetCurve("", typeof(Animator), "Chest Front-Back", chest);

            // 両肩も跳ねる (肩: +1 = 肩が上方向)
            var leftShoulder = new AnimationCurve();
            leftShoulder.AddKey(new Keyframe(0f,    0f));
            leftShoulder.AddKey(new Keyframe(0.30f,  0.4f));
            leftShoulder.AddKey(new Keyframe(0.70f,  0.15f));
            leftShoulder.AddKey(new Keyframe(1.10f,  0.4f));
            leftShoulder.AddKey(new Keyframe(1.60f,  0f));
            SmoothCurve(leftShoulder);
            clip.SetCurve("", typeof(Animator), "Left Shoulder Down-Up", leftShoulder);

            var rightShoulder = new AnimationCurve();
            rightShoulder.AddKey(new Keyframe(0f,    0f));
            rightShoulder.AddKey(new Keyframe(0.30f,  0.4f));
            rightShoulder.AddKey(new Keyframe(0.70f,  0.15f));
            rightShoulder.AddKey(new Keyframe(1.10f,  0.4f));
            rightShoulder.AddKey(new Keyframe(1.60f,  0f));
            SmoothCurve(rightShoulder);
            clip.SetCurve("", typeof(Animator), "Right Shoulder Down-Up", rightShoulder);

            SetOneShot(clip);
            return clip;
        }
        private static void SetOneShot(AnimationClip clip)
        {
            var settings = AnimationUtility.GetAnimationClipSettings(clip);
            settings.loopTime = false;
            settings.loopBlend = false;
            AnimationUtility.SetAnimationClipSettings(clip, settings);
        }

        private static void SaveClip(AnimationClip clip, string path)
        {
            var existing = AssetDatabase.LoadAssetAtPath<AnimationClip>(path);
            if (existing != null)
            {
                EditorUtility.CopySerialized(clip, existing);
            }
            else
            {
                AssetDatabase.CreateAsset(clip, path);
            }
        }

        // ── AnimatorController 組み込み ──────────────────────────

        private static void SetupAnimatorController(
            string idlePath,
            string nodPath, string shakePath, string wavePath,
            string cheerPath, string shrugPath, string facepalmPath,
            string laughPath)
        {
            var controller = AssetDatabase.LoadAssetAtPath<AnimatorController>(ControllerPath);
            if (controller == null)
            {
                Debug.LogError($"[AnimationGenerator] Controller not found: {ControllerPath}");
                return;
            }

            // ディスクから保存済みアセットを読み込む（GUID 参照を保持するため必須）
            var idle     = AssetDatabase.LoadAssetAtPath<AnimationClip>(idlePath);
            var nod      = AssetDatabase.LoadAssetAtPath<AnimationClip>(nodPath);
            var shake    = AssetDatabase.LoadAssetAtPath<AnimationClip>(shakePath);
            var wave     = AssetDatabase.LoadAssetAtPath<AnimationClip>(wavePath);
            var cheer    = AssetDatabase.LoadAssetAtPath<AnimationClip>(cheerPath);
            var shrug    = AssetDatabase.LoadAssetAtPath<AnimationClip>(shrugPath);
            var facepalm = AssetDatabase.LoadAssetAtPath<AnimationClip>(facepalmPath);
            var laugh    = AssetDatabase.LoadAssetAtPath<AnimationClip>(laughPath);

            // Base Layer を取得
            var rootSM = controller.layers[0].stateMachine;

            // Idle ステートに Motion をセット
            AnimatorState idleState = null;
            foreach (var cs in rootSM.states)
            {
                if (cs.state.name == "Idle")
                {
                    idleState = cs.state;
                    break;
                }
            }
            if (idleState != null)
            {
                idleState.motion = idle;
            }

            // ジェスチャー用ステートを追加（既存なら更新）
            // パラメータも確実に存在させる（Laughなど追加分のため）
            EnsureTrigger(controller, "Nod");
            EnsureTrigger(controller, "Shake");
            EnsureTrigger(controller, "Wave");
            EnsureTrigger(controller, "Cheer");
            EnsureTrigger(controller, "Shrug");
            EnsureTrigger(controller, "Facepalm");
            EnsureTrigger(controller, "Laugh");

            AddOrUpdateGestureState(rootSM, idleState, "Nod",      nod,      "Nod");
            AddOrUpdateGestureState(rootSM, idleState, "Shake",    shake,    "Shake");
            AddOrUpdateGestureState(rootSM, idleState, "Wave",     wave,     "Wave");
            AddOrUpdateGestureState(rootSM, idleState, "Cheer",    cheer,    "Cheer");
            AddOrUpdateGestureState(rootSM, idleState, "Shrug",    shrug,    "Shrug");
            AddOrUpdateGestureState(rootSM, idleState, "Facepalm", facepalm, "Facepalm");
            AddOrUpdateGestureState(rootSM, idleState, "Laugh",    laugh,    "Laugh");

            EditorUtility.SetDirty(controller);
        }

        private static void AddOrUpdateGestureState(
            AnimatorStateMachine sm,
            AnimatorState idleState,
            string stateName,
            AnimationClip clip,
            string triggerParam,
            bool addExitTransition = true)
        {
            // 既存ステートを探す
            AnimatorState gestureState = null;
            foreach (var cs in sm.states)
            {
                if (cs.state.name == stateName)
                {
                    gestureState = cs.state;
                    break;
                }
            }

            // 新規作成
            if (gestureState == null)
            {
                gestureState = sm.AddState(stateName);
            }
            gestureState.motion = clip;

            // Idle → Gesture 遷移（トリガー条件）: 既存の遷移がなければ追加
            // gestureState == idleState（IdleAlt の自己遷移）は不要なのでスキップ
            bool hasTransitionFromIdle = false;
            if (idleState != null && idleState != gestureState)
            {
                foreach (var t in idleState.transitions)
                {
                    if (t.destinationState == gestureState)
                    {
                        hasTransitionFromIdle = true;
                        break;
                    }
                }
                if (!hasTransitionFromIdle)
                {
                    var t = idleState.AddTransition(gestureState);
                    t.hasExitTime = false;
                    t.duration = 0.1f;
                    t.AddCondition(AnimatorConditionMode.If, 0, triggerParam);
                }
            }

            // Gesture → Idle 遷移（Exit Time で自動戻り）: addExitTransition=true のときのみ追加
            // 既存の exitTime 遷移があれば宛先を idleState に更新（Idle→IdleAlt 移行対応）
            if (addExitTransition && idleState != null)
            {
                AnimatorStateTransition exitTransition = null;
                foreach (var t in gestureState.transitions)
                {
                    if (t.hasExitTime) { exitTransition = t; break; }
                }
                if (exitTransition == null)
                {
                    exitTransition = gestureState.AddTransition(idleState);
                    exitTransition.hasExitTime    = true;
                    exitTransition.exitTime       = 0.9f;
                    exitTransition.duration       = 0.15f;
                    exitTransition.hasFixedDuration = true;
                }
                else if (exitTransition.destinationState != idleState)
                {
                    // 宛先が古い Idle の場合は IdleAlt に更新
                    exitTransition.destinationState = idleState;
                }
            }
        }

        // ── Mixamo アニメーションをコントローラーに追加 ──────────────────

        private const string MixamoDir = "Assets/Clips/Mixamo";

        /// <summary>FBX の avatarSetup を CopyFromOther→CreateFromThisModel に修正するヘルパー</summary>
        private static void FixAvatarSetupForFbx(string fbxPath)
        {
            var imp = AssetImporter.GetAtPath(fbxPath) as ModelImporter;
            if (imp == null) return;
            if (imp.avatarSetup == ModelImporterAvatarSetup.CreateFromThisModel) return; // 既に正しい

            Debug.Log($"[Mixamo] Fixing avatar setup for: {System.IO.Path.GetFileName(fbxPath)}");

            // Step1: Generic → CopyFromOther の参照と humanDescription をクリア
            imp.animationType = ModelImporterAnimationType.Generic;
            imp.SaveAndReimport();

            // Step2: Human + CreateFromThisModel → 正しいアバターを自動生成
            imp.animationType = ModelImporterAnimationType.Human;
            imp.avatarSetup   = ModelImporterAvatarSetup.CreateFromThisModel;
            imp.SaveAndReimport();

            Debug.Log($"[Mixamo] After fix: avatarSetup={imp.avatarSetup}");
        }

        /// <summary>Mixamo FBX の中身を診断するデバッグメニュー</summary>
        [MenuItem("AITuber/Debug Mixamo FBX Assets")]
        public static void DebugMixamoFbxAssets()
        {
            string testPath = $"{MixamoDir}/Bashful.fbx";
            Debug.Log("[DebugMixamo] Testing 2-step approach (Generic first, then Human CreateFromThisModel)");

            var imp = AssetImporter.GetAtPath(testPath) as ModelImporter;
            if (imp == null) { Debug.LogError("[DebugMixamo] No ModelImporter!"); return; }

            Debug.Log($"[DebugMixamo] Before: animationType={imp.animationType}, avatarSetup={imp.avatarSetup}");

            // Step1: Generic に設定してimportすることで humanDescription と CopyFromOther 参照をクリア
            imp.animationType = ModelImporterAnimationType.Generic;
            imp.SaveAndReimport();
            Debug.Log($"[DebugMixamo] After Generic: animationType={imp.animationType}");

            // Step2: Human + CreateFromThisModel に設定
            imp.animationType = ModelImporterAnimationType.Human;
            imp.avatarSetup   = ModelImporterAvatarSetup.CreateFromThisModel;
            imp.SaveAndReimport();
            Debug.Log($"[DebugMixamo] After Human: animationType={imp.animationType}, avatarSetup={imp.avatarSetup}");

            var all = AssetDatabase.LoadAllAssetsAtPath(testPath);
            int clipCount = 0;
            foreach (var a in all)
                if (a is AnimationClip c && !c.name.Contains("__preview__")) { clipCount++; Debug.Log($"  Clip: {c.name}"); }
            Debug.Log($"[DebugMixamo] AnimationClip count = {clipCount}");
        }

        /// <summary>
        /// Mixamo FBX クリップ（shy/surprised/rejected/sigh 等）を
        /// AvatarAnimatorController に一括登録する。
        /// </summary>
        [MenuItem("AITuber/Add Mixamo Animations to Controller")]
        public static void AddMixamoAnimationsToController()
        {
            var controller = AssetDatabase.LoadAssetAtPath<AnimatorController>(ControllerPath);
            if (controller == null)
            {
                Debug.LogError($"[AnimationGenerator] Controller not found: {ControllerPath}");
                return;
            }

            var rootSM = controller.layers[0].stateMachine;

            // ジェスチャー終了後の戻り先は IdleAlt（全身ループ）を優先、なければ Idle
            AnimatorState idleState = null;
            foreach (var cs in rootSM.states)
                if (cs.state.name == "IdleAlt") { idleState = cs.state; break; }
            if (idleState == null)
                foreach (var cs in rootSM.states)
                    if (cs.state.name == "Idle") { idleState = cs.state; break; }

            // (FBX パス, トリガー名) のペアテーブル
            var entries = new (string fbx, string trigger)[]
            {
                ($"{MixamoDir}/Bashful.fbx",              "Shy"),
                ($"{MixamoDir}/Reacting.fbx",             "Surprised"),
                ($"{MixamoDir}/Rejected.fbx",             "Rejected"),
                ($"{MixamoDir}/Relieved Sigh.fbx",        "Sigh"),
                ($"{MixamoDir}/Thankful.fbx",             "Thankful"),
                ($"{MixamoDir}/Sad Idle.fbx",             "SadIdle"),
                ($"{MixamoDir}/Sad Idle kick.fbx",        "SadKick"),
                ($"{MixamoDir}/Thinking.fbx",             "Thinking"),
                ($"{MixamoDir}/Idle.fbx",                 "IdleAlt"),
                ($"{MixamoDir}/Sitting.fbx",              "SitDown"),
                ($"{MixamoDir}/Sitting Idle.fbx",         "SitIdle"),
                ($"{MixamoDir}/Sitting Laughing.fbx",     "SitLaugh"),
                ($"{MixamoDir}/Sitting Clap.fbx",         "SitClap"),
                ($"{MixamoDir}/Sitting And Pointing.fbx", "SitPoint"),
                ($"{MixamoDir}/Sitting Disbelief.fbx",    "SitDisbelief"),
                ($"{MixamoDir}/Sitting_kick.fbx",         "SitKick"),
                // Walk system (FR-LIFE-01)
                ($"{MixamoDir}/Female Walk.fbx",                  "Walk"),
                ($"{MixamoDir}/Female Start Walking.fbx",         "WalkStart"),
                ($"{MixamoDir}/Female Stop Walking.fbx",          "WalkStop"),
                ($"{MixamoDir}/Female Stop And Start Walking.fbx","WalkStopStart"),
            };

            // avatarSetup=CopyFromOther(破損状態) の FBX を先に修正する
            foreach (var (fbxPath, _) in entries)
                FixAvatarSetupForFbx(fbxPath);

            int added = 0;
            foreach (var (fbxPath, trigger) in entries)
            {
                // FBXから AnimationClip を取得
                AnimationClip clip = null;
                var allAssets = AssetDatabase.LoadAllAssetsAtPath(fbxPath);
                foreach (var a in allAssets)
                {
                    if (a is AnimationClip c && !c.name.Contains("__preview__"))
                    { clip = c; break; }
                }

                if (clip == null)
                {
                    Debug.LogWarning($"[Mixamo] AnimationClip not found in: {fbxPath}");
                    continue;
                }

                EnsureTrigger(controller, trigger);
                // IdleAlt 自身は exit 遷移不要（ループさせる）
                AddOrUpdateGestureState(rootSM, idleState, trigger, clip, trigger,
                    addExitTransition: trigger != "IdleAlt");
                added++;
                Debug.Log($"[Mixamo] Added state '{trigger}' with clip from {System.IO.Path.GetFileName(fbxPath)}");
            }

            EditorUtility.SetDirty(controller);
            AssetDatabase.SaveAssets();
            AssetDatabase.Refresh();
            Debug.Log($"[Mixamo] Done. {added} Mixamo clips registered in AnimatorController.");
        }
    }
}
#endif
