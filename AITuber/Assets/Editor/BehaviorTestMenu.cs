// Temporary debug menu — delete after testing is complete
using System.Linq;
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

        [MenuItem("AITuber/Test Behavior/Log go_stream Snapshot")]
        public static void LogGoStreamSnapshot()
        {
            if (!Application.isPlaying)
            {
                Debug.LogWarning("[BehaviorTest] Enter Play Mode first, then call AITuber/Test Behavior/Log go_stream Snapshot");
                return;
            }

            var avatarRoot = GameObject.Find("AvatarRoot");
            var camera = Camera.main;
            var runner = BehaviorSequenceRunner.Instance;
            var slot = avatarRoot != null ? InteractionSlot.FindNearest("sit_work", avatarRoot.transform.position) : null;

            string avatarText = avatarRoot != null
                ? $"AvatarRoot pos={avatarRoot.transform.position} rot={avatarRoot.transform.eulerAngles}"
                : "AvatarRoot missing";
            string cameraText = camera != null
                ? $"MainCamera pos={camera.transform.position} rot={camera.transform.eulerAngles} fov={camera.fieldOfView:F1}"
                : "MainCamera missing";
            string runnerText = runner != null
                ? $"BehaviorRunner busy={runner.IsBusy} running='{runner.RunningBehavior ?? ""}'"
                : "BehaviorRunner missing";
            string slotText = slot != null
                ? $"sit_work slot pos={slot.StandPosition} rot={slot.StandRotation.eulerAngles} obj='{slot.gameObject.name}'"
                : "sit_work slot missing";

            string supportText = "avatar support not found";
            if (avatarRoot != null)
            {
                var rayOrigin = avatarRoot.transform.position + Vector3.up * 0.25f;
                if (Physics.Raycast(rayOrigin, Vector3.down, out var hit, 1.0f, Physics.DefaultRaycastLayers, QueryTriggerInteraction.Ignore))
                    supportText = $"support hit='{hit.collider.name}' point={hit.point} dist={hit.distance:F3}";
            }

            string slotSupportText = "slot support not found";
            string nearbyColliderText = "nearbyColliders=[]";
            if (slot != null)
            {
                var slotRayOrigin = slot.StandPosition + Vector3.up * 0.25f;
                if (Physics.Raycast(slotRayOrigin, Vector3.down, out var slotHit, 0.75f, Physics.DefaultRaycastLayers, QueryTriggerInteraction.Ignore))
                {
                    slotSupportText = $"slotSupport hit='{slotHit.collider.name}' point={slotHit.point} drop={(slot.StandPosition.y - slotHit.point.y):F3}";
                }

                var nearbyColliders = Physics.OverlapSphere(slot.StandPosition, 0.35f, Physics.DefaultRaycastLayers, QueryTriggerInteraction.Ignore)
                    .Select(c => c.name)
                    .Distinct()
                    .OrderBy(name => name)
                    .ToArray();
                nearbyColliderText = nearbyColliders.Length > 0
                    ? $"nearbyColliders=[{string.Join(", ", nearbyColliders)}]"
                    : "nearbyColliders=[]";
            }

            Debug.Log($"[BehaviorTest] Snapshot | {runnerText} | {avatarText} | {cameraText} | {slotText} | {supportText} | {slotSupportText} | {nearbyColliderText}");
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
