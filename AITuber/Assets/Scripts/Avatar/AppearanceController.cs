// AppearanceController.cs
// Runtime appearance manager: shader mode, costume preset, hairstyle preset.
// Receives commands from AvatarController.HandleAppearanceUpdate().
//
// SRS refs: FR-SHADER-02, FR-APPEARANCE-01, FR-APPEARANCE-02, FR-SHADER-TRANSITION-01

using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using AITuber.Rendering;

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
        /// <summary>Silent's Cel Shading/Lightramp (Outline) — SCSS セルシェーダー (Built-in RP のみ。URP ではピンクになるため非推奨)</summary>
        Scss,
        /// <summary>AITuber/RetroAvatarCRT — CRT スキャンライン / レトロ 2.5D</summary>
        Crt,
        /// <summary>AITuber/CrosshatchSketch — クロスハッチ鉛筆スケッチ</summary>
        Sketch,
        /// <summary>AITuber/WatercolorAvatar — 水彩</summary>
        Watercolor,
        /// <summary>AITuber/WireframeSolid — ワイヤーフレーム + ソリッド blend</summary>
        Wireframe,
        /// <summary>AITuber/MangaPanel — Unlit + 手描きハイライト / 漫画パネル</summary>
        Manga,
        /// <summary>AITuber/PixelArtAvatar — ドット絵スタイル (UV ブロック量子化 + パレット削減)</summary>
        PixelArt,
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
               + "Lightramp / Lightramp (Outline) / Crosstone / Crosstone (Outline) から選択。\n"
               + "NOTE: SCSS v1.11 は Built-in RP 専用です。URP プロジェクトではピンクになります。")]
        [SerializeField] private string _scssShaderName       = "Silent's Cel Shading/Lightramp (Outline)";
        [SerializeField] private string _crtShaderName        = "AITuber/RetroAvatarCRT";
        [SerializeField] private string _sketchShaderName     = "Shader Graphs/SketchEffect";
        [SerializeField] private string _watercolorShaderName = "AITuber/WatercolorAvatar";
        [SerializeField] private string _wireframeShaderName  = "AITuber/WireframeSolid";
        [SerializeField] private string _mangaShaderName      = "AITuber/MangaPanel";
        [SerializeField] private string _pixelArtShaderName  = "AITuber/PixelArtAvatar";

        [Tooltip("Sketch モード時に全レンダラーに上書きするマテリアル (SE_Avatar.mat を割り当てる)。")]
        [SerializeField] private Material _sketchOverrideMaterial;

        [Header("Shader Transition  (FR-SHADER-TRANSITION-01)")]
        [Tooltip("アバター専用トランジションマテリアル (ShaderTransitionAvatar.mat)。\n"
               + "未設定の場合は即時切り替えにフォールバックします。")]
        [SerializeField] private Material _avatarTransitionMaterial;
        [Tooltip("シェーダー切り替え時にアバターへのワイヤーフレームモーフトランジションを使用する (Play Mode のみ)。")]
        [SerializeField] private bool _useTransition = true;
        [Tooltip("トランジション全体の秒数 (前半: グリッド登場、後半: グリッド退場)。")]
        [SerializeField, Range(0.2f, 2.0f)] private float _transitionDuration = 0.7f;

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

        // Per-renderer original sharedMaterials, captured once at Awake for Sketch restore.
        private Material[][] _savedMaterials;

        // Per-material property set on avatar transition instances (FR-SHADER-TRANSITION-01).
        private static readonly int AvatarTransitionProgressId =
            Shader.PropertyToID("_TransitionProgress");

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

            // Save original sharedMaterials so Sketch mode can be fully reverted (FR-SHADER-02).
            _savedMaterials = new Material[_targetRenderers.Length][];
            for (int i = 0; i < _targetRenderers.Length; i++)
                _savedMaterials[i] = _targetRenderers[i] != null
                    ? (Material[])_targetRenderers[i].sharedMaterials.Clone()
                    : System.Array.Empty<Material>();

            // Detect actual initial shader from the first material so that
            // _currentMode reflects reality (e.g. after SCSSApplier was run in Edit Mode).
            DetectInitialMode();
        }

        private void OnDestroy()
        {
            if (Instance == this) Instance = null;
        }

        // ── Public API ─────────────────────────────────────────────────────

        /// <summary>
        /// Hot-swaps the shader on all managed renderers.
        /// FR-SHADER-02 / FR-SHADER-TRANSITION-01
        ///
        /// When <c>_useTransition</c> is true and the game is playing, plays the
        /// wireframe-grid morph effect and switches the shader at the visual midpoint.
        /// Otherwise switches immediately.
        /// </summary>
        public void ApplyShaderMode(ShaderMode mode)
        {
            if (mode == _currentMode) return;

            if (_useTransition && Application.isPlaying)
            {
                StopAllCoroutines();
                ShaderMode from = _currentMode;
                _currentMode = mode; // Claim immediately to block re-entrant calls.
                StartCoroutine(TransitionCoroutine(from, mode, _transitionDuration));
                return;
            }

            ApplyShaderModeImmediate(_currentMode, mode);
        }

        // Coroutine: avatar geometry morphs source-appearance → wireframe peak → target-appearance.
        // Per-renderer ShaderTransitionAvatar material instances are applied directly to the SMRs;
        // the full-screen renderer feature is not used. (FR-SHADER-TRANSITION-01)
        private IEnumerator TransitionCoroutine(ShaderMode from, ShaderMode to, float duration)
        {
            if (_avatarTransitionMaterial == null)
            {
                ApplyShaderModeImmediate(from, to);
                yield break;
            }

            float half = duration * 0.5f;

            // wirePhase = smoothstep(0.40, 0.88, p) が視覚的に始まる手前。
            // これより低い p では遷移シェーダーが元シェーダーと異なって見えるため
            // 遷移マテリアルを使う期間を [kLo, 1] に絞る。
            const float kLo = 0.38f;

            // ── Phase 1: 元シェーダーを保持 → kLo で遷移開始 → wireframe peak ──
            // kLo に達するまでは何もせずに待つ（元シェーダーがそのまま表示される）。
            float preDelay = half * kLo;
            for (float t = 0f; t < preDelay; t += Time.deltaTime)
                yield return null;

            // kLo からアニメーション開始。
            var srcInstances = CreateTransitionInstances(useSaved: true);
            for (int i = 0; i < srcInstances.Length; i++)
                srcInstances[i]?.SetFloat(AvatarTransitionProgressId, kLo);
            ApplyTransitionMaterials(srcInstances);

            float p1Dur = half * (1f - kLo);
            for (float t = 0f; t < p1Dur; t += Time.deltaTime)
            {
                float p = Mathf.Lerp(kLo, 1f, Mathf.Clamp01(t / p1Dur));
                for (int i = 0; i < srcInstances.Length; i++)
                    srcInstances[i]?.SetFloat(AvatarTransitionProgressId, p);
                yield return null;
            }
            for (int i = 0; i < srcInstances.Length; i++)
                srcInstances[i]?.SetFloat(AvatarTransitionProgressId, 1f);

            // ── Midpoint: ターゲットシェーダーに切り替え ──
            ApplyShaderModeImmediate(from, to);

            // ── Phase 2: wireframe peak → kLo → 即スナップ ──
            var dstInstances = CreateTransitionInstances(useSaved: true);
            for (int i = 0; i < dstInstances.Length; i++)
                dstInstances[i]?.SetFloat(AvatarTransitionProgressId, 1f);
            ApplyTransitionMaterials(dstInstances);

            float p2Dur = half * (1f - kLo);
            for (float t = 0f; t < p2Dur; t += Time.deltaTime)
            {
                float p = Mathf.Lerp(1f, kLo, Mathf.Clamp01(t / p2Dur));
                for (int i = 0; i < dstInstances.Length; i++)
                    dstInstances[i]?.SetFloat(AvatarTransitionProgressId, p);
                yield return null;
            }

            // kLo → 0 の「元シェーダーと違う見た目」区間はスキップしてターゲットにスナップ。
            ApplyShaderModeImmediate(from, to);

            for (int i = 0; i < srcInstances.Length; i++) if (srcInstances[i] != null) Destroy(srcInstances[i]);
            for (int i = 0; i < dstInstances.Length; i++) if (dstInstances[i] != null) Destroy(dstInstances[i]);
        }

        // Creates one Material instance per renderer from _avatarTransitionMaterial,
        // copying _MainTex / base colour.
        // useSaved=true: Awake 時に保存した _savedMaterials からテクスチャを読む。
        //   → WireframeSolid など _MainTex を持たないシェーダーが現在適用されていても
        //     元のテクスチャを正しくコピーできる。
        private Material[] CreateTransitionInstances(bool useSaved = false)
        {
            var instances = new Material[_targetRenderers.Length];
            for (int i = 0; i < _targetRenderers.Length; i++)
            {
                var rend = _targetRenderers[i];
                if (rend == null) continue;

                var inst = new Material(_avatarTransitionMaterial);

                // テクスチャソースの決定: useSaved=true なら保存済み元マテリアルを優先。
                Material srcMat = null;
                if (useSaved && _savedMaterials != null && i < _savedMaterials.Length
                    && _savedMaterials[i] != null && _savedMaterials[i].Length > 0)
                    srcMat = _savedMaterials[i][0];
                if (srcMat == null)
                {
                    var cur = rend.sharedMaterials;
                    if (cur != null && cur.Length > 0) srcMat = cur[0];
                }

                if (srcMat != null)
                {
                    Texture tex = null;
                    if      (srcMat.HasProperty("_MainTex")) tex = srcMat.GetTexture("_MainTex");
                    else if (srcMat.HasProperty("_BaseMap")) tex = srcMat.GetTexture("_BaseMap");
                    if (tex != null) inst.SetTexture("_MainTex", tex);

                    if      (srcMat.HasProperty("_BaseColor")) inst.SetColor("_BaseColor", srcMat.GetColor("_BaseColor"));
                    else if (srcMat.HasProperty("_Color"))      inst.SetColor("_BaseColor", srcMat.GetColor("_Color"));
                }
                instances[i] = inst;
            }
            return instances;
        }

        // Fills every material slot of each renderer with its per-renderer transition instance.
        private void ApplyTransitionMaterials(Material[] perRenderer)
        {
            for (int i = 0; i < _targetRenderers.Length && i < perRenderer.Length; i++)
            {
                var rend = _targetRenderers[i];
                if (rend == null || perRenderer[i] == null) continue;
                var mats = new Material[rend.sharedMaterials.Length];
                for (int j = 0; j < mats.Length; j++) mats[j] = perRenderer[i];
                rend.materials = mats;
            }
        }

        // Performs the immediate switch used both at the transition midpoint and the fast path.
        private void ApplyShaderModeImmediate(ShaderMode from, ShaderMode to)
        {
            // Disable pixel-art screen effect when leaving PixelArt mode. (FR-SHADER-02)
            if (from == ShaderMode.PixelArt)
            {
                PixelizeFeature.Instance?.SetEnabled(false);
                PixelizeFeature.Instance?.SetAvatarRenderers(null);
            }

            bool leavingSketch  = from == ShaderMode.Sketch;
            bool enteringSketch = to   == ShaderMode.Sketch;

            if (leavingSketch)
                RestoreSavedMaterials();

            if (enteringSketch)
            {
                if (_sketchOverrideMaterial == null)
                {
                    Debug.LogWarning("[AppearanceCtrl] _sketchOverrideMaterial is not assigned. Cannot apply Sketch mode.");
                    return;
                }
                ApplyMaterialOverride(_sketchOverrideMaterial);
            }
            else if (to == ShaderMode.PixelArt)
            {
                // Screen-space pixelization: keep current materials, just enable the blit pass.
                // Register avatar renderers so AvatarMaskPass marks only their pixels. (FR-SHADER-02)
                RestoreSavedMaterials();
                PixelizeFeature.Instance?.SetAvatarRenderers(_targetRenderers);
                PixelizeFeature.Instance?.SetEnabled(true);
            }
            else
            {
                // Always restore from saved originals so this method is safe to call even
                // when temporary transition materials are currently on the renderers.
                RestoreSavedMaterials();
                var shader = GetOrFindShader(to);
                if (shader == null) return;

                foreach (var rend in _targetRenderers)
                {
                    if (rend == null) continue;
                    var mats = rend.materials;
                    for (int i = 0; i < mats.Length; i++)
                        if (mats[i] != null) mats[i].shader = shader;
                    rend.materials = mats;
                }
            }

            _currentMode = to;
            Debug.Log($"[AppearanceCtrl] ShaderMode → {to}  (FR-SHADER-02)");
        }

        // Replaces every material slot on all renderers with a single override material.
        private void ApplyMaterialOverride(Material overrideMat)
        {
            foreach (var rend in _targetRenderers)
            {
                if (rend == null) continue;
                var mats = new Material[rend.sharedMaterials.Length];
                for (int i = 0; i < mats.Length; i++) mats[i] = overrideMat;
                rend.materials = mats;
            }
        }

        // Restores sharedMaterials from the snapshot taken at Awake.
        private void RestoreSavedMaterials()
        {
            if (_savedMaterials == null) return;
            for (int r = 0; r < _targetRenderers.Length && r < _savedMaterials.Length; r++)
            {
                if (_targetRenderers[r] == null) continue;
                _targetRenderers[r].materials = _savedMaterials[r];
            }
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
                ShaderMode.Toon       => _toonShaderName,
                ShaderMode.Lit        => _litShaderName,
                ShaderMode.Scss       => _scssShaderName,
                ShaderMode.Crt        => _crtShaderName,
                ShaderMode.Sketch     => _sketchShaderName,
                ShaderMode.Watercolor => _watercolorShaderName,
                ShaderMode.Wireframe  => _wireframeShaderName,
                ShaderMode.Manga      => _mangaShaderName,
                ShaderMode.PixelArt   => _toonShaderName,   // screen-effect mode; toon used as base
                _                     => _litShaderName,
            };
            var shader = Shader.Find(name);
            if (shader == null)
                Debug.LogWarning($"[AppearanceCtrl] Shader not found: '{name}'.");
            else
                _shaderCache[mode] = shader;
            return shader;
        }

        /// <summary>
        /// Inspects the first available material to determine the active shader mode at startup.
        /// Prevents the duplicate-apply skip when the initial shader was set by SCSSApplier.
        /// </summary>
        private void DetectInitialMode()
        {
            foreach (var rend in _targetRenderers)
            {
                if (rend == null) continue;
                var mats = rend.sharedMaterials;
                foreach (var mat in mats)
                {
                    if (mat == null || mat.shader == null) continue;
                    string sn = mat.shader.name;
                    if      (sn.StartsWith("Silent's Cel Shading"))           _currentMode = ShaderMode.Scss;
                    else if (sn == _toonShaderName)                             _currentMode = ShaderMode.Toon;
                    else if (sn.Contains("Universal Render Pipeline/Lit"))      _currentMode = ShaderMode.Lit;
                    else if (sn == _crtShaderName)                              _currentMode = ShaderMode.Crt;
                    else if (sn == _sketchShaderName)                           _currentMode = ShaderMode.Sketch;
                    else if (sn == _watercolorShaderName)                       _currentMode = ShaderMode.Watercolor;
                    else if (sn == _wireframeShaderName)                        _currentMode = ShaderMode.Wireframe;
                    else if (sn == _mangaShaderName)                            _currentMode = ShaderMode.Manga;
                    else if (sn == _pixelArtShaderName)                         _currentMode = ShaderMode.PixelArt;
                    else
                        continue;
                    Debug.Log($"[AppearanceCtrl] Initial ShaderMode detected: {_currentMode}");
                    return;  // first non-null material is enough
                }
            }
        }
    }
}
