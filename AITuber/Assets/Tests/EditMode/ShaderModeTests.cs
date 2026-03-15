// ShaderModeTests.cs
// EditMode unit tests for AppearanceController shader-mode switching.
// TC-SHADER-01 ~ TC-SHADER-06
//
// Coverage:
//   SHADER-01  ShaderMode enum — Toon/Lit/Wireframe/Crt/Sketch/Watercolor/Manga/PixelArt が全て定義されている
//   SHADER-02  ApplyShaderMode — 同じモードを 2 回呼ぶと no-op (CurrentMode 変化なし)
//   SHADER-03  CurrentMode     — 初期値は Toon (FR-SHADER-02 デフォルト)
//   SHADER-04  ApplyShaderMode — シェーダーキャッシュ注入時に CurrentMode が変わる
//   SHADER-05  ApplyShaderMode — 未知のシェーダー名 → 警告ログ + CurrentMode 変化なし
//   SHADER-06  ShaderMode parse — WS から受け取る際の Enum.TryParse (大文字小文字無視) が正しく動作する
//
// SRS refs: FR-SHADER-02
// Issue: #28

using System;
using System.Collections.Generic;
using System.Reflection;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;
using AITuber.Avatar;

namespace AITuber.Tests
{
    /// <summary>
    /// EditMode tests for AppearanceController shader-mode switching.
    /// TC-SHADER-01 ~ TC-SHADER-06
    /// FR-SHADER-02 / Issue #28
    /// </summary>
    public class ShaderModeTests
    {
        // ── Fixtures ─────────────────────────────────────────────────────────

        private GameObject _go;
        private AppearanceController _ac;

        [SetUp]
        public void SetUp()
        {
            _go = new GameObject("AC_Shader_Test");
            _ac = _go.AddComponent<AppearanceController>();
        }

        [TearDown]
        public void TearDown()
        {
            UnityEngine.Object.DestroyImmediate(_go);
        }

        // ── Tests ─────────────────────────────────────────────────────────────

        /// <summary>
        /// TC-SHADER-01: ShaderMode enum에 Toon/Lit/Wireframe/Crt/Sketch/Watercolor/Manga/PixelArt が全て定義されている。
        /// FR-SHADER-02
        /// </summary>
        [Test]
        public void TC_SHADER_01_ShaderMode_Enum_HasAllExpectedValues()
        {
            var names = Enum.GetNames(typeof(ShaderMode));
            CollectionAssert.Contains(names, "Toon");
            CollectionAssert.Contains(names, "Lit");
            CollectionAssert.Contains(names, "Wireframe");
            CollectionAssert.Contains(names, "Crt");
            CollectionAssert.Contains(names, "Sketch");
            CollectionAssert.Contains(names, "Watercolor");
            CollectionAssert.Contains(names, "Manga");
            CollectionAssert.Contains(names, "PixelArt");
        }

        /// <summary>
        /// TC-SHADER-02: ApplyShaderMode(currentMode) は no-op — shader lookup も発生しない。
        /// FR-SHADER-02
        /// </summary>
        [Test]
        public void TC_SHADER_02_ApplyShaderMode_SameMode_IsNoOp()
        {
            ShaderMode initial = _ac.CurrentMode;
            _ac.ApplyShaderMode(initial);
            Assert.AreEqual(initial, _ac.CurrentMode, "Same-mode call must not change CurrentMode");
        }

        /// <summary>
        /// TC-SHADER-03: 起動直後の CurrentMode はデフォルト値の Toon。
        /// FR-SHADER-02
        /// </summary>
        [Test]
        public void TC_SHADER_03_InitialCurrentMode_IsToon()
        {
            Assert.AreEqual(ShaderMode.Toon, _ac.CurrentMode,
                "AppearanceController must start with ShaderMode.Toon as default");
        }

