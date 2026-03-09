// A2GPlugin.cpp
// Audio-to-Gesture Plugin — standalone audio-energy driven body gesture engine
//
// FR-A2G-01: PCM audio (16 kHz mono float) → 13 body bone delta quaternions
//
// DESIGN:
//   audio2x.dll contains NO body/gesture APIs (confirmed by export table scan).
//   This plugin is therefore fully self-contained.
//
//   Algorithm:
//     1. Buffer incoming 16-kHz PCM audio.
//     2. At each output frame boundary (e.g. 30fps), analyse the PCM window:
//          - RMS energy   → upper-body sway amplitude
//          - Onset energy → head nod impulse
//          - Phase clock  → oscillatory arm swing (natural looking)
//     3. Map each signal through first-order low-pass filters to smooth motion.
//     4. Emit 13 XYZW delta quaternions (delta from neutral A-pose).
//
//   Bone layout (must match Audio2GestureController.cs A2GBones[]):
//     0  Spine          1  Chest           2  UpperChest
//     3  Neck            4  Head
//     5  LeftShoulder    6  LeftUpperArm    7  LeftLowerArm    8  LeftHand
//     9  RightShoulder  10  RightUpperArm  11  RightLowerArm  12  RightHand

#define A2GPLUGIN_EXPORTS
#include "A2GPlugin.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstring>
#include <deque>
#include <memory>
#include <mutex>
#include <string>
#include <vector>

// ───────────────────────────────────────────────────────────────────────────
// Constants
// ───────────────────────────────────────────────────────────────────────────
static constexpr int   NUM_BONES      = 13;
static constexpr float SAMPLE_RATE_HZ = 16000.0f;
static constexpr float PI_F           = 3.14159265358979323846f;

// Maximum rotation angles (rads) — keeps gesture subtle for a VTuber
static constexpr float MAX_SWAY_RAD    = 5.0f  * PI_F / 180.0f;
static constexpr float MAX_NOD_RAD     = 8.0f  * PI_F / 180.0f;
static constexpr float MAX_RAISE_RAD   = 15.0f * PI_F / 180.0f;
static constexpr float MAX_SWING_RAD   = 10.0f * PI_F / 180.0f;

// ───────────────────────────────────────────────────────────────────────────
// Quaternion helpers
// ───────────────────────────────────────────────────────────────────────────
struct Quat { float x, y, z, w; };

static inline Quat identity_quat() noexcept { return {0.f, 0.f, 0.f, 1.f}; }

// Rotation of `radians` around (ax, ay, az) — vector need not be normalised.
static Quat axis_angle(float ax, float ay, float az, float radians) noexcept
{
    float len = std::sqrt(ax*ax + ay*ay + az*az);
    if (len < 1e-6f) return identity_quat();
    float s = std::sin(radians * 0.5f);
    float c = std::cos(radians * 0.5f);
    return { ax/len*s, ay/len*s, az/len*s, c };
}

// ───────────────────────────────────────────────────────────────────────────
// Audio analysis helpers
// ───────────────────────────────────────────────────────────────────────────
static float compute_rms(const float* s, int n) noexcept
{
    if (n <= 0) return 0.f;
    double acc = 0.0;
    for (int i = 0; i < n; ++i) acc += static_cast<double>(s[i]) * s[i];
    return std::sqrt(static_cast<float>(acc / n));
}

// Alpha coefficient for a first-order IIR low-pass filter:
//   tau = desired time constant in seconds, dt = frame duration in seconds
static inline float iir_alpha(float dt, float tau) noexcept
{
    return 1.f - std::exp(-dt / tau);
}

// ───────────────────────────────────────────────────────────────────────────
// Gesture context
// ───────────────────────────────────────────────────────────────────────────
struct A2GContext
{
    // Config (immutable after construction)
    float frame_dur_s;      // seconds per output frame
    int   samples_per_frame;

    // PCM buffer
    std::vector<float> audio_buf;
    bool               audio_closed{false};

    // Motion state (low-pass filtered driving signals)
    float body_sway{0.f};   // forward body lean from energy
    float head_nod{0.f};    // onset-triggered head nod
    float arm_raise{0.f};   // amplitude-driven arm raise
    float phase{0.f};       // oscillation phase (radians)
    float prev_rms{0.f};

    // Output queue — each entry is NUM_BONES Quats
    std::deque<std::vector<Quat>> frame_queue;
    long long ts_us{0};     // microseconds timestamp counter

    std::string last_error;
    mutable std::mutex mtx;

    explicit A2GContext(int fps_num, int fps_den)
    {
        float fps = (fps_den > 0) ? static_cast<float>(fps_num) / fps_den : 30.f;
        frame_dur_s      = 1.f / fps;
        samples_per_frame = static_cast<int>(SAMPLE_RATE_HZ * frame_dur_s + 0.5f);
    }

