// Temporary build launcher — delete after use
using UnityEditor;
using UnityEngine;

public static class BuildLauncher
{
    [MenuItem("Tools/Build And Run Now")]
    public static void BuildAndRun()
    {
        var opts = new BuildPlayerOptions
        {
            scenes = new[] { "Assets/Scenes/SampleScene.unity" },
            locationPathName = "output/AITuber.exe",
            target = BuildTarget.StandaloneWindows64,
            options = BuildOptions.AutoRunPlayer
        };
        Debug.Log("[BuildLauncher] Starting Build and Run...");
        BuildPipeline.BuildPlayer(opts);
    }
}
