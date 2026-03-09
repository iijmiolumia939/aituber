// Audio2FacePlugin.cs
// P/Invoke wrapper for A2FPlugin.dll (Unity Native Plugin).
// Provides raw access to the C-exported Audio2Face-3D SDK functions.
//
// SRS refs: FR-LIPSYNC-01, FR-LIPSYNC-02
// Namespace: AITuber.Avatar

using System;
using System.IO;
using System.Runtime.InteropServices;

namespace AITuber.Avatar
{
    /// <summary>
    /// Low-level P/Invoke bindings for A2FPlugin.dll.
    /// All methods are thread-safe on the C++ side (weights are mutex-guarded).
    /// Call A2FPlugin_Create() from the main thread only.
    /// </summary>
    internal static class Audio2FacePlugin
    {
        // Name of the native DLL placed in Assets/Plugins/x86_64/
        private const string DllName = "A2FPlugin";

        // A2FNativeLoader handles pre-loading of CUDA/TRT dependencies
        // via RuntimeInitializeOnLoadMethod(SubsystemRegistration).
        // This static constructor is a belt-and-suspenders backup for
        // cases where the class is first accessed outside Play Mode.
        static Audio2FacePlugin()
        {
            A2FNativeLoader.ForceInit();
        }

        // ── Lifecycle ────────────────────────────────────────────────

        /// <summary>
        /// Create a plugin handle.
        /// </summary>
        /// <param name="modelJsonPath">Absolute path to model.json (must be accessible at runtime).</param>
        /// <param name="useGpuSolver">1 = GPU blendshape solve, 0 = CPU.</param>
        /// <param name="frameRateNum">Target output frame rate numerator (e.g. 30).</param>
        /// <param name="frameRateDen">Target output frame rate denominator (e.g. 1).</param>
        /// <returns>Opaque handle, or IntPtr.Zero on catastrophic failure.
        /// Check <see cref="IsValid"/> after creation.</returns>
        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        internal static extern IntPtr A2FPlugin_Create(
            [MarshalAs(UnmanagedType.LPStr)] string modelJsonPath,
            int useGpuSolver,
            int frameRateNum,
            int frameRateDen);

        /// <summary>Destroy a handle created with <see cref="A2FPlugin_Create"/>.</summary>
        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        internal static extern void A2FPlugin_Destroy(IntPtr handle);

        /// <summary>Return the last C-side error string (valid until the next call on the same handle).</summary>
        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        [return: MarshalAs(UnmanagedType.LPStr)]
        internal static extern string A2FPlugin_GetLastError(IntPtr handle);

        /// <summary>Non-zero if the bundle was successfully created inside the handle.</summary>
        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        internal static extern int A2FPlugin_IsValid(IntPtr handle);

        // ── Audio input ──────────────────────────────────────────────

        /// <summary>
        /// Push mono 16 kHz float32 PCM samples (track 0).
        /// </summary>
        /// <returns>0 on success.</returns>
        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        internal static extern int A2FPlugin_PushAudio(
            IntPtr handle,
            [In] float[] samples,
            int count);

        /// <summary>Signal end-of-stream for this utterance.</summary>
        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        internal static extern int A2FPlugin_CloseAudio(IntPtr handle);

        /// <summary>Reset for the next utterance (resets audio + emotion accumulators and executor).</summary>
        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        internal static extern int A2FPlugin_Reset(IntPtr handle);

        // ── Processing ───────────────────────────────────────────────

        /// <summary>Number of tracks ready to execute (>0 means <see cref="A2FPlugin_ProcessFrame"/> is productive).</summary>
        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        internal static extern int A2FPlugin_HasFrameReady(IntPtr handle);

        /// <summary>Run one inference step; the results callback fires synchronously.</summary>
        /// <returns>0 on success.</returns>
        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        internal static extern int A2FPlugin_ProcessFrame(IntPtr handle);

        // ── Results ──────────────────────────────────────────────────

        /// <summary>Number of blendshape weights (typically 52 for ARKit).</summary>
        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        internal static extern int A2FPlugin_GetWeightCount(IntPtr handle);

        /// <summary>
        /// Copy the latest weights (track 0) into <paramref name="outWeights"/>.
        /// </summary>
        /// <param name="outTimestampUs">Frame timestamp in microseconds (may be null).</param>
        /// <returns>Number of weights written; 0 if no new frame; negative on error.</returns>
        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        internal static extern int A2FPlugin_GetLatestWeights(
            IntPtr handle,
            [Out] float[] outWeights,
            int maxCount,
            out long outTimestampUs);

        /// <summary>
        /// Drain all pending frames and return the most recent weights.
        /// Calls ProcessFrame in a loop internally.
        /// </summary>
        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        internal static extern int A2FPlugin_DrainAndGetLatestWeights(
            IntPtr handle,
            [Out] float[] outWeights,
            int maxCount,
            out long outTimestampUs);
    }
}