    bool is_valid() const noexcept { return samples_per_frame > 0; }

    // ── Public thread-safe methods ────────────────────────────────────────

    void push_audio(const float* s, int n)
    {
        std::lock_guard<std::mutex> lk(mtx);
        audio_buf.insert(audio_buf.end(), s, s + n);
        _drain();
    }

    void close_audio()
    {
        std::lock_guard<std::mutex> lk(mtx);
        if (!audio_buf.empty()) {
            // Zero-pad partial final frame
            audio_buf.resize(samples_per_frame, 0.f);
            _drain();
        }
        audio_closed = true;
    }

    void reset()
    {
        std::lock_guard<std::mutex> lk(mtx);
        audio_buf.clear();
        frame_queue.clear();
        body_sway = head_nod = arm_raise = phase = prev_rms = 0.f;
        ts_us = 0;
        audio_closed = false;
        last_error.clear();
    }

    int has_frame() const
    {
        std::lock_guard<std::mutex> lk(mtx);
        return static_cast<int>(frame_queue.size());
    }

    // Pop one frame. Returns false if queue empty.
    bool pop_frame(std::vector<Quat>& out, long long& out_ts)
    {
        std::lock_guard<std::mutex> lk(mtx);
        if (frame_queue.empty()) return false;
        out    = std::move(frame_queue.front());
        out_ts = ts_us;
        frame_queue.pop_front();
        ts_us += static_cast<long long>(frame_dur_s * 1e6f);
        return true;
    }

private:
    // Process all complete frames currently in audio_buf (called under lock)
    void _drain()
    {
        while (static_cast<int>(audio_buf.size()) >= samples_per_frame) {
            _process_frame(audio_buf.data(), samples_per_frame);
            audio_buf.erase(audio_buf.begin(),
                            audio_buf.begin() + samples_per_frame);
        }
    }

    // Build one output frame from `n` PCM samples (n == samples_per_frame)
    void _process_frame(const float* s, int n)
    {
        const float dt  = frame_dur_s;
        const float rms = compute_rms(s, n);

        // Onset detector: positive derivative of RMS
        float onset   = std::max(0.f, rms - prev_rms);
        prev_rms      = rms;

        // ── Update driving signals via first-order IIR ──────────────────
        // body_sway: slow 500ms TC, proportional to RMS
        body_sway += iir_alpha(dt, 0.5f)  * (rms * 0.4f  - body_sway);
        // head_nod: fast 80ms TC, driven by audio onsets
        head_nod  += iir_alpha(dt, 0.08f) * (onset * 2.5f - head_nod);
        // arm_raise: medium 250ms TC, proportional to RMS
        arm_raise += iir_alpha(dt, 0.25f) * (rms * 0.6f  - arm_raise);

        // ── Oscillation clock ───────────────────────────────────────────
        // Frequency: ~1.5 Hz baseline + slight tempo-tracking from energy
        float osc_hz = 1.5f + rms * 0.5f;
        phase += 2.f * PI_F * osc_hz * dt;
        float swing = std::sin(phase) * arm_raise;

        // ── Clamp to angle limits ───────────────────────────────────────
        auto clamp_f = [](float v, float lo, float hi) {
            return v < lo ? lo : v > hi ? hi : v;
        };
        float sway  = clamp_f(body_sway, 0.f,        MAX_SWAY_RAD);
        float nod   = clamp_f(head_nod,  0.f,        MAX_NOD_RAD);
        float raise = clamp_f(arm_raise, 0.f,        MAX_RAISE_RAD);
        float sw    = clamp_f(swing,    -MAX_SWING_RAD, MAX_SWING_RAD);

        // ── Build 13 bone quaternions ───────────────────────────────────
        // All rotations are expressed as delta from neutral A-pose.
        // Coordinate convention: Unity left-hand, Y-up, Z-forward.
        //   X-axis rotation = nod/pitch
        //   Y-axis rotation = yaw/turn
        //   Z-axis rotation = roll/lean
        std::vector<Quat> frame(NUM_BONES);

        // 0 Spine: subtle forward lean from energy
        frame[0]  = axis_angle(1, 0, 0,  sway * 0.40f);
        // 1 Chest: slight Z-roll following arm swing
        frame[1]  = axis_angle(0, 0, 1,  sw   * 0.20f);
        // 2 UpperChest: counter-roll to keep upper body natural
        frame[2]  = axis_angle(0, 0, 1, -sw   * 0.10f);
        // 3 Neck: share portion of head nod
        frame[3]  = axis_angle(1, 0, 0,  nod  * 0.40f);
        // 4 Head: larger nod share + tiny opposing sway
        frame[4]  = axis_angle(1, 0, 0,  nod  * 0.60f);
        // 5 LeftShoulder: raised slightly when arm_raise is high (Z rotation = raises arm)
        frame[5]  = axis_angle(0, 0, 1,  raise * 0.30f);
        // 6 LeftUpperArm: swings forward on beat
        frame[6]  = axis_angle(0, 1, 0,  sw    * 0.60f);
        // 7 LeftLowerArm: gentle elbow bend following upper arm magnitude
        frame[7]  = axis_angle(0, 0, 1,  std::abs(sw) * 0.30f);
        // 8 LeftHand: near identity (wrist relaxed)
        frame[8]  = identity_quat();
        // 9 RightShoulder: mirror of left
        frame[9]  = axis_angle(0, 0, -1, raise * 0.30f);
        // 10 RightUpperArm: anti-phase swing (opposite to left arm → natural walk)
        frame[10] = axis_angle(0, 1, 0, -sw   * 0.60f);
        // 11 RightLowerArm: matching elbow bend
        frame[11] = axis_angle(0, 0, -1, std::abs(sw) * 0.30f);
        // 12 RightHand: near identity
        frame[12] = identity_quat();

        frame_queue.push_back(std::move(frame));
    }
};

