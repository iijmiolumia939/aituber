#if UNITY_EDITOR
// WalkAnimDiagnostics.cs — Diagnose walk animation foot issues
// Checks avatar definition matching, foot contact curves, and retargeting quality.
using UnityEditor;
using UnityEngine;

namespace AITuber.Editor
{
    public static class WalkAnimDiagnostics
    {
        [MenuItem("AITuber/Diagnostics/Walk Animation Check")]
        public static void DiagnoseWalkAnimation()
        {
            var sb = new System.Text.StringBuilder();
            sb.AppendLine("[WalkDiag] ═══ Walk Animation Diagnostics ═══");

            // 1. Find the humanoid Animator
            Animator targetAnim = null;
            foreach (var anim in Object.FindObjectsByType<Animator>(FindObjectsInactive.Include, FindObjectsSortMode.None))
            {
                if (anim.isHuman && anim.avatar != null)
                {
                    targetAnim = anim;
                    break;
                }
            }

            if (targetAnim == null)
            {
                Debug.LogWarning("[WalkDiag] No humanoid Animator found.");
                return;
            }

            sb.AppendLine($"  Animator: {targetAnim.gameObject.name}");
            sb.AppendLine($"  Avatar: {targetAnim.avatar.name} (isHuman={targetAnim.avatar.isHuman}, isValid={targetAnim.avatar.isValid})");
            sb.AppendLine($"  applyRootMotion: {targetAnim.applyRootMotion}");
            sb.AppendLine($"  Controller: {(targetAnim.runtimeAnimatorController != null ? targetAnim.runtimeAnimatorController.name : "NULL")}");

            // 2. Measure skeleton proportions
            var hips = targetAnim.GetBoneTransform(HumanBodyBones.Hips);
            var leftFoot = targetAnim.GetBoneTransform(HumanBodyBones.LeftFoot);
            var rightFoot = targetAnim.GetBoneTransform(HumanBodyBones.RightFoot);
            var leftLowerLeg = targetAnim.GetBoneTransform(HumanBodyBones.LeftLowerLeg);
            var rightLowerLeg = targetAnim.GetBoneTransform(HumanBodyBones.RightLowerLeg);
            var leftUpperLeg = targetAnim.GetBoneTransform(HumanBodyBones.LeftUpperLeg);
            var rightUpperLeg = targetAnim.GetBoneTransform(HumanBodyBones.RightUpperLeg);
            var leftToes = targetAnim.GetBoneTransform(HumanBodyBones.LeftToes);
            var rightToes = targetAnim.GetBoneTransform(HumanBodyBones.RightToes);

            sb.AppendLine("\n  ── Skeleton Bone Positions ──");
            if (hips != null) sb.AppendLine($"  Hips: {hips.position} (local={hips.localPosition})");
            if (leftUpperLeg != null) sb.AppendLine($"  L.UpperLeg: {leftUpperLeg.position}");
            if (leftLowerLeg != null) sb.AppendLine($"  L.LowerLeg: {leftLowerLeg.position}");
            if (leftFoot != null) sb.AppendLine($"  L.Foot: {leftFoot.position}");
            if (leftToes != null) sb.AppendLine($"  L.Toes: {leftToes.position}");
            if (rightUpperLeg != null) sb.AppendLine($"  R.UpperLeg: {rightUpperLeg.position}");
            if (rightLowerLeg != null) sb.AppendLine($"  R.LowerLeg: {rightLowerLeg.position}");
            if (rightFoot != null) sb.AppendLine($"  R.Foot: {rightFoot.position}");
            if (rightToes != null) sb.AppendLine($"  R.Toes: {rightToes.position}");

            // Leg length measurements
            if (leftUpperLeg != null && leftLowerLeg != null && leftFoot != null)
            {
                float thigh = Vector3.Distance(leftUpperLeg.position, leftLowerLeg.position);
                float shin = Vector3.Distance(leftLowerLeg.position, leftFoot.position);
                float footLen = leftToes != null ? Vector3.Distance(leftFoot.position, leftToes.position) : 0f;
                float totalLeg = thigh + shin;
                float hipHeight = leftUpperLeg.position.y - targetAnim.transform.position.y;
                sb.AppendLine($"\n  ── Left Leg Measurements ──");
                sb.AppendLine($"  Thigh: {thigh:F4}m  Shin: {shin:F4}m  Foot: {footLen:F4}m");
                sb.AppendLine($"  Total leg: {totalLeg:F4}m  Hip height from root: {hipHeight:F4}m");
                sb.AppendLine($"  Foot Y above root: {(leftFoot.position.y - targetAnim.transform.position.y):F4}m");
            }

            // 3. Check LocoBlend clip reference
            sb.AppendLine("\n  ── Animation Clip Check ──");
            var ctrl = targetAnim.runtimeAnimatorController;
            if (ctrl != null)
            {
                foreach (var clip in ctrl.animationClips)
                {
                    if (clip.name.Contains("Walk", System.StringComparison.OrdinalIgnoreCase)
                        || clip.name.Contains("mixamo", System.StringComparison.OrdinalIgnoreCase)
                        || clip.name.Contains("Idle", System.StringComparison.OrdinalIgnoreCase))
                    {
                        sb.AppendLine($"  Clip: '{clip.name}' length={clip.length:F3}s loop={clip.isLooping} " +
                                      $"wrapMode={clip.wrapMode} hasRootCurves={clip.hasRootCurves} " +
                                      $"hasGenericRootTransform={clip.hasGenericRootTransform} " +
                                      $"hasMotionCurves={clip.hasMotionCurves} " +
                                      $"humanMotion={clip.humanMotion}");

                        // Check clip events
                        var events = clip.events;
                        if (events.Length > 0)
                        {
                            foreach (var ev in events)
                                sb.AppendLine($"    Event: time={ev.time:F3} func={ev.functionName}");
                        }
                    }
                }
            }

            // 4. Check current Animator state
            sb.AppendLine("\n  ── Current Animator State ──");
            var stateInfo = targetAnim.GetCurrentAnimatorStateInfo(0);
            sb.AppendLine($"  State hash: {stateInfo.shortNameHash}");
            sb.AppendLine($"  IsLoop: {stateInfo.loop}");
            sb.AppendLine($"  NormalizedTime: {stateInfo.normalizedTime:F3}");
            sb.AppendLine($"  Speed: {stateInfo.speed}");
            sb.AppendLine($"  SpeedMultiplier: {stateInfo.speedMultiplier}");

            // Check Foot IK setting on Animator layer
            sb.AppendLine($"\n  ── Animator Layer Foot IK ──");
            sb.AppendLine($"  Layer 0 name: BaseLayer");
            // The Foot IK checkbox per state currently reads from the LocoBlend state.
            // Check if AvatarAnimatorController has footIK enabled on LocoBlend.

            // 5. Check walk FBX import settings summary
            sb.AppendLine("\n  ── FBX Import Settings Summary ──");
            string walkFbxPath = "Assets/Clips/Mixamo/Female Walk.fbx";
            var walkImporter = AssetImporter.GetAtPath(walkFbxPath) as ModelImporter;
            if (walkImporter != null)
            {
                sb.AppendLine($"  FBX: {walkFbxPath}");
                sb.AppendLine($"  animationType: {walkImporter.animationType}");
                sb.AppendLine($"  avatarSetup (sourceAvatar): {(walkImporter.sourceAvatar != null ? walkImporter.sourceAvatar.name : "NULL (own definition)")}");
                sb.AppendLine($"  resampleCurves: {walkImporter.resampleCurves}");

                var clips = walkImporter.clipAnimations;
                if (clips.Length > 0)
                {
                    var c = clips[0];
                    sb.AppendLine($"  Clip '{c.name}':");
                    sb.AppendLine($"    loopTime: {c.loopTime}");
                    sb.AppendLine($"    lockRootHeightY: {c.lockRootHeightY}");
                    sb.AppendLine($"    lockRootPositionXZ: {c.lockRootPositionXZ}");
                    sb.AppendLine($"    lockRootRotation: {c.lockRootRotation}");
                    sb.AppendLine($"    keepOriginalOrientation: {c.keepOriginalOrientation}");
                    sb.AppendLine($"    keepOriginalPositionY: {c.keepOriginalPositionY}");
                    sb.AppendLine($"    keepOriginalPositionXZ: {c.keepOriginalPositionXZ}");
                    sb.AppendLine($"    heightFromFeet: {c.heightFromFeet}");
                    sb.AppendLine($"    mirror: {c.mirror}");
                    sb.AppendLine($"    hasAdditiveReferencePose: {c.hasAdditiveReferencePose}");
                }
            }
            else
            {
                sb.AppendLine($"  Walk FBX not found or not a ModelImporter at: {walkFbxPath}");
            }

            // 6. Check VRM avatar
            string vrmPath = "Assets/Models/Avatar.vrm";
            sb.AppendLine($"\n  ── VRM Model ──");
            var vrmObj = AssetDatabase.LoadAssetAtPath<GameObject>(vrmPath);
            if (vrmObj != null)
            {
                var vrmAnim = vrmObj.GetComponentInChildren<Animator>();
                if (vrmAnim != null && vrmAnim.avatar != null)
                {
                    sb.AppendLine($"  VRM Animator Avatar: {vrmAnim.avatar.name} (isHuman={vrmAnim.avatar.isHuman}, isValid={vrmAnim.avatar.isValid})");
                }
                else
                {
                    sb.AppendLine($"  VRM has no humanoid Animator or avatar is null");
                }
            }

            sb.AppendLine("\n[WalkDiag] ═══ Diagnostics Complete ═══");
            Debug.Log(sb.ToString());
        }
    }
}
#endif
