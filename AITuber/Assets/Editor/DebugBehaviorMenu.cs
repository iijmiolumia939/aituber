// Temporary Editor menu to trigger behaviors during Play mode for MCP testing.
// Safe to delete after testing.
#if UNITY_EDITOR
using UnityEditor;
using UnityEngine;

namespace AITuber.Editor
{
    public static class DebugBehaviorMenu
    {
        [MenuItem("Debug/Behavior/go_eat")]
        static void GoEat() => Trigger("go_eat");

        [MenuItem("Debug/Behavior/go_stream")]
        static void GoStream() => Trigger("go_stream");

        [MenuItem("Debug/Behavior/go_sleep")]
        static void GoSleep() => Trigger("go_sleep");

        [MenuItem("Debug/Behavior/go_read")]
        static void GoRead() => Trigger("go_read");

        [MenuItem("Debug/Behavior/go_walk")]
        static void GoWalk() => Trigger("go_walk");

        static void Trigger(string behavior)
        {
            if (!Application.isPlaying)
            {
                Debug.LogWarning($"[DebugMenu] Not in play mode — cannot trigger '{behavior}'.");
                return;
            }
            var instance = Behavior.BehaviorSequenceRunner.Instance;
            if (instance == null)
            {
                Debug.LogError($"[DebugMenu] BehaviorSequenceRunner.Instance is null — cannot trigger '{behavior}'.");
                return;
            }
            Debug.Log($"[DebugMenu] Triggering '{behavior}'...");
            instance.StartBehavior(behavior);
        }
    }
}
#endif