        /// <summary>
        /// TC-SHADER-04: シェーダーキャッシュにシェーダーを直接注入した場合、
        ///   ApplyShaderMode が渡されたモードに CurrentMode を更新する。
        ///   （Shader.Find の環境依存を避けるためキャッシュ注入アプローチを用いる）
        /// FR-SHADER-02
        /// </summary>
        [Test]
        public void TC_SHADER_04_ApplyShaderMode_WithCachedShader_ChangesCurrentMode()
        {
            var cacheField = typeof(AppearanceController).GetField(
                "_shaderCache", BindingFlags.NonPublic | BindingFlags.Instance);
            Assert.IsNotNull(cacheField, "_shaderCache private field must exist");

            var cache = (Dictionary<ShaderMode, Shader>)cacheField.GetValue(_ac);

            // Use any available shader as a stand-in. URP/Lit is preferred; fallback to built-ins.
            var shader = Shader.Find("Universal Render Pipeline/Lit")
                      ?? Shader.Find("Hidden/InternalErrorShader")
                      ?? Shader.Find("Sprites/Default");
            Assume.That(shader, Is.Not.Null,
                "At least one fallback shader (URP/Lit, Hidden/InternalErrorShader, Sprites/Default) must be findable");

            cache[ShaderMode.Lit] = shader;

            // Ensure _targetRenderers is a valid (empty) array so foreach in
            // ApplyShaderModeImmediate doesn't throw. This guards against the edge case
            // where Awake's Singleton check fires before initialization completes.
            var renderersField = typeof(AppearanceController).GetField(
                "_targetRenderers", BindingFlags.NonPublic | BindingFlags.Instance);
            if (renderersField != null && renderersField.GetValue(_ac) == null)
                renderersField.SetValue(_ac, new Renderer[0]);

            // Likewise ensure _savedMaterials is not null (used in RestoreSavedMaterials).
            var savedField = typeof(AppearanceController).GetField(
                "_savedMaterials", BindingFlags.NonPublic | BindingFlags.Instance);
            if (savedField != null && savedField.GetValue(_ac) == null)
                savedField.SetValue(_ac, new UnityEngine.Material[0][]);

            _ac.ApplyShaderMode(ShaderMode.Lit);

            Assert.AreEqual(ShaderMode.Lit, _ac.CurrentMode,
                "CurrentMode must switch to Lit after ApplyShaderMode with a cached shader");
        }

        /// <summary>
        /// TC-SHADER-05: ターゲットシェーダーが見つからない場合、警告ログが出て CurrentMode は変わらない。
        /// FR-SHADER-02
        /// </summary>
        [Test]
        public void TC_SHADER_05_ApplyShaderMode_ShaderNotFound_LogsWarningAndKeepsMode()
        {
            // Override _crtShaderName to a guaranteed-nonexistent shader name.
            var nameField = typeof(AppearanceController).GetField(
                "_crtShaderName", BindingFlags.NonPublic | BindingFlags.Instance);
            Assert.IsNotNull(nameField, "_crtShaderName private field must exist");
            nameField.SetValue(_ac, "AITuber/__NonExistent_Shader_TC05__");

            ShaderMode before = _ac.CurrentMode;

            LogAssert.Expect(LogType.Warning,
                new System.Text.RegularExpressions.Regex("Shader not found"));

            _ac.ApplyShaderMode(ShaderMode.Crt);

            Assert.AreEqual(before, _ac.CurrentMode,
                "CurrentMode must remain unchanged when the target shader cannot be found");
        }

        /// <summary>
        /// TC-SHADER-06: WS コマンドから受け取る shader_mode 文字列が
        ///   Enum.TryParse (caseInsensitive) で正しく ShaderMode に変換される。
        /// FR-SHADER-02
        /// </summary>
        [Test]
        public void TC_SHADER_06_ShaderModeString_ParsesCaseInsensitive()
        {
            Assert.IsTrue(Enum.TryParse<ShaderMode>("toon",      true, out var r1));
            Assert.AreEqual(ShaderMode.Toon, r1);

            Assert.IsTrue(Enum.TryParse<ShaderMode>("Lit",       true, out var r2));
            Assert.AreEqual(ShaderMode.Lit, r2);

            Assert.IsTrue(Enum.TryParse<ShaderMode>("WIREFRAME", true, out var r3));
            Assert.AreEqual(ShaderMode.Wireframe, r3);

            Assert.IsTrue(Enum.TryParse<ShaderMode>("crt",       true, out var r4));
            Assert.AreEqual(ShaderMode.Crt, r4);

            Assert.IsFalse(Enum.TryParse<ShaderMode>("invalid_shader_xyz", true, out _),
                "Unknown shader_mode string must not parse to a valid ShaderMode");
        }
    }
}
