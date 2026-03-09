# A2GPlugin — Audio-to-Gesture Unity Native Plugin

Standalone C++ DLL that converts 16 kHz mono PCM audio into 13 body bone
delta-quaternions for use with Unity's Humanoid rigging system.

> **Note:** `audio2x.dll` contains **no body/gesture APIs** (it is a face
> animation + emotion library). `A2GPlugin.dll` is therefore self-contained
> and has **no runtime dependencies** other than the MSVC C++ runtime (which
> is statically linked via `/MT`).

---

## Algorithm summary

| Signal | Source | Target bones |
|--------|--------|--------------|
| RMS energy (500 ms IIR) | Overall audio loudness | Spine / Chest sway |
| Onset energy (80 ms IIR) | Amplitude jumps | Neck / Head nod |
| Amplitude (250 ms IIR) × sin(phase) | Beat oscillation | L/R Upper + Lower Arm swing |

All output quaternions are **delta rotations relative to neutral A-pose**.

---

## Prerequisites

| Tool | Version |
|------|---------|
| Visual Studio 2022 (or Build Tools) | 17.x |
| CMake | 3.20+ |
| Windows SDK | 10.0.x |

---

## Build (Release)

```powershell
# From the repo root
cd native\A2GPlugin

# Configure
cmake -B build -A x64 -DCMAKE_BUILD_TYPE=Release

# Build + auto-copy DLL to Assets/Plugins/x86_64/
cmake --build build --config Release
```

The post-build step copies `A2GPlugin.dll` to
`AITuber/Assets/Plugins/x86_64/A2GPlugin.dll` automatically.

---

## Build (Debug)

```powershell
cmake -B build -A x64
cmake --build build --config Debug
# Output: build\Debug\A2GPlugin.dll  (NOT auto-copied to Unity)
```

---

## Unity P/Invoke stub

`AITuber/Assets/Scripts/Avatar/Audio2GesturePlugin.cs`

The C# stub uses `[DllImport("A2GPlugin")]` which Unity resolves to
`Assets/Plugins/x86_64/A2GPlugin.dll` on Windows x64.

---

## Bone index map

Matches `Audio2GestureController.cs` `A2GBones[]`:

| Index | Unity HumanBodyBones |
|-------|---------------------|
| 0     | Spine               |
| 1     | Chest               |
| 2     | UpperChest          |
| 3     | Neck                |
| 4     | Head                |
| 5     | LeftShoulder        |
| 6     | LeftUpperArm        |
| 7     | LeftLowerArm        |
| 8     | LeftHand            |
| 9     | RightShoulder       |
| 10    | RightUpperArm       |
| 11    | RightLowerArm       |
| 12    | RightHand           |

---

## Future work

To replace the heuristic approach with a learned model, update
`A2GPlugin_Create` to load `modelJsonPath` and drive bone rotations from
inference outputs. The public C API is forward-compatible with
a neural backend.