// ═══════════════════════════════════════════════════════════════════════════
// Public C API (extern "C" __declspec(dllexport))
// ═══════════════════════════════════════════════════════════════════════════
extern "C" {

A2G_API const char* A2GPlugin_GetVersion()
{
    return "1.0.0";
}

A2G_API void* A2GPlugin_Create(
    const char* /*modelJsonPath*/,
    int         /*useGpuSolver*/,
    int         frameRateNum,
    int         frameRateDen)
{
    try {
        return new A2GContext(frameRateNum, frameRateDen);
    } catch (...) {
        return nullptr;
    }
}

A2G_API void A2GPlugin_Destroy(void* handle)
{
    delete static_cast<A2GContext*>(handle);
}

A2G_API const char* A2GPlugin_GetLastError(void* handle)
{
    if (!handle) return "null handle";
    return static_cast<A2GContext*>(handle)->last_error.c_str();
}

A2G_API int A2GPlugin_IsValid(void* handle)
{
    if (!handle) return 0;
    return static_cast<A2GContext*>(handle)->is_valid() ? 1 : 0;
}

A2G_API int A2GPlugin_PushAudio(void* handle, const float* samples, int count)
{
    if (!handle || !samples || count <= 0) return -1;
    try {
        static_cast<A2GContext*>(handle)->push_audio(samples, count);
        return 0;
    } catch (...) {
        return -2;
    }
}

A2G_API int A2GPlugin_CloseAudio(void* handle)
{
    if (!handle) return -1;
    try {
        static_cast<A2GContext*>(handle)->close_audio();
        return 0;
    } catch (...) {
        return -2;
    }
}

A2G_API int A2GPlugin_Reset(void* handle)
{
    if (!handle) return -1;
    try {
        static_cast<A2GContext*>(handle)->reset();
        return 0;
    } catch (...) {
        return -2;
    }
}

A2G_API int A2GPlugin_HasFrameReady(void* handle)
{
    if (!handle) return 0;
    return static_cast<A2GContext*>(handle)->has_frame();
}

A2G_API int A2GPlugin_ProcessFrame(void* handle)
{
    // Frames are computed eagerly inside PushAudio / CloseAudio.
    // This entry point is kept for API compatibility and returns queue depth.
    if (!handle) return -1;
    return static_cast<A2GContext*>(handle)->has_frame();
}

A2G_API int A2GPlugin_GetBoneCount(void* /*handle*/)
{
    return NUM_BONES;
}

A2G_API int A2GPlugin_GetLatestBoneRotations(
    void*      handle,
    float*     outQuaternions,
    int        maxBones,
    long long* tsUs)
{
    if (!handle || !outQuaternions || maxBones <= 0) return -1;

    auto* ctx = static_cast<A2GContext*>(handle);
    std::vector<Quat> frame;
    long long ts = 0;
    if (!ctx->pop_frame(frame, ts)) return 0;

    if (tsUs) *tsUs = ts;

    int written = static_cast<int>(std::min(
        static_cast<size_t>(maxBones), frame.size()));

    for (int i = 0; i < written; ++i) {
        outQuaternions[i*4 + 0] = frame[i].x;
        outQuaternions[i*4 + 1] = frame[i].y;
        outQuaternions[i*4 + 2] = frame[i].z;
        outQuaternions[i*4 + 3] = frame[i].w;
    }
    return written;
}

} // extern "C"
