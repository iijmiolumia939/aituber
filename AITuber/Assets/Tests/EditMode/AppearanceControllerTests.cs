// AppearanceControllerTests.cs
// EditMode unit tests for AppearanceController, CostumeDefinition, HairstyleDefinition.
// TC-APPEAR-01 ~ TC-APPEAR-12
//
// Coverage:
//   APPEAR-01  ApplyCostume — 登録済み ID で CostumeDefinition.Apply が実行される
//   APPEAR-02  ApplyCostume — 同じ ID を 2 回呼ぶと 2 回目は no-op (CurrentCostume 不変)
//   APPEAR-03  ApplyCostume — 未登録 ID → 警告ログ + 状態変化なし
//   APPEAR-04  ApplyHair   — 登録済み ID で HairstyleDefinition.Apply が実行される
//   APPEAR-05  ApplyHair   — 同じ ID を 2 回呼ぶと 2 回目は no-op (CurrentHair 不変)
//   APPEAR-06  ApplyHair   — 未登録 ID → 警告ログ + 状態変化なし
//   APPEAR-07  CostumeDefinition.Apply — 一致するレンダラーにマテリアルが適用される
//   APPEAR-08  CostumeDefinition.Apply — 一致しないレンダラーは変更されない
//   APPEAR-09  CostumeDefinition.Apply — null renderers → 例外なし
//   APPEAR-10  HairstyleDefinition.Apply — 一致するレンダラーにマテリアルが適用される
//   APPEAR-11  HairstyleDefinition.Apply — null renderers → 例外なし
//   APPEAR-12  ApplyCostume + ApplyHair を同時指定 → 両方が反映される
//
// SRS refs: FR-APPEARANCE-01, FR-APPEARANCE-02, FR-APPEARANCE-03
// Issue: #29

using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;
using AITuber.Avatar;

namespace AITuber.Tests
{
    /// <summary>
    /// EditMode tests for AppearanceController / CostumeDefinition / HairstyleDefinition.
    /// TC-APPEAR-01 ~ TC-APPEAR-12
    /// FR-APPEARANCE-01, FR-APPEARANCE-02, FR-APPEARANCE-03 / Issue #29
    /// </summary>
    public class AppearanceControllerTests
    {
        // ── Fixtures ─────────────────────────────────────────────────────────

        private GameObject         _go;
        private AppearanceController _ac;

        [SetUp]
        public void SetUp()
        {
            _go = new GameObject("AC_Test");
            _ac = _go.AddComponent<AppearanceController>();
        }

        [TearDown]
        public void TearDown()
        {
            Object.DestroyImmediate(_go);
        }

        // ── Helpers ───────────────────────────────────────────────────────────

        /// <summary>最小限の CostumeDefinition を作成する。</summary>
        private static CostumeDefinition MakeCostume(string id)
        {
            var def = ScriptableObject.CreateInstance<CostumeDefinition>();
            def.costumeId   = id;
            def.displayName = id;
            def.overrides   = System.Array.Empty<RendererMaterialOverride>();
            return def;
        }

        /// <summary>最小限の HairstyleDefinition を作成する。</summary>
        private static HairstyleDefinition MakeHair(string id)
        {
            var def = ScriptableObject.CreateInstance<HairstyleDefinition>();
            def.hairId      = id;
            def.displayName = id;
            def.overrides   = System.Array.Empty<RendererMaterialOverride>();
            return def;
        }

        /// <summary>
        /// リフレクションで AppearanceController の private フィールドに配列をセットする。
        /// </summary>
        private void SetCostumes(CostumeDefinition[] defs)
        {
            var field = typeof(AppearanceController)
                .GetField("_costumes", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance);
            Assert.IsNotNull(field, "_costumes field not found");
            field.SetValue(_ac, defs);
        }

        private void SetHairstyles(HairstyleDefinition[] defs)
        {
            var field = typeof(AppearanceController)
                .GetField("_hairstyles", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance);
            Assert.IsNotNull(field, "_hairstyles field not found");
            field.SetValue(_ac, defs);
        }

        // ── TC-APPEAR-01: ApplyCostume 登録済み ID ────────────────────────────

