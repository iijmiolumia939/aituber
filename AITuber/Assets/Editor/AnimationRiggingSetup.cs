#if UNITY_EDITOR
// AnimationRiggingSetup.cs — Issue #72 (Animation Rigging 導入)
// Animation Rigging パッケージの Constraint をアバターにセットアップするエディタツール。
//
// 段階的アプローチ:
//   Phase 1: RigBuilder + Rig 階層の作成 (このスクリプト)
//   Phase 2: Override Transform Constraint (Hips XZ drift 補正)
//   Phase 3: Multi-Aim Constraint (視線制御の強化)
//   Phase 4: Two Bone IK Constraint (足接地の強化)
//
// 既存の Built-in Humanoid IK (AvatarIKProxy) は維持。
// Animation Rigging は追加レイヤーとして機能し、段階的に移行する。
//
// ⚠ com.unity.animation.rigging パッケージが必要。
//   Package Manager で解決されていない場合、このスクリプトは無効化されます。
//   PackageDefineManager.cs が自動的に HAS_ANIMATION_RIGGING シンボルを設定します。
//
// SRS refs: FR-ROOM-01, FR-LIFE-01

#if HAS_ANIMATION_RIGGING
using UnityEditor;
using UnityEngine;
using UnityEngine.Animations.Rigging;

namespace AITuber.Editor
{
    public static class AnimationRiggingSetup
    {
        // ── 1. RigBuilder 初期セットアップ ─────────────────────────

        [MenuItem("AITuber/Animation Rigging/1. Setup RigBuilder on Avatar")]
        public static void SetupRigBuilder()
        {
            // アバターモデル (Humanoid Animator) を見つける
            var animator = FindAvatarAnimator();
            if (animator == null)
            {
                Debug.LogError("[AnimRig] Humanoid Animator が見つかりません。シーンにアバターを配置してください。");
                return;
            }

            var avatarGo = animator.gameObject;

            // RigBuilder が既にあるか確認
            var rigBuilder = avatarGo.GetComponent<RigBuilder>();
            if (rigBuilder != null)
            {
                Debug.Log($"[AnimRig] RigBuilder は既に {avatarGo.name} に設定済みです。");
                return;
            }

            // RigBuilder を追加
            rigBuilder = Undo.AddComponent<RigBuilder>(avatarGo);

            // Rig 子オブジェクトを作成
            var rigGo = new GameObject("AnimationRig");
            Undo.RegisterCreatedObjectUndo(rigGo, "Create Animation Rig");
            rigGo.transform.SetParent(avatarGo.transform, false);

            var rig = Undo.AddComponent<Rig>(rigGo);

            // RigBuilder に Rig レイヤーを追加
            var layers = rigBuilder.layers;
            layers.Add(new RigLayer(rig, true));
            rigBuilder.layers = layers;

            EditorUtility.SetDirty(rigBuilder);
            EditorUtility.SetDirty(rigGo);

            Debug.Log($"[AnimRig] RigBuilder を {avatarGo.name} にセットアップしました。" +
                      $"\n  Rig 子オブジェクト: {rigGo.name}" +
                      $"\n  次は個別の Constraint を追加してください。");

            UnityEditor.SceneManagement.EditorSceneManager.MarkSceneDirty(
                UnityEngine.SceneManagement.SceneManager.GetActiveScene());
        }

        // ── 2. Override Transform (Hips drift 補正) ────────────────

        [MenuItem("AITuber/Animation Rigging/2. Add Hips Override Constraint")]
        public static void AddHipsOverride()
        {
            var (rig, animator) = GetOrCreateRig();
            if (rig == null) return;

            // 既存チェック
            if (rig.transform.Find("HipsOverride") != null)
            {
                Debug.Log("[AnimRig] HipsOverride は既に存在します。");
                return;
            }

            var hips = animator.GetBoneTransform(HumanBodyBones.Hips);
            if (hips == null)
            {
                Debug.LogError("[AnimRig] Hips ボーンが見つかりません。");
                return;
            }

            // Constraint オブジェクト作成
            var constraintGo = new GameObject("HipsOverride");
            Undo.RegisterCreatedObjectUndo(constraintGo, "Create Hips Override");
            constraintGo.transform.SetParent(rig.transform, false);

            var constraint = Undo.AddComponent<OverrideTransformConstraint>(constraintGo);

            // Constraint データ設定
            constraint.data.constrainedObject = hips;

            // ソース: AvatarRoot (NavMeshAgent の位置)
            var avatarRoot = animator.transform.parent;
            if (avatarRoot == null) avatarRoot = animator.transform;

            // XZ ソースとなるターゲット Transform を作成
            var targetGo = new GameObject("HipsXZTarget");
            Undo.RegisterCreatedObjectUndo(targetGo, "Create Hips XZ Target");
            targetGo.transform.SetParent(avatarRoot, false);
            targetGo.transform.localPosition = Vector3.zero;

            constraint.data.sourceObject = targetGo.transform;
            constraint.data.space = OverrideTransformData.Space.World;

            // Position のみ (X, Z)。Y と Rotation はアニメーション任せ
            constraint.data.positionWeight = 0f; // 初期は無効 — テスト後に有効化
            constraint.data.rotationWeight = 0f;

            constraint.weight = 0f; // 安全のため初期無効

            EditorUtility.SetDirty(constraintGo);
            EditorUtility.SetDirty(targetGo);

            Debug.Log("[AnimRig] HipsOverride Constraint を追加しました。" +
                      "\n  ⚠ weight=0 で無効状態です。テスト後に Inspector で weight を上げてください。" +
                      "\n  constrainedObject: Hips" +
                      $"\n  sourceObject: {targetGo.name} (AvatarRoot 子)");

            UnityEditor.SceneManagement.EditorSceneManager.MarkSceneDirty(
                UnityEngine.SceneManagement.SceneManager.GetActiveScene());
        }

