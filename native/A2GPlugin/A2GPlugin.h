// A2GPlugin.h
// Public C API for the Audio-to-Gesture Unity plugin
// Standalone implementation: audio PCM in -> body bone quaternions out
// Does NOT depend on audio2x.dll (which is a face-only library)
#pragma once

#ifdef _WIN32
#  ifdef A2GPLUGIN_EXPORTS
#    define A2G_API extern "C" __declspec(dllexport)
#  else
#    define A2G_API extern "C" __declspec(dllimport)
#  endif
#else
#  define A2G_API extern "C"
#endif

// Returns version string, e.g. "1.0.0"
A2G_API const char* A2GPlugin_GetVersion();

// Create a new context.
//   modelJsonPath : reserved for future model loading; pass NULL for now
//   useGpuSolver  : reserved; pass 0
//   frameRateNum  : frame rate numerator   (e.g. 30)
//   frameRateDen  : frame rate denominator (e.g. 1)
// Returns non-NULL handle on success, NULL on failure.
A2G_API void* A2GPlugin_Create(
    const char* modelJsonPath,
    int         useGpuSolver,
    int         frameRateNum,
    int         frameRateDen);

// Destroy a context created by A2GPlugin_Create.
A2G_API void A2GPlugin_Destroy(void* handle);

// Returns last error message string, or empty string if no error.
A2G_API const char* A2GPlugin_GetLastError(void* handle);

// Returns 1 if the context is in a valid, usable state; 0 otherwise.
A2G_API int A2GPlugin_IsValid(void* handle);

// Push 16-kHz mono PCM float samples.
// Returns 0 on success, negative on error.
A2G_API int A2GPlugin_PushAudio(void* handle, const float* samples, int count);

// Signal end of audio stream (flushes partial frame).
// Returns 0 on success.
A2G_API int A2GPlugin_CloseAudio(void* handle);

// Reset the context to its initial empty state.
A2G_API int A2GPlugin_Reset(void* handle);

// Returns the number of output frames currently queued (>0 means frames available).
A2G_API int A2GPlugin_HasFrameReady(void* handle);

// No-op kept for API compatibility; frames are computed inside PushAudio/CloseAudio.
// Returns current queued frame count.
A2G_API int A2GPlugin_ProcessFrame(void* handle);

// Returns the number of bones this plugin outputs (always 13).
A2G_API int A2GPlugin_GetBoneCount(void* handle);

// Pop one frame and write bone rotations as XYZW quaternions into outQuaternions.
//   outQuaternions : float array of size maxBones*4
//   maxBones       : capacity of outQuaternions (must be >= 13)
//   tsUs           : [out] timestamp of the frame in microseconds
// Returns number of bones written (0 if no frame queued, negative on error).
A2G_API int A2GPlugin_GetLatestBoneRotations(
    void*      handle,
    float*     outQuaternions,
    int        maxBones,
    long long* tsUs);
