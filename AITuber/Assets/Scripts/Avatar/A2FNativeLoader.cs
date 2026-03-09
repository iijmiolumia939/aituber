// A2FNativeLoader.cs
// Ensures CUDA and TensorRT native DLLs are loaded into the process
// before the first P/Invoke into A2FPlugin.dll fires.
//
// Why this is needed:
//   A2FPlugin.dll → audio2x.dll → nvinfer_10.dll / cudart64_12.dll etc.
//   When Unity.exe is launched from the desktop (not a configured terminal),
//   TensorRT/CUDA directories may not be in the process PATH, which causes
//   LoadLibrary to fail when Unity resolves A2FPlugin's import table.
//
// Fix: RuntimeInitializeOnLoadMethod(SubsystemRegistration) is the earliest
//   C# callback in Unity's startup sequence.  We call LoadLibraryW() here
//   by full path so Windows caches the handles before any P/Invoke runs.
//
// SRS refs: FR-LIPSYNC-01

using System;
using System.IO;
using System.Runtime.InteropServices;
using UnityEngine;

namespace AITuber.Avatar
{
    internal static class A2FNativeLoader
    {
        // ── Win32 API ────────────────────────────────────────────────

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern IntPtr LoadLibraryW(string lpFileName);

        // ── Known install paths ──────────────────────────────────────

        private static readonly string[] s_CudaDirs =
        {
            @"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.9\bin",
            @"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.8\bin",
            @"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.6\bin",
            @"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.2\bin",
        };

        private static readonly string[] s_TrtDirs =
        {
            @"C:\TensorRT-10.13.0.35\lib",
            @"C:\TensorRT-10.12.0.35\lib",
            @"C:\TensorRT-10.0.0.6\lib",
        };

        // Load order matters: CUDA first, then TRT (which depends on CUDA)
        private static readonly (string dll, string[] dirs)[] s_LoadOrder =
        {
            ("cudart64_12.dll",       s_CudaDirs),
            ("cublas64_12.dll",       s_CudaDirs),
            ("curand64_10.dll",       s_CudaDirs),
            ("nvinfer_10.dll",        s_TrtDirs),
            ("nvinfer_plugin_10.dll", s_TrtDirs),
        };

        // ── Entry point ──────────────────────────────────────────────

        /// <summary>
        /// Called by Audio2FacePlugin's static constructor as a fallback,
        /// in case RuntimeInitializeOnLoadMethod hasn't fired yet.
        /// Safe to call multiple times (no-op after first call).
        /// </summary>
        internal static void ForceInit()
        {
            // The RuntimeInitializeOnLoadMethod will have already run during
            // Play Mode. This is a no-op in that case since the DLLs are
            // already loaded. Called here only as belt-and-suspenders.
            if (s_initialized) return;
            PreloadNativeDependencies();
        }

        private static bool s_initialized;

        /// <summary>
        /// SubsystemRegistration fires before BeforeSceneLoad and before any
        /// MonoBehaviour Awake/OnEnable, making it the safest place to
        /// pre-load transitive native dependencies.
        /// </summary>
        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        private static void PreloadNativeDependencies()
        {
            s_initialized = true;

            // Step 1: Update PATH so any additional transitive LoadLibrary calls succeed.
            AddDirsToPath(s_CudaDirs);
            AddDirsToPath(s_TrtDirs);

            // Step 2: Explicit LoadLibraryW by full path – the definitive fix.
            //         If a DLL is already in memory (already loaded), LoadLibraryW
            //         is a no-op (returns existing handle). Safe to call multiple times.
            int loaded = 0;
            int missing = 0;
            foreach (var (dll, dirs) in s_LoadOrder)
            {
                bool found = false;
                foreach (string dir in dirs)
                {
                    string fullPath = Path.Combine(dir, dll);
                    if (!File.Exists(fullPath)) continue;

                    IntPtr h = LoadLibraryW(fullPath);
                    if (h == IntPtr.Zero)
                    {
                        int err = Marshal.GetLastWin32Error();
                        Debug.LogWarning($"[A2FLoader] LoadLibraryW FAILED '{fullPath}'  Win32Error={err}");
                    }
                    else
                    {
                        Debug.Log($"[A2FLoader] Loaded '{dll}'  ({dir})");
                        loaded++;
                    }
                    found = true;
                    break;
                }
                if (!found)
                {
                    Debug.LogWarning($"[A2FLoader] '{dll}' not found in any known directory. "
                                   + "Install CUDA/TensorRT or add their paths to PATH.");
                    missing++;
                }
            }

            // Step 3: Pre-load audio2x.dll explicitly (it lives in Plugins/x86_64/).
            //         Application.dataPath is safe to call from RuntimeInitializeOnLoadMethod.
            string audio2xPath = Path.Combine(
                Application.dataPath, "Plugins", "x86_64", "audio2x.dll");
            if (File.Exists(audio2xPath))
            {
                IntPtr h = LoadLibraryW(audio2xPath);
                if (h == IntPtr.Zero)
                    Debug.LogWarning($"[A2FLoader] LoadLibraryW FAILED for audio2x.dll. Win32Error={Marshal.GetLastWin32Error()}");
                else
                {
                    Debug.Log($"[A2FLoader] Loaded 'audio2x.dll'  ({audio2xPath})");
                    loaded++;
                }
            }
            else
            {
                Debug.LogWarning($"[A2FLoader] audio2x.dll not found at '{audio2xPath}'. "
                               + "Copy it to Assets/Plugins/x86_64/.");
                missing++;
            }

            // Step 4: Pre-load A2FPlugin.dll itself so Mono P/Invoke resolves the
            //         existing module handle rather than calling LoadLibrary cold.
            string a2fPluginPath = Path.Combine(
                Application.dataPath, "Plugins", "x86_64", "A2FPlugin.dll");
            if (File.Exists(a2fPluginPath))
            {
                IntPtr ha = LoadLibraryW(a2fPluginPath);
                if (ha == IntPtr.Zero)
                    Debug.LogWarning($"[A2FLoader] LoadLibraryW FAILED for A2FPlugin.dll. Win32Error={Marshal.GetLastWin32Error()}");
                else
                {
                    Debug.Log($"[A2FLoader] Loaded 'A2FPlugin.dll'  ({a2fPluginPath})");
                    loaded++;
                }
            }
            else
            {
                Debug.LogWarning($"[A2FLoader] A2FPlugin.dll not found at '{a2fPluginPath}'.");
                missing++;
            }

            Debug.Log($"[A2FLoader] Pre-load complete: {loaded} loaded, {missing} missing.");
        }

        private static void AddDirsToPath(string[] dirs)
        {
            string current = Environment.GetEnvironmentVariable("PATH") ?? "";
            bool changed = false;
            foreach (string dir in dirs)
            {
                if (Directory.Exists(dir) &&
                    current.IndexOf(dir, StringComparison.OrdinalIgnoreCase) < 0)
                {
                    current += ";" + dir;
                    changed = true;
                }
            }
            if (changed)
                Environment.SetEnvironmentVariable("PATH", current);
        }
    }
}
