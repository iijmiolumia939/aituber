// NativePluginConfigurator.cs
// Programmatically sets platform settings for A2FPlugin.dll and A2GPlugin.dll
// so their .meta files are generated correctly by Unity's own serializer.
// Without this, manually-written meta files fail YAML parsing in Unity 6.
//
// Runs once automatically via [InitializeOnLoad] static constructor.
// Can also be run manually from: Tools > Configure Native Plugins

using System.IO;
using UnityEditor;
using UnityEngine;

[InitializeOnLoad]
public static class NativePluginConfigurator
{
    private static readonly string[] s_PluginPaths =
    {
        "Assets/Plugins/x86_64/audio2x.dll",
        "Assets/Plugins/x86_64/A2FPlugin.dll",
        "Assets/Plugins/x86_64/A2GPlugin.dll",
    };

    static NativePluginConfigurator()
    {
        // Defer until Editor is idle to avoid import loop on startup
        EditorApplication.delayCall += ConfigurePluginsIfNeeded;
    }

    [MenuItem("Tools/Configure Native Plugins (A2F/A2G)")]
    public static void ConfigurePlugins()
    {
        int configured = 0;
        foreach (string path in s_PluginPaths)
        {
            if (!File.Exists(Path.Combine(Application.dataPath, "../", path)))
            {
                Debug.LogWarning($"[NativePluginConfigurator] DLL not found: {path}");
                continue;
            }

            var importer = AssetImporter.GetAtPath(path) as PluginImporter;
            if (importer == null)
            {
                Debug.LogWarning($"[NativePluginConfigurator] Could not get PluginImporter for {path}");
                continue;
            }

            // Reset all platform compatibility
            importer.SetCompatibleWithAnyPlatform(false);

            // Editor: disabled (prevents TRT heap corruption in Editor Play Mode)
            importer.SetCompatibleWithEditor(false);

            // isPreloaded: disabled (prevents Unity from loading before scripts in Editor)
            importer.isPreloaded = false;

            // Standalone Win64: enabled, CPU = x86_64
            importer.SetCompatibleWithPlatform(BuildTarget.StandaloneWindows64, true);
            importer.SetPlatformData(BuildTarget.StandaloneWindows64, "CPU", "x86_64");

            importer.SaveAndReimport();
            configured++;
            Debug.Log($"[NativePluginConfigurator] Configured {path}: Editor=false, Win64=true");
        }

        if (configured > 0)
            Debug.Log($"[NativePluginConfigurator] Done: {configured} plugin(s) configured.");
        else
            Debug.LogWarning("[NativePluginConfigurator] No plugins configured — verify DLL paths.");
    }

    private static void ConfigurePluginsIfNeeded()
    {
        foreach (string path in s_PluginPaths)
        {
            var importer = AssetImporter.GetAtPath(path) as PluginImporter;
            if (importer == null) continue;

            // Reconfigure if Editor is enabled OR isPreloaded is true (both are wrong)
            if (importer.GetCompatibleWithEditor() || importer.isPreloaded)
            {
                Debug.Log($"[NativePluginConfigurator] Auto-fixing plugin settings for {path}");
                ConfigurePlugins();
                return;
            }
        }
    }
}