        // ── 3. Multi-Aim Constraint (視線制御) ─────────────────────

        [MenuItem("AITuber/Animation Rigging/3. Add Gaze MultiAim Constraint")]
        public static void AddGazeMultiAim()
        {
            var (rig, animator) = GetOrCreateRig();
            if (rig == null) return;

            if (rig.transform.Find("GazeMultiAim") != null)
            {
                Debug.Log("[AnimRig] GazeMultiAim は既に存在します。");
                return;
            }

            var head = animator.GetBoneTransform(HumanBodyBones.Head);
            if (head == null)
            {
                Debug.LogError("[AnimRig] Head ボーンが見つかりません。");
                return;
            }

            var constraintGo = new GameObject("GazeMultiAim");
            Undo.RegisterCreatedObjectUndo(constraintGo, "Create Gaze MultiAim");
            constraintGo.transform.SetParent(rig.transform, false);

            var constraint = Undo.AddComponent<MultiAimConstraint>(constraintGo);
            constraint.data.constrainedObject = head;

            // LookAt ターゲットは GazeController が管理するため、
            // ここでは空の WeightedTransformArray を設定。
            // 運用時に GazeController のターゲットを登録する。
            constraint.weight = 0f; // 初期無効

            EditorUtility.SetDirty(constraintGo);

            Debug.Log("[AnimRig] GazeMultiAim Constraint を追加しました。" +
                      "\n  ⚠ weight=0 で無効状態です。" +
                      "\n  constrainedObject: Head" +
                      "\n  → GazeController のターゲットを sourceObjects に追加して有効化してください。");

            UnityEditor.SceneManagement.EditorSceneManager.MarkSceneDirty(
                UnityEngine.SceneManagement.SceneManager.GetActiveScene());
        }

        // ── 4. Two Bone IK (足接地) ────────────────────────────────

        [MenuItem("AITuber/Animation Rigging/4. Add Foot TwoBoneIK Constraints")]
        public static void AddFootTwoBoneIK()
        {
            var (rig, animator) = GetOrCreateRig();
            if (rig == null) return;

            AddFootIK(rig, animator, "LeftFoot",
                HumanBodyBones.LeftUpperLeg,
                HumanBodyBones.LeftLowerLeg,
                HumanBodyBones.LeftFoot);

            AddFootIK(rig, animator, "RightFoot",
                HumanBodyBones.RightUpperLeg,
                HumanBodyBones.RightLowerLeg,
                HumanBodyBones.RightFoot);

            Debug.Log("[AnimRig] Foot TwoBoneIK Constraints を追加しました。" +
                      "\n  ⚠ weight=0 で無効状態です。テスト後に有効化してください。");

            UnityEditor.SceneManagement.EditorSceneManager.MarkSceneDirty(
                UnityEngine.SceneManagement.SceneManager.GetActiveScene());
        }

        // ── 5. 全 Constraint ウェイトの一括制御 ────────────────────

        [MenuItem("AITuber/Animation Rigging/Enable All Constraints (weight=1)")]
        public static void EnableAll()
        {
            var rig = FindRig();
            if (rig == null) return;
            SetAllWeights(rig, 1f);
            Debug.Log("[AnimRig] 全 Constraint を有効化しました (weight=1)。");
        }

        [MenuItem("AITuber/Animation Rigging/Disable All Constraints (weight=0)")]
        public static void DisableAll()
        {
            var rig = FindRig();
            if (rig == null) return;
            SetAllWeights(rig, 0f);
            Debug.Log("[AnimRig] 全 Constraint を無効化しました (weight=0)。");
        }

        // ── 6. 状態確認 ────────────────────────────────────────────

