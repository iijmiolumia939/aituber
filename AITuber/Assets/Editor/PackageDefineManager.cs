#if UNITY_EDITOR
// PackageDefineManager.cs — Issue #72
// パッケージの存在を検出して Scripting Define Symbols を自動設定する。
// Animation Rigging パッケージが Package Manager で解決されると
// HAS_ANIMATION_RIGGING シンボルが自動追加され、
// AnimationRiggingSetup.cs が有効化される。

using System.Linq;
using UnityEditor;
using UnityEditor.PackageManager;
using UnityEditor.PackageManager.Requests;

namespace AITuber.Editor
{
    [InitializeOnLoad]
    public static class PackageDefineManager
    {
        private const string AnimRigSymbol  = "HAS_ANIMATION_RIGGING";
        private const string AnimRigPackage = "com.unity.animation.rigging";

        private static ListRequest _listRequest;

        static PackageDefineManager()
        {
            Events.registeredPackages += OnPackagesChanged;
            // 非同期でパッケージリストを取得 (ブロッキングしない)
            _listRequest = Client.List(offlineMode: true);
            EditorApplication.update += PollListRequest;
        }

        private static void PollListRequest()
        {
            if (_listRequest == null || !_listRequest.IsCompleted) return;

            EditorApplication.update -= PollListRequest;

            if (_listRequest.Status == StatusCode.Success)
            {
                bool hasPackage = _listRequest.Result.Any(p => p.name == AnimRigPackage);
                SetDefine(AnimRigSymbol, hasPackage);
            }

            _listRequest = null;
        }

        private static void OnPackagesChanged(PackageRegistrationEventArgs args)
        {
            // パッケージ変更時に再チェック (非同期)
            _listRequest = Client.List(offlineMode: true);
            EditorApplication.update += PollListRequest;
        }

        private static void SetDefine(string symbol, bool enabled)
        {
            var group = BuildPipeline.GetBuildTargetGroup(EditorUserBuildSettings.activeBuildTarget);
            var namedTarget = UnityEditor.Build.NamedBuildTarget.FromBuildTargetGroup(group);
            PlayerSettings.GetScriptingDefineSymbols(namedTarget, out string[] defines);

            bool has = defines.Contains(symbol);
            if (enabled && !has)
            {
                var list = defines.ToList();
                list.Add(symbol);
                PlayerSettings.SetScriptingDefineSymbols(namedTarget, list.ToArray());
                UnityEngine.Debug.Log($"[PackageDefine] Added '{symbol}' — Animation Rigging features enabled.");
            }
            else if (!enabled && has)
            {
                var list = defines.Where(d => d != symbol).ToArray();
                PlayerSettings.SetScriptingDefineSymbols(namedTarget, list);
                UnityEngine.Debug.Log($"[PackageDefine] Removed '{symbol}' — package not found.");
            }
        }
    }
}
#endif