        [Test]
        public void TC_APPEAR_01_ApplyCostume_KnownId_UpdatesCurrentCostume()
        {
            var def = MakeCostume("casual");
            SetCostumes(new[] { def });

            _ac.ApplyCostume("casual");

            Assert.AreEqual("casual", _ac.CurrentCostume,
                "TC-APPEAR-01: CurrentCostume should be 'casual' after ApplyCostume('casual')");

            Object.DestroyImmediate(def);
        }

        // ── TC-APPEAR-02: ApplyCostume 同 ID 2 回目は no-op ──────────────────

        [Test]
        public void TC_APPEAR_02_ApplyCostume_SameIdTwice_IsNoOp()
        {
            var def = MakeCostume("formal");
            SetCostumes(new[] { def });

            _ac.ApplyCostume("formal");
            // 2 回目: 同じ ID → 内部 skip (early-return on _currentCostume check)
            LogAssert.ignoreFailingMessages = true;
            _ac.ApplyCostume("formal");
            LogAssert.ignoreFailingMessages = false;

            Assert.AreEqual("formal", _ac.CurrentCostume,
                "TC-APPEAR-02: CurrentCostume should remain 'formal'");

            Object.DestroyImmediate(def);
        }

        // ── TC-APPEAR-03: ApplyCostume 未登録 ID → 警告 ──────────────────────

        [Test]
        public void TC_APPEAR_03_ApplyCostume_UnknownId_LogsWarning()
        {
            SetCostumes(new[] { MakeCostume("default") });

            LogAssert.Expect(LogType.Warning,
                new System.Text.RegularExpressions.Regex(@"\[AppearanceCtrl\].*Costume preset not found.*no_such_costume"));

            _ac.ApplyCostume("no_such_costume");

            Assert.AreEqual("", _ac.CurrentCostume,
                "TC-APPEAR-03: CurrentCostume should remain empty on unknown id");
        }

        // ── TC-APPEAR-04: ApplyHair 登録済み ID ─────────────────────────────

        [Test]
        public void TC_APPEAR_04_ApplyHair_KnownId_UpdatesCurrentHair()
        {
            var def = MakeHair("ponytail");
            SetHairstyles(new[] { def });

            _ac.ApplyHair("ponytail");

            Assert.AreEqual("ponytail", _ac.CurrentHair,
                "TC-APPEAR-04: CurrentHair should be 'ponytail'");

            Object.DestroyImmediate(def);
        }

        // ── TC-APPEAR-05: ApplyHair 同 ID 2 回目は no-op ─────────────────────

        [Test]
        public void TC_APPEAR_05_ApplyHair_SameIdTwice_IsNoOp()
        {
            var def = MakeHair("short");
            SetHairstyles(new[] { def });

            _ac.ApplyHair("short");
            LogAssert.ignoreFailingMessages = true;
            _ac.ApplyHair("short");
            LogAssert.ignoreFailingMessages = false;

            Assert.AreEqual("short", _ac.CurrentHair,
                "TC-APPEAR-05: CurrentHair should remain 'short'");

            Object.DestroyImmediate(def);
        }

        // ── TC-APPEAR-06: ApplyHair 未登録 ID → 警告 ─────────────────────────

        [Test]
        public void TC_APPEAR_06_ApplyHair_UnknownId_LogsWarning()
        {
            SetHairstyles(new[] { MakeHair("default") });

            LogAssert.Expect(LogType.Warning,
                new System.Text.RegularExpressions.Regex(@"\[AppearanceCtrl\].*Hair preset not found.*no_such_hair"));

            _ac.ApplyHair("no_such_hair");

            Assert.AreEqual("", _ac.CurrentHair,
                "TC-APPEAR-06: CurrentHair should remain empty on unknown id");
        }

        // ── TC-APPEAR-07: CostumeDefinition.Apply — 一致レンダラーに適用 ──────

        [Test]
        public void TC_APPEAR_07_CostumeDefinition_Apply_MatchingRenderer_MaterialReplaced()
        {
            // Arrange
            var mat = new Material(Shader.Find("Hidden/InternalErrorShader") ?? Shader.Find("Standard"));
            var def = ScriptableObject.CreateInstance<CostumeDefinition>();
            def.costumeId = "test";
            def.overrides = new[]
            {
                new RendererMaterialOverride
                {
                    rendererName = "Body",
                    materials    = new[] { mat },
                }
            };

            var rendGo = new GameObject("Body");
            var rend   = rendGo.AddComponent<MeshRenderer>();
            rend.sharedMaterials = new Material[] { null };

            // Act
            def.Apply(new Renderer[] { rend });

            // Assert
            Assert.AreEqual(mat, rend.sharedMaterials[0],
                "TC-APPEAR-07: Material should be replaced on matching renderer");

            Object.DestroyImmediate(rendGo);
            Object.DestroyImmediate(def);
            Object.DestroyImmediate(mat);
        }

