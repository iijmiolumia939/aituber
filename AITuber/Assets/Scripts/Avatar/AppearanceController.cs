// AppearanceController.cs
// Runtime appearance manager: shader mode, costume preset, hairstyle preset.
// Receives commands from AvatarController.HandleAppearanceUpdate().
//
// SRS refs: FR-SHADER-02, FR-APPEARANCE-01, FR-APPEARANCE-02

using System.Collections.Generic;
using UnityEngine;

namespace AITuber.Avatar
{
    /// <summary>
    /// Runtime shader modes available via WS appearance_update command.
    /// FR-SHADER-02
    /// </summary>
    public enum ShaderMode
    {
        /// <summary>AITuber/CyberpunkToon — トゥーンシェーダー</summary>
        Toon,
        /// <summary>Universal Render Pipeline/Lit — PBR リアル</summary>
        Lit,
        /// <summary>Silent's Cel Shading/Lightramp (Outline) — SCSS セルシェーダー (FR-SHADER-02)</summary>
        Scss,
    }

    /// <summary>
    /// Singleton MonoBehaviour that manages the VRM avatar's visual appearance at runtime.
    /// Attach to the same GameObject as AvatarController.
    ///
    /// Features:
    ///  - ApplyShaderMode: hot-swap between Toon / Lit shaders (FR-SHADER-02)
    ///  - ApplyCostume  : activate a named CostumeDefinition preset (FR-APPEARANCE-01)
    ///  - ApplyHair     : activate a named HairstyleDefinition preset (FR-APPEARANCE-02)
    /// </summary>
    public class AppearanceController : MonoBehaviour
    {
        // ── Singleton ──────────────────────────────────────────────────────
        public static AppearanceController Instance { get; private set; }

        // ── Inspector ──────────────────────────────────────────────────────
        [Header("Shader Settings  (FR-SHADER-02)")]
        [SerializeField] private string _toonShaderName = "AITuber/CyberpunkToon";
        [SerializeField] private string _litShaderName  = "Universal Render Pipeline/Lit";
        [Tooltip("Silent's Cel Shading Shader のバリアント名。\n"
               + "Lightramp / Lightramp (Outline) / Crosstone / Crosstone (Outline) から選択。")]
        [SerializeField] private string _scssShaderName = "Silent's Cel Shading/Lightramp (Outline)";

        [Tooltip("管理対象レンダラー。空の場合は Awake で GetComponentsInChildren<Renderer>() を使用。")]
        [SerializeField] private Renderer[] _targetRenderers;

        [Header("Costume Presets  (FR-APPEARANCE-01)")]
        [SerializeField] private CostumeDefinition[] _costumes;

        [Header("Hairstyle Presets  (FR-APPEARANCE-02)")]
        [SerializeField] private HairstyleDefinition[] _hairstyles;

        // ── State ──────────────────────────────────────────────────────────
        private ShaderMode _currentMode    = ShaderMode.Toon;
        private string     _currentCostume = "";
        private string     _currentHair    = "";

        // Shader cache so Shader.Find is only called once per mode
        private readonly Dictionary<ShaderMode, Shader> _shaderCache = new();

        // ── Lifecycle ──────────────────────────────────────────────────────

        private void Awake()
        {
            if (Instance != null && Instance != this)
            {
                Destroy(this);
                return;
            }
            Instance = this;

            // Auto-discover renderers if not wired
            if (_targetRenderers == null || _targetRenderers.Length == 0)
                _targetRenderers = GetComponentsInChildren<Renderer>(true);
        }

        private void OnDestroy()
        {
            if (Instance == this) Instance = null;
        }

        // ── Public API ─────────────────────────────────────────────────────

        /// <summary>
        /// Hot-swaps the shader on all managed renderers.
        /// FR-SHADER-02: shader_mode "toon" | "lit"
        /// </summary>
        public void ApplyShaderMode(ShaderMode mode)
        {
            if (mode == _currentMode) return;

            var shader = GetOrFindShader(mode);
            if (shader == null) return;

            foreach (var rend in _targetRenderers)
            {
                if (rend == null) continue;
                // Use sharedMaterials to avoid per-instance material creation
                var mats = rend.sharedMaterials;
                for (int i = 0; i < mats.Length; i++)
                    if (mats[i] != null) mats[i].shader = shader;
                rend.sharedMaterials = mats;
            }

            _currentMode = mode;
            Debug.Log($"[AppearanceCtrl] ShaderMode → {mode}  (FR-SHADER-02)");
        }

        /// <summary>
        /// Activates a costume preset by ID.
        /// FR-APPEARANCE-01: costume field in appearance_update
        /// </summary>
        public void ApplyCostume(string costumeId)
        {
            if (string.IsNullOrEmpty(costumeId) || costumeId == _currentCostume) return;
            if (_costumes == null) return;

            foreach (var def in _costumes)
            {
                if (def == null || def.costumeId != costumeId) continue;
                def.Apply(_targetRenderers);
                _currentCostume = costumeId;
                Debug.Log($"[AppearanceCtrl] Costume → {costumeId}  (FR-APPEARANCE-01)");
                return;
            }
            Debug.LogWarning($"[AppearanceCtrl] Costume preset not found: '{costumeId}'");
        }

        /// <summary>
        /// Activates a hairstyle preset by ID.
        /// FR-APPEARANCE-02: hair field in appearance_update
        /// </summary>
        public void ApplyHair(string hairId)
        {
            if (string.IsNullOrEmpty(hairId) || hairId == _currentHair) return;
            if (_hairstyles == null) return;

            foreach (var def in _hairstyles)
            {
                if (def == null || def.hairId != hairId) continue;
                def.Apply(_targetRenderers);
                _currentHair = hairId;
                Debug.Log($"[AppearanceCtrl] Hair → {hairId}  (FR-APPEARANCE-02)");
                return;
            }
            Debug.LogWarning($"[AppearanceCtrl] Hair preset not found: '{hairId}'");
        }

        // ── Accessors ──────────────────────────────────────────────────────

        public ShaderMode CurrentMode    => _currentMode;
        public string     CurrentCostume => _currentCostume;
        public string     CurrentHair    => _currentHair;

        // ── Internal ───────────────────────────────────────────────────────

        private Shader GetOrFindShader(ShaderMode mode)
        {
            if (_shaderCache.TryGetValue(mode, out var cached)) return cached;

            string name = mode switch
            {
                ShaderMode.Toon => _toonShaderName,
                ShaderMode.Lit  => _litShaderName,
                ShaderMode.Scss => _scssShaderName,
                _               => _litShaderName,
            };
            var shader = Shader.Find(name);
            if (shader == null)
                Debug.LogWarning($"[AppearanceCtrl] Shader not found: '{name}'. SCSS の場合は Assets へ unitypackage をインポートしてください。");
            else
                _shaderCache[mode] = shader;
            return shader;
        }
    }
}
