// Temporary debug menu — delete after testing is complete
using UnityEngine;
using UnityEditor;

namespace AITuber.Behavior
{
    public static class BehaviorTestMenu
    {
        [MenuItem("AITuber/Test Behavior/go_stream")]
        public static void TestGoStream() => Trigger("go_stream");

        [MenuItem("AITuber/Test Behavior/go_sleep")]
        public static void TestGoSleep() => Trigger("go_sleep");

        [MenuItem("AITuber/Test Behavior/go_eat")]
        public static void TestGoEat() => Trigger("go_eat");

        [MenuItem("AITuber/Test Behavior/Stop")]
        public static void StopBehavior() => BehaviorSequenceRunner.Instance?.StopBehavior();

        [MenuItem("AITuber/Test Behavior/Log AvatarRoot Position")]
        public static void LogAvatarRootPos()
        {
            var go = GameObject.Find("AvatarRoot");
            if (go == null) { Debug.LogError("[BehaviorTest] AvatarRoot not found."); return; }
            Debug.Log($"[BehaviorTest] AvatarRoot pos={go.transform.position} rot={go.transform.eulerAngles}");
        }

        private static void Trigger(string name)
        {
            if (!Application.isPlaying)
            {
                Debug.LogWarning($"[BehaviorTest] Enter Play Mode first, then call AITuber/Test Behavior/{name}");
                return;
            }
            if (BehaviorSequenceRunner.Instance == null)
            {
                Debug.LogError("[BehaviorTest] BehaviorSequenceRunner.Instance is null — check scene setup.");
                return;
            }
            Debug.Log($"[BehaviorTest] Triggering '{name}'");
            BehaviorSequenceRunner.Instance.StartBehavior(name);
        }
    }
}
