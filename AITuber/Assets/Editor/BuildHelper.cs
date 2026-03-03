// Assets/Editor/BuildHelper.cs
// メニューからワンクリックで Windows スタンドアロンビルドを生成。
// メニュー: AITuber > Build Windows Standalone

#if UNITY_EDITOR
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEngine;
using System.IO;
using System.Linq;

namespace AITuber.Editor
{
    public static class BuildHelper
    {
        private const string BuildDir = "Build";
        private const string ExeName = "AITuber.exe";

        /// <summary>
        /// メニューから Windows x64 スタンドアロンビルドを実行。
        /// </summary>
        [MenuItem("AITuber/Build Windows Standalone")]
        public static void BuildWindows()
        {
            // ビルドに含めるシーン（EditorBuildSettings に登録済みのシーン）
            string[] scenes = EditorBuildSettings.scenes
                .Where(s => s.enabled)
                .Select(s => s.path)
                .ToArray();

            if (scenes.Length == 0)
            {
                Debug.LogError("[BuildHelper] ビルドに含まれるシーンがありません。"
                    + " File > Build Settings でシーンを追加してください。");
                return;
            }

            // 出力先
            string buildPath = Path.Combine(BuildDir, ExeName);

            // Build ディレクトリ作成
            if (!Directory.Exists(BuildDir))
                Directory.CreateDirectory(BuildDir);

            Debug.Log($"[BuildHelper] ビルド開始: {buildPath}");
            Debug.Log($"[BuildHelper] シーン: {string.Join(", ", scenes)}");

            var options = new BuildPlayerOptions
            {
                scenes = scenes,
                locationPathName = buildPath,
                target = BuildTarget.StandaloneWindows64,
                options = BuildOptions.None,
            };

            BuildReport report = BuildPipeline.BuildPlayer(options);
            BuildSummary summary = report.summary;

            switch (summary.result)
            {
                case BuildResult.Succeeded:
                    long sizeMB = (long)summary.totalSize / (1024 * 1024);
                    Debug.Log($"[BuildHelper] ビルド成功！ ({sizeMB} MB, {summary.totalTime.TotalSeconds:F1}s)");
                    Debug.Log($"[BuildHelper] 出力先: {Path.GetFullPath(buildPath)}");

                    // ビルド完了後にフォルダを開く
                    EditorUtility.RevealInFinder(buildPath);
                    break;

                case BuildResult.Failed:
                    Debug.LogError($"[BuildHelper] ビルド失敗: エラー {summary.totalErrors} 件");
                    break;

                case BuildResult.Cancelled:
                    Debug.LogWarning("[BuildHelper] ビルドがキャンセルされました。");
                    break;
            }
        }

        /// <summary>
        /// コマンドラインからのバッチビルド用エントリーポイント。
        /// Unity -batchmode -executeMethod AITuber.Editor.BuildHelper.BatchBuild -quit
        /// </summary>
        public static void BatchBuild()
        {
            BuildWindows();
        }
    }
}
#endif
