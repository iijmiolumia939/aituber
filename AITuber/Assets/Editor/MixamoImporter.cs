using System.Linq;
using UnityEditor;
using UnityEngine;

namespace AITuber.Editor
{
    /// <summary>
    /// Assets/Clips/Mixamo/ 以下の FBX を自動的に
    ///   - Humanoid rig
    ///   - Copy From Other Avatar (QuQu の UAvatar)
    ///   - Root motion を Bake Into Pose
    /// に設定する AssetPostprocessor。
    /// 既存ファイルは [AITuber/Reimport Mixamo FBXes] で再インポートできる。
    /// </summary>
    public class MixamoImporter : AssetPostprocessor
    {
        private const string MixamoFolder  = "Assets/Clips/Mixamo/";
        private const string QuQuFbxGuid   = "bc8d4e374324bb74c8a5f0b9207c33f4";

        // ── rig 設定 ─────────────────────────────────────────────────
        private void OnPreprocessModel()
        {
            if (!assetPath.StartsWith(MixamoFolder)) return;
            if (!assetPath.ToLower().EndsWith(".fbx"))  return;

            var mi = assetImporter as ModelImporter;
            if (mi == null) return;

            mi.animationType = ModelImporterAnimationType.Human;
            // sourceAvatar を設定すると自動的に "Copy From Other Avatar" モードになる

            // QuQu の UAvatar を source に設定
            string ququPath = AssetDatabase.GUIDToAssetPath(QuQuFbxGuid);
            if (!string.IsNullOrEmpty(ququPath))
            {
                var srcAvatar = AssetDatabase.LoadAllAssetsAtPath(ququPath)
                                             .OfType<UnityEngine.Avatar>()
                                             .FirstOrDefault();
                if (srcAvatar != null)
                    mi.sourceAvatar = srcAvatar;
                else
                    Debug.LogWarning("[MixamoImporter] QuQu Avatar sub-asset not found.");
            }
            else
                Debug.LogWarning("[MixamoImporter] QuQu FBX GUID not found in project.");
        }

        // ── clip 設定 (root motion bake) ─────────────────────────────
        private void OnPreprocessAnimation()
        {
            if (!assetPath.StartsWith(MixamoFolder)) return;

            var mi = assetImporter as ModelImporter;
            if (mi == null) return;

            ModelImporterClipAnimation[] clips = mi.clipAnimations;
            if (clips == null || clips.Length == 0)
                clips = mi.defaultClipAnimations;

            foreach (var clip in clips)
            {
                clip.lockRootPositionXZ       = true;
                clip.lockRootHeightY          = true;
                clip.lockRootRotation         = true;
                clip.keepOriginalOrientation  = true;
                clip.keepOriginalPositionXZ   = false;
                clip.keepOriginalPositionY    = false;
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
