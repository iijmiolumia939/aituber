using UnityEditor;
using UnityEngine;

namespace AITuber.EditorTools
{
    [InitializeOnLoad]
    public static class PlayModeControl
    {
        private const string ProbeName = "__AITuberPlayModeProbe";

        static PlayModeControl()
        {
            EditorApplication.playModeStateChanged -= OnPlayModeStateChanged;
            EditorApplication.playModeStateChanged += OnPlayModeStateChanged;
        }

        [MenuItem("AITuber/PlayMode/Enter")]
        public static void EnterPlayMode()
        {
            if (EditorApplication.isPlaying)
            {
                Debug.Log("[PlayModeControl] Already in Play Mode.");
                EnsureProbeExists();
                return;
            }

            Debug.Log("[PlayModeControl] Entering Play Mode.");
            EditorApplication.isPlaying = true;
        }

        [MenuItem("AITuber/PlayMode/Exit")]
        public static void ExitPlayMode()
        {
            if (!EditorApplication.isPlaying)
            {
                Debug.Log("[PlayModeControl] Already in Edit Mode.");
                RemoveProbeIfExists();
                return;
            }

            Debug.Log("[PlayModeControl] Exiting Play Mode.");
            EditorApplication.isPlaying = false;
        }

        private static void OnPlayModeStateChanged(PlayModeStateChange state)
        {
            switch (state)
            {
                case PlayModeStateChange.EnteredPlayMode:
                    EnsureProbeExists();
                    Debug.Log("[PlayModeControl] Entered Play Mode.");
                    break;
                case PlayModeStateChange.ExitingPlayMode:
                case PlayModeStateChange.EnteredEditMode:
                    RemoveProbeIfExists();
                    break;
            }
        }

        private static void EnsureProbeExists()
        {
            if (Object.FindFirstObjectByType<PlayModeProbeMarker>() != null)
                return;

            var probe = new GameObject(ProbeName);
            probe.hideFlags = HideFlags.DontSave;
            probe.AddComponent<PlayModeProbeMarker>();
        }

        private static void RemoveProbeIfExists()
        {
            var marker = Object.FindFirstObjectByType<PlayModeProbeMarker>();
            if (marker != null)
                Object.DestroyImmediate(marker.gameObject);
        }

        private sealed class PlayModeProbeMarker : MonoBehaviour
        {
        }
    }
}