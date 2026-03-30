// TransparentBackgroundController.cs
// Switches the main camera between room-view and transparent (chroma-key green)
// background modes for OBS capture. FR-BCAST-BG-01
//
// Usage:
//   Attach to the same GameObject as RoomManager.
//   Orchestrator sends: { "cmd": "set_background_mode", "params": { "mode": "transparent" } }
//   Modes: "room" (default) — show 3D room environment
//          "transparent"    — green chroma-key background, rooms hidden
//
// OBS should have a Color Key filter on the Avatar source to key out #00FF00.

using UnityEngine;

namespace AITuber.Room
{
    /// <summary>
    /// Controls whether the camera renders the 3D room or a solid chroma-key
    /// green background for overlay-based streaming. FR-BCAST-BG-01
    /// </summary>
    public class TransparentBackgroundController : MonoBehaviour
    {
        [Header("References")]
        [SerializeField] private Camera _mainCamera;

        [Header("Chroma Key")]
        [Tooltip("Background color when in transparent mode (OBS Color Key target)")]
        [SerializeField] private Color _chromaKeyColor = new Color(0f, 1f, 0f, 1f); // #00FF00

        // ── State ────────────────────────────────────────────────────

        private bool _isTransparent;
        private CameraClearFlags _originalClearFlags;
        private Color _originalBackgroundColor;
        private bool _initialized;

        // ── Singleton ────────────────────────────────────────────────

        public static TransparentBackgroundController Instance { get; private set; }

        public static void ClearInstanceForTest() => Instance = null;

        // ── Properties ───────────────────────────────────────────────

        /// <summary>True when camera is in chroma-key transparent mode.</summary>
        public bool IsTransparent => _isTransparent;

        // ── Unity Lifecycle ──────────────────────────────────────────

        private void Awake()
        {
            if (Instance != null && Instance != this)
            {
                Destroy(this);
                return;
            }
            Instance = this;
        }

        private void Start()
        {
            if (_mainCamera == null)
                _mainCamera = Camera.main;

            if (_mainCamera != null)
            {
                _originalClearFlags = _mainCamera.clearFlags;
                _originalBackgroundColor = _mainCamera.backgroundColor;
                _initialized = true;
            }
            else
            {
                Debug.LogWarning("[TransparentBG] No main camera found.");
            }
        }

        private void OnDestroy()
        {
            if (Instance == this) Instance = null;
        }

        // ── Public API ───────────────────────────────────────────────

        /// <summary>
        /// Set background mode. FR-BCAST-BG-01
        /// </summary>
        /// <param name="mode">"transparent" for chroma-key, "room" for normal 3D room.</param>
        public void SetMode(string mode)
        {
            if (!_initialized || _mainCamera == null) return;

            bool wantTransparent = mode == "transparent";
            if (wantTransparent == _isTransparent) return;

            _isTransparent = wantTransparent;

            if (_isTransparent)
            {
                // Switch to chroma-key green background
                _mainCamera.clearFlags = CameraClearFlags.SolidColor;
                _mainCamera.backgroundColor = _chromaKeyColor;

                // Hide all room prefabs
                var rm = RoomManager.Instance;
                if (rm != null)
                    rm.SetRoomsVisible(false);

                Debug.Log("[TransparentBG] Switched to TRANSPARENT mode (chroma-key green)");
            }
            else
            {
                // Restore original camera settings
                _mainCamera.clearFlags = _originalClearFlags;
                _mainCamera.backgroundColor = _originalBackgroundColor;

                // Re-show the active room
                var rm = RoomManager.Instance;
                if (rm != null)
                    rm.SetRoomsVisible(true);

                Debug.Log("[TransparentBG] Switched to ROOM mode (3D environment)");
            }
        }
    }
}
