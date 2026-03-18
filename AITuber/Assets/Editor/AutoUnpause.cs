using UnityEditor;
using UnityEngine;

/// <summary>
/// Prevents Error Pause from freezing the game loop during Play mode.
/// Intercepts error logs and immediately schedules an unpause via delayCall.
/// </summary>
[InitializeOnLoad]
public static class AutoUnpause
{
    static AutoUnpause()
    {
        Application.logMessageReceived += OnLogMessage;
        EditorApplication.pauseStateChanged += OnPauseStateChanged;
    }

    private static void OnLogMessage(string condition, string stacktrace, LogType type)
    {
        if (type == LogType.Error || type == LogType.Exception)
        {
            if (EditorApplication.isPlaying)
            {
                // Schedule unpause for the next editor tick.
                // This fires after Error Pause processes the log.
                EditorApplication.delayCall += Unpause;
            }
        }
    }

    private static void OnPauseStateChanged(PauseState state)
    {
        if (state == PauseState.Paused && EditorApplication.isPlaying)
            EditorApplication.delayCall += Unpause;
    }

    private static void Unpause()
    {
        if (EditorApplication.isPlaying && EditorApplication.isPaused)
            EditorApplication.isPaused = false;
    }
}
