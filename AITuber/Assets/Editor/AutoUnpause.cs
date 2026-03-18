using UnityEditor;
using UnityEngine;

/// <summary>
/// Detects and logs Editor pause state during Play mode.
/// Auto-unpauses if Error Pause triggers during play to prevent frozen game loop.
/// </summary>
[InitializeOnLoad]
public static class AutoUnpause
{
    static AutoUnpause()
    {
        EditorApplication.pauseStateChanged += OnPauseStateChanged;
    }

    private static void OnPauseStateChanged(PauseState state)
    {
        if (state == PauseState.Paused && EditorApplication.isPlaying)
        {
            Debug.LogWarning("[AutoUnpause] Game paused during Play mode — auto-unpausing.");
            EditorApplication.isPaused = false;
        }
    }
}
