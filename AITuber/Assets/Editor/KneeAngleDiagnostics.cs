#if UNITY_EDITOR
using UnityEditor;
using UnityEngine;

namespace AITuber.Editor
{
    /// <summary>
    /// 膝の角度を T-pose と歩行クリップの全フレームで検査し、
    /// 逆関節（過伸展）が起きているか診断する。
    /// Menu: AITuber/Diagnostics/Knee Angle Check
    /// </summary>
    public static class KneeAngleDiagnostics
    {
        [MenuItem("AITuber/Diagnostics/Knee Angle Check")]
        public static void DiagnoseKneeAngles()
        {
            var sb = new System.Text.StringBuilder();
            sb.AppendLine("[KneeDiag] ═══ Knee Angle Diagnostics ═══");

            // ── QuQu の T-pose 骨格からの膝方向ヒント ──
            sb.AppendLine("\n  ── QuQu T-pose Knee Direction (from U.fbx.meta) ──");
            AnalyzeTPoseKnee(sb);

            // ── ランタイム Animator がいれば実際の骨位置を確認 ──
            Animator anim = null;
            foreach (var a in Object.FindObjectsByType<Animator>(FindObjectsInactive.Include, FindObjectsSortMode.None))
            {
                if (a.isHuman && a.avatar != null && a.avatar.isValid)
                {
                    anim = a;
                    break;
                }
            }

            if (anim != null)
            {
                sb.AppendLine($"\n  ── Runtime Animator: {anim.gameObject.name} ──");
                sb.AppendLine($"  Avatar: {anim.avatar.name}");
                MeasureKneeAngle(sb, anim, "Left",
                    HumanBodyBones.LeftUpperLeg,
                    HumanBodyBones.LeftLowerLeg,
                    HumanBodyBones.LeftFoot);
                MeasureKneeAngle(sb, anim, "Right",
                    HumanBodyBones.RightUpperLeg,
                    HumanBodyBones.RightLowerLeg,
                    HumanBodyBones.RightFoot);

                // ── Walk クリップの全フレームで膝角度スキャン ──
                sb.AppendLine("\n  ── Walk Clip Frame-by-Frame Knee Scan ──");
                ScanWalkClipKneeAngles(sb, anim);
            }
            else
            {
                sb.AppendLine("\n  [INFO] Play モードで実行すると実際の骨位置を確認できます");
            }

            sb.AppendLine("\n[KneeDiag] ═══ Diagnostics Complete ═══");
            Debug.Log(sb.ToString());
        }

        static void AnalyzeTPoseKnee(System.Text.StringBuilder sb)
        {
            // U.fbx.meta のスケルトンデータから膝の前方ヒント角度を計算
            // L_LowerLeg rotation: {x: 0.03347667, y: 0, z: 0.0016620469, w: 0.99943817}
            // これは ~3.84° around X
            var lowerLegLocalRot = new Quaternion(0.03347667f, 0.00000009876385f, 0.0016620469f, 0.99943817f);
            float angleX = 2f * Mathf.Acos(Mathf.Abs(lowerLegLocalRot.w)) * Mathf.Rad2Deg;
            sb.AppendLine($"  L_LowerLeg local rotation (T-pose): {lowerLegLocalRot}");
            sb.AppendLine($"  Forward knee hint angle: ~{angleX:F2}°");
            sb.AppendLine($"  (推奨: 5-10° で逆関節が防げます。現在 {angleX:F1}° は小さめ)");

            // L_LowerLeg bone length (from U.fbx.meta skeleton)
            float shinLength = 0.31842f; // y position of L_Foot under L_LowerLeg
            float kneeForwardOffset = shinLength * Mathf.Sin(angleX * Mathf.Deg2Rad);
            sb.AppendLine($"  すね長: {shinLength:F4}m → T-pose 膝前方オフセット: {kneeForwardOffset * 100f:F2}cm");

            // Mixamo LeftLeg rotation for comparison
            var mixamoLegRot = new Quaternion(-0.34393024f, 0.08094896f, 0.018708022f, 0.9353124f);
            float mixamoAngle = 2f * Mathf.Acos(Mathf.Abs(mixamoLegRot.w)) * Mathf.Rad2Deg;
            sb.AppendLine($"\n  Mixamo LeftLeg local rotation (T-pose): {mixamoLegRot}");
            sb.AppendLine($"  Mixamo knee angle: ~{mixamoAngle:F2}°");
            sb.AppendLine($"  NOTE: Mixamo uses different bone axis convention (Z-axis vs X-axis)");
        }

        static void MeasureKneeAngle(System.Text.StringBuilder sb, Animator anim,
            string side, HumanBodyBones hipBone, HumanBodyBones kneeBone, HumanBodyBones ankleBone)
        {
            var hip = anim.GetBoneTransform(hipBone);
            var knee = anim.GetBoneTransform(kneeBone);
            var ankle = anim.GetBoneTransform(ankleBone);

            if (hip == null || knee == null || ankle == null)
            {
                sb.AppendLine($"  {side}: bones not found");
                return;
            }

            // 膝の角度を計算（hip→knee→ankle の折れ角）
            Vector3 thighDir = (knee.position - hip.position).normalized;
            Vector3 shinDir = (ankle.position - knee.position).normalized;
            float kneeAngle = Vector3.Angle(thighDir, shinDir);
            // 180° = まっすぐ、<180° = 正常な曲がり、>180° = 逆関節（実際にはAngleは0-180なので別の方法で判定）

            // 逆関節判定: knee が hip-ankle ラインより後ろにあるか
            Vector3 hipToAnkle = (ankle.position - hip.position).normalized;
            Vector3 hipToKnee = (knee.position - hip.position).normalized;
            Vector3 kneeForwardDir = Vector3.Cross(hipToAnkle, Vector3.right).normalized;
            float kneeDot = Vector3.Dot(knee.position - hip.position, anim.transform.forward);
            float ankleDot = Vector3.Dot(ankle.position - hip.position, anim.transform.forward);

            // 膝がキャラクターの前方にあるべき
            Vector3 midpoint = (hip.position + ankle.position) / 2f;
            Vector3 kneeOffset = knee.position - midpoint;
            float forwardComponent = Vector3.Dot(kneeOffset, anim.transform.forward);

            sb.AppendLine($"  {side} Knee:");
            sb.AppendLine($"    Hip:   {hip.position}");
            sb.AppendLine($"    Knee:  {knee.position}");
            sb.AppendLine($"    Ankle: {ankle.position}");
            sb.AppendLine($"    Knee angle (inner): {kneeAngle:F2}° (180°=straight)");
            sb.AppendLine($"    Knee forward offset: {forwardComponent * 100f:F2}cm ({(forwardComponent > 0 ? "FORWARD ✓" : "BACKWARD ✗ 逆関節!")})");
        }

        static void ScanWalkClipKneeAngles(System.Text.StringBuilder sb, Animator anim)
        {
            // Walk クリップを見つける
            AnimationClip walkClip = null;
            if (anim.runtimeAnimatorController != null)
            {
                foreach (var clip in anim.runtimeAnimatorController.animationClips)
                {
                    if (clip.name.Contains("Walk", System.StringComparison.OrdinalIgnoreCase)
                        && !clip.name.Contains("Start") && !clip.name.Contains("Stop"))
                    {
                        walkClip = clip;
                        break;
                    }
                }
            }

            if (walkClip == null)
            {
                sb.AppendLine("  Walk clip not found in controller");
                return;
            }

            sb.AppendLine($"  Scanning: '{walkClip.name}' ({walkClip.length:F3}s, {walkClip.frameRate}fps)");
            int totalFrames = Mathf.RoundToInt(walkClip.length * walkClip.frameRate);

            var leftHip = anim.GetBoneTransform(HumanBodyBones.LeftUpperLeg);
            var leftKnee = anim.GetBoneTransform(HumanBodyBones.LeftLowerLeg);
            var leftAnkle = anim.GetBoneTransform(HumanBodyBones.LeftFoot);

            if (leftHip == null || leftKnee == null || leftAnkle == null)
            {
                sb.AppendLine("  Left leg bones not found for scan");
                return;
            }

            float minAngle = 180f;
            int minAngleFrame = 0;
            int reverseFrameCount = 0;

            for (int frame = 0; frame <= totalFrames; frame++)
            {
                float time = frame / walkClip.frameRate;
                walkClip.SampleAnimation(anim.gameObject, time);

                Vector3 thighDir = (leftKnee.position - leftHip.position).normalized;
                Vector3 shinDir = (leftAnkle.position - leftKnee.position).normalized;
                float angle = Vector3.Angle(thighDir, shinDir);

                // Check forward direction
                Vector3 midpoint = (leftHip.position + leftAnkle.position) / 2f;
                float fwd = Vector3.Dot(leftKnee.position - midpoint, anim.transform.forward);

                if (angle < minAngle)
                {
                    minAngle = angle;
                    minAngleFrame = frame;
                }

                if (fwd < -0.001f)
                {
                    reverseFrameCount++;
                    if (reverseFrameCount <= 5)  // Only log first 5 instances
                    {
                        sb.AppendLine($"  ⚠ Frame {frame}/{totalFrames} (t={time:F3}s): angle={angle:F1}° fwd={fwd * 100f:F2}cm REVERSE KNEE");
                    }
                }
            }

            sb.AppendLine($"\n  Summary: min knee angle = {minAngle:F1}° at frame {minAngleFrame}");
            sb.AppendLine($"  Reverse knee frames: {reverseFrameCount}/{totalFrames + 1}");
            if (reverseFrameCount > 0)
            {
                sb.AppendLine("  → 逆関節が発生しています。T-pose の膝前方ヒント増加が必要です。");
            }
            else
            {
                sb.AppendLine("  → 逆関節は検出されませんでした ✓");
            }
        }
    }
}
#endif
