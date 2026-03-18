using UnityEditor;
using UnityEngine;
using System;
using System.Collections.Generic;

namespace AITuber.Editor
{
    /// <summary>
    /// Assets/Clips/Mixamo/ 以下の FBX を自動的に
    ///   - Humanoid rig
    ///   - Create From This Model（元々は QuQu の UAvatar を使っていたが骨名不一致のため使用停止）
    ///   - Root motion を Bake Into Pose
    /// に設定する AssetPostprocessor。
    /// 既存ファイルは [AITuber/Reimport Mixamo FBXes] で再インポートできる。
    /// </summary>
    public class MixamoImporter : AssetPostprocessor
    {
        private const string MixamoFolder  = "Assets/Clips/Mixamo/";
        private static readonly HashSet<string> LoopingClips = new(StringComparer.OrdinalIgnoreCase)
        {
            "Female Walk",
            "Idle",
            "Sitting Reading",
            "Sitting Writing",
            "Sleeping",
        };

        // ── rig 設定 ─────────────────────────────────────────────────
        private void OnPreprocessModel()
        {
            if (!assetPath.StartsWith(MixamoFolder)) return;
            if (!assetPath.ToLower().EndsWith(".fbx"))  return;

            var mi = assetImporter as ModelImporter;
            if (mi == null) return;

            // Mixamo FBX は mixamorig:* ボーン名を使うため、自身の骨からアバターを生成する
            mi.animationType = ModelImporterAnimationType.Human;
            mi.sourceAvatar  = null;   // CopyFromOther を無効化
            mi.avatarSetup   = ModelImporterAvatarSetup.CreateFromThisModel;

            // Euler→Quaternion リサンプルを無効化し、元のカーブを保持する
            // QuQu と Mixamo の骨格プロポーション差で膝回転が劣化するのを防ぐ
            mi.resampleCurves = false;
        }

        // ── clip 設定 (root motion bake) ─────────────────────────────
        private void OnPreprocessAnimation()
        {
            if (!assetPath.StartsWith(MixamoFolder)) return;

            var mi = assetImporter as ModelImporter;
            if (mi == null) return;

            // defaultClipAnimations を常にベースとして使う
            // （meta に保存された clipAnimations は firstFrame/lastFrame が 0 の場合があるため）
            ModelImporterClipAnimation[] clips = mi.defaultClipAnimations;
            if (clips == null || clips.Length == 0) return;

            foreach (var clip in clips)
            {
                clip.lockRootPositionXZ       = true;
                clip.lockRootHeightY          = true;
                clip.lockRootRotation         = true;
                clip.keepOriginalOrientation  = true;
                clip.keepOriginalPositionXZ   = false;
                clip.keepOriginalPositionY    = false;
                bool shouldLoop = LoopingClips.Contains(System.IO.Path.GetFileNameWithoutExtension(assetPath));
                clip.loopTime = shouldLoop;
                clip.loopPose = shouldLoop;
            }
            mi.clipAnimations = clips;
        }

        // ── MenuItem: 既存ファイルを全て再インポート ─────────────────
        [MenuItem("AITuber/Reimport Mixamo FBXes")]
        public static void ReimportAll()
        {
            string[] guids = AssetDatabase.FindAssets("t:Object", new[] { MixamoFolder });
            int count = 0;
            foreach (string guid in guids)
            {
                string path = AssetDatabase.GUIDToAssetPath(guid);
                if (!path.ToLower().EndsWith(".fbx")) continue;
                AssetDatabase.ImportAsset(path, ImportAssetOptions.ForceUpdate);
                count++;
            }
            AssetDatabase.Refresh();
            Debug.Log($"[MixamoImporter] Reimported {count} FBX file(s).");
        }
    }
}
