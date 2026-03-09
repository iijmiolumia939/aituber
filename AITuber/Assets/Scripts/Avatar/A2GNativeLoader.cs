// A2GNativeLoader.cs
// Ensures A2GPlugin.dll is loaded into the process before the first P/Invoke
// into Audio2GesturePlugin fires.  Mirrors the A2FNativeLoader pattern.
//
// Why this is needed:
//   On some Windows configurations the Unity Editor's DLL search path does not
//   include Assets/Plugins/x86_64/ early enough for the first P/Invoke cold call.
//   Explicit LoadLibraryW by full path guarantees the module is in-process before
//   any DllImport resolves it, eliminating DllNotFoundException.
//   A2GPlugin.dll is TRT-free (RMS/IIR energy algorithm) — safe in both Editor and Standalone.
//
// SRS refs: FR-GESTURE-AUTO-01

using System;
using System.IO;
using System.Runtime.InteropServices;
using UnityEngine;

namespace AITuber.Avatar
{
    internal static class A2GNativeLoader
    {
        // ── Win32 API ────────────────────────────────────────────────

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern IntPtr LoadLibraryW(string lpFileName);

        // ── State ────────────────────────────────────────────────────

        private static bool s_initialized;

        /// <summary>True if A2GPlugin.dll was successfully loaded via LoadLibraryW.</summary>
        internal static bool DllLoaded { get; private set; }

        // ── Entry points ─────────────────────────────────────────────

        /// <summary>
        /// Called by Audio2GesturePlugin's static constructor as belt-and-suspenders.
        /// No-op after first call.
        /// </summary>
        internal static void ForceInit()
        {
            if (s_initialized) return;
            PreloadNativeDependencies();
        }

        /// <summary>
        /// SubsystemRegistration fires before BeforeSceneLoad and before any
        /// MonoBehaviour Awake/OnEnable — the earliest safe place to preload DLLs.
        /// </summary>
        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        private static void PreloadNativeDependencies()
        {
            s_initialized = true;

            // Load A2GPlugin.dll explicitly so Mono P/Invoke resolves the existing
            // module handle rather than calling LoadLibrary cold.
            // Application.dataPath = {project}/Assets at runtime.
            string dllPath = Path.Combine(
                Application.dataPath, "Plugins", "x86_64", "A2GPlugin.dll");

            if (!File.Exists(dllPath))
            {
                Debug.LogWarning($"[A2GLoader] A2GPlugin.dll not found at '{dllPath}'. "
                               + "Ensure A2GPlugin.dll is in Assets/Plugins/x86_64/. "
                               + "Rebuild from native/A2GPlugin/ if missing.");
                return;
            }

            IntPtr handle = LoadLibraryW(dllPath);
            if (handle == IntPtr.Zero)
            {
                int err = Marshal.GetLastWin32Error();
                Debug.LogWarning($"[A2GLoader] LoadLibraryW FAILED for A2GPlugin.dll. "
                               + $"Win32Error={err}  path='{dllPath}'");
            }
            else
            {
                DllLoaded = true;
                Debug.Log($"[A2GLoader] Loaded 'A2GPlugin.dll'  ({dllPath})");
            }
        }
    }
}