        [MenuItem("AITuber/Animation Rigging/Diagnostics")]
        public static void Diagnostics()
        {
            var animator = FindAvatarAnimator();
            if (animator == null)
            {
                Debug.LogWarning("[AnimRig] Humanoid Animator が見つかりません。");
                return;
            }

            var sb = new System.Text.StringBuilder();
            sb.AppendLine("[AnimRig] ═══ Animation Rigging Diagnostics ═══");

            var rigBuilder = animator.GetComponent<RigBuilder>();
            if (rigBuilder == null)
            {
                sb.AppendLine("  ⚠ RigBuilder 未設定。'1. Setup RigBuilder on Avatar' を実行してください。");
                Debug.LogWarning(sb.ToString());
                return;
            }

            sb.AppendLine($"  RigBuilder: {animator.gameObject.name}");
            sb.AppendLine($"    layers: {rigBuilder.layers.Count}");

            foreach (var layer in rigBuilder.layers)
            {
                if (layer.rig == null) continue;
                sb.AppendLine($"\n  Rig: {layer.rig.gameObject.name}  active={layer.active}");

                // 子 Constraint を列挙
                foreach (Transform child in layer.rig.transform)
                {
                    var components = child.GetComponents<MonoBehaviour>();
                    foreach (var comp in components)
                    {
                        if (comp is IRigConstraint rc)
                        {
                            sb.AppendLine($"    {child.name}: {comp.GetType().Name}  weight={rc.weight:F2}");
                        }
                    }
                }
            }

            Debug.Log(sb.ToString());
        }

        // ── Internal helpers ────────────────────────────────────────

        private static Animator FindAvatarAnimator()
        {
            foreach (var a in Object.FindObjectsByType<Animator>(FindObjectsSortMode.None))
            {
                if (a.isHuman) return a;
            }
            return null;
        }

        private static Rig FindRig()
        {
            var animator = FindAvatarAnimator();
            if (animator == null) return null;
            return animator.GetComponentInChildren<Rig>();
        }

        private static (Rig rig, Animator animator) GetOrCreateRig()
        {
            var animator = FindAvatarAnimator();
            if (animator == null)
            {
                Debug.LogError("[AnimRig] Humanoid Animator が見つかりません。");
                return (null, null);
            }

            var rig = animator.GetComponentInChildren<Rig>();
            if (rig == null)
            {
                Debug.LogWarning("[AnimRig] Rig が見つかりません。RigBuilder をセットアップします…");
                SetupRigBuilder();
                rig = animator.GetComponentInChildren<Rig>();
            }

            return (rig, animator);
        }

        private static void AddFootIK(Rig rig, Animator animator, string name,
            HumanBodyBones upper, HumanBodyBones lower, HumanBodyBones tip)
        {
            string constraintName = $"{name}IK";
            if (rig.transform.Find(constraintName) != null) return;

            var upperBone = animator.GetBoneTransform(upper);
            var lowerBone = animator.GetBoneTransform(lower);
            var tipBone   = animator.GetBoneTransform(tip);

            if (upperBone == null || lowerBone == null || tipBone == null)
            {
                Debug.LogWarning($"[AnimRig] {name} のボーンが見つかりません。スキップ。");
                return;
            }

            var constraintGo = new GameObject(constraintName);
            Undo.RegisterCreatedObjectUndo(constraintGo, $"Create {name} IK");
            constraintGo.transform.SetParent(rig.transform, false);

            var constraint = Undo.AddComponent<TwoBoneIKConstraint>(constraintGo);
            constraint.data.root = upperBone;
            constraint.data.mid  = lowerBone;
            constraint.data.tip  = tipBone;

            // IK ターゲット作成
            var targetGo = new GameObject($"{name}IK_Target");
            Undo.RegisterCreatedObjectUndo(targetGo, $"Create {name} IK Target");
            targetGo.transform.SetParent(rig.transform, false);
            targetGo.transform.position = tipBone.position;
            targetGo.transform.rotation = tipBone.rotation;

            constraint.data.target = targetGo.transform;
            constraint.weight = 0f; // 安全のため初期無効

            EditorUtility.SetDirty(constraintGo);
            EditorUtility.SetDirty(targetGo);
        }

        private static void SetAllWeights(Rig rig, float weight)
        {
            foreach (Transform child in rig.transform)
            {
                foreach (var comp in child.GetComponents<MonoBehaviour>())
                {
                    if (comp is IRigConstraint rc)
                    {
                        Undo.RecordObject(comp, "Set constraint weight");
                        rc.weight = weight;
                        EditorUtility.SetDirty(comp);
                    }
                }
            }
        }
    }
}
#endif // HAS_ANIMATION_RIGGING
#endif // UNITY_EDITOR