        // ── TC-APPEAR-08: CostumeDefinition.Apply — 不一致レンダラーは変更なし ─

        [Test]
        public void TC_APPEAR_08_CostumeDefinition_Apply_NonMatchingRenderer_Unchanged()
        {
            var matOrig = new Material(Shader.Find("Hidden/InternalErrorShader") ?? Shader.Find("Standard"));
            var matNew  = new Material(Shader.Find("Hidden/InternalErrorShader") ?? Shader.Find("Standard"));

            var def = ScriptableObject.CreateInstance<CostumeDefinition>();
            def.costumeId = "test";
            def.overrides = new[]
            {
                new RendererMaterialOverride { rendererName = "Skirt", materials = new[] { matNew } }
            };

            var rendGo = new GameObject("Body");
            var rend   = rendGo.AddComponent<MeshRenderer>();
            rend.sharedMaterials = new[] { matOrig };

            def.Apply(new Renderer[] { rend });

            Assert.AreEqual(matOrig, rend.sharedMaterials[0],
                "TC-APPEAR-08: Non-matching renderer should not be modified");

            Object.DestroyImmediate(rendGo);
            Object.DestroyImmediate(def);
            Object.DestroyImmediate(matOrig);
            Object.DestroyImmediate(matNew);
        }

        // ── TC-APPEAR-09: CostumeDefinition.Apply — null renderers は例外なし ──

        [Test]
        public void TC_APPEAR_09_CostumeDefinition_Apply_NullRenderers_NoException()
        {
            var def = MakeCostume("x");
            Assert.DoesNotThrow(() => def.Apply(null),
                "TC-APPEAR-09: Apply(null) should not throw");
            Object.DestroyImmediate(def);
        }

        // ── TC-APPEAR-10: HairstyleDefinition.Apply — 一致レンダラーに適用 ────

        [Test]
        public void TC_APPEAR_10_HairstyleDefinition_Apply_MatchingRenderer_MaterialReplaced()
        {
            var mat = new Material(Shader.Find("Hidden/InternalErrorShader") ?? Shader.Find("Standard"));
            var def = ScriptableObject.CreateInstance<HairstyleDefinition>();
            def.hairId = "test";
            def.overrides = new[]
            {
                new RendererMaterialOverride { rendererName = "Hair", materials = new[] { mat } }
            };

            var rendGo = new GameObject("Hair");
            var rend   = rendGo.AddComponent<MeshRenderer>();
            rend.sharedMaterials = new Material[] { null };

            def.Apply(new Renderer[] { rend });

            Assert.AreEqual(mat, rend.sharedMaterials[0],
                "TC-APPEAR-10: Material should be replaced on matching hair renderer");

            Object.DestroyImmediate(rendGo);
            Object.DestroyImmediate(def);
            Object.DestroyImmediate(mat);
        }

        // ── TC-APPEAR-11: HairstyleDefinition.Apply — null renderers は例外なし ─

        [Test]
        public void TC_APPEAR_11_HairstyleDefinition_Apply_NullRenderers_NoException()
        {
            var def = MakeHair("y");
            Assert.DoesNotThrow(() => def.Apply(null),
                "TC-APPEAR-11: Apply(null) should not throw");
            Object.DestroyImmediate(def);
        }

        // ── TC-APPEAR-12: ApplyCostume + ApplyHair 同時指定 ──────────────────

        [Test]
        public void TC_APPEAR_12_ApplyCostumeAndHair_BothApplied()
        {
            var costume = MakeCostume("pajama");
            var hair    = MakeHair("twin_tails");
            SetCostumes(new[] { costume });
            SetHairstyles(new[] { hair });

            _ac.ApplyCostume("pajama");
            _ac.ApplyHair("twin_tails");

            Assert.AreEqual("pajama",     _ac.CurrentCostume, "TC-APPEAR-12: costume");
            Assert.AreEqual("twin_tails", _ac.CurrentHair,    "TC-APPEAR-12: hair");

            Object.DestroyImmediate(costume);
            Object.DestroyImmediate(hair);
        }
    }
}
