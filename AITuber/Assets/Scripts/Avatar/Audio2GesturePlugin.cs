// Audio2GesturePlugin.cs
// P/Invoke wrapper for A2GPlugin.dll (NVIDIA Audio2Gesture Unity Native Plugin).
// Mirrors the A2FPlugin architecture for consistent integration.
//
// Setup:
//   1. Download NVIDIA Audio2Gesture SDK from developer.nvidia.com/audio2gesture
//   2. Place A2GPlugin.dll in Assets/Plugins/x86_64/ alongside A2FPlugin.dll
//   3. Audio2GestureController will automatically detect and use the plugin.
//
// Output: Per-frame upper-body bone rotations (quaternions) for 13 humanoid joints.
//
// SRS refs: FR-GESTURE-AUTO-01

using System;
using System.Runtime.InteropServices;
using UnityEngine;

namespace AITuber.Avatar
{
    /// <summary>
    /// Low-level P/Invoke bindings for A2GPlugin.dll.
    /// Falls back gracefully when the DLL is absent (IsAvailable = false).
    /// All methods are thread-safe on the C++ side.
    /// </summary>
    internal static class Audio2GesturePlugin
    {
        private const string DllName = "A2GPlugin";

        // A2GNativeLoader explicitly loads A2GPlugin.dll via LoadLibraryW before
        // the first P/Invoke fires, ensuring the module is in-process.
        // Matches the A2FNativeLoader pattern in Audio2FacePlugin.
        static Audio2GesturePlugin()
        {
            A2GNativeLoader.ForceInit();
        }

        // ── DLL availability check ───────────────────────────────────

        private static bool? _available;

        /// <summary>True when A2GPlugin.dll is present and loadable.</summary>
        internal static bool IsAvailable
        {
            get
            {
                if (_available.HasValue) return _available.Value;
                _available = TryLoad();
                return _available.Value;
            }
        }

        private static bool TryLoad()
        {
            // Use A2GNativeLoader's DllLoaded flag (set by explicit LoadLibraryW at SubsystemRegistration)
            // instead of a P/Invoke test call, which can trigger native SEH exceptions before
            // the managed catch block is established.
            bool loaded = A2GNativeLoader.DllLoaded;
            if (!loaded)
                Debug.Log("[A2GPlugin] A2GPlugin.dll not loaded — Audio2Gesture disabled.");
            return loaded;
        }

        // ── Versioning ───────────────────────────────────────────────

        /// <summary>Returns the plugin version string. Used for availability detection.</summary>
        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        [return: MarshalAs(UnmanagedType.LPStr)]
        internal static extern string A2GPlugin_GetVersion();

        // ── Lifecycle ────────────────────────────────────────────────

        /// <summary>
        /// Create a plugin handle.
        /// </summary>
        /// <param name="modelJsonPath">Absolute path to A2G model.json.</param>
        /// <param name="useGpuSolver">1 = GPU inference (recommended), 0 = CPU.</param>
        /// <param name="frameRateNum">Target output frame rate numerator (e.g. 30).</param>
        /// <param name="frameRateDen">Target output frame rate denominator (e.g. 1).</param>
        /// <returns>Opaque handle, or IntPtr.Zero on catastrophic failure.</returns>
        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        internal static extern IntPtr A2GPlugin_Create(
            [MarshalAs(UnmanagedType.LPStr)] string modelJsonPath,
            int useGpuSolver,
            int frameRateNum,
            int frameRateDen);

        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        internal static extern void A2GPlugin_Destroy(IntPtr handle);

        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        [return: MarshalAs(UnmanagedType.LPStr)]
        internal static extern string A2GPlugin_GetLastError(IntPtr handle);

        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        internal static extern int A2GPlugin_IsValid(IntPtr handle);

        // ── Audio input ──────────────────────────────────────────────

        /// <summary>Push mono 16 kHz float32 PCM samples.</summary>
        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        internal static extern int A2GPlugin_PushAudio(
            IntPtr handle,
            [In] float[] samples,
            int count);

        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        internal static extern int A2GPlugin_CloseAudio(IntPtr handle);

        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        internal static extern int A2GPlugin_Reset(IntPtr handle);

        // ── Processing ───────────────────────────────────────────────

        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        internal static extern int A2GPlugin_HasFrameReady(IntPtr handle);

        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        internal static extern int A2GPlugin_ProcessFrame(IntPtr handle);

        // ── Results ──────────────────────────────────────────────────

        /// <summary>Number of upper-body bones output by the model (typically 13).</summary>
        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        internal static extern int A2GPlugin_GetBoneCount(IntPtr handle);

        /// <summary>
        /// Copy the latest bone rotations (quaternions) into outQuaternions.
        /// Layout: [bone0.x, bone0.y, bone0.z, bone0.w, bone1.x, ...] (XYZW order).
        /// Rotations are delta quaternions relative to the neutral A-pose.
        /// </summary>
        /// <returns>Number of bones written; 0 if no new frame; negative on error.</returns>
        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        internal static extern int A2GPlugin_GetLatestBoneRotations(
            IntPtr handle,
            [Out] float[] outQuaternions,
            int maxBones,
            out long outTimestampUs);
    }
}
