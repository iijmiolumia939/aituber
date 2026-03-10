// HairPhysicsTests.cs
// EditMode unit tests for HairPhysicsConfig and HairPhysicsApplicator.
// TC-HAIR-PHYS-01 ~ TC-HAIR-PHYS-05
//
// Coverage:
//   HAIR-PHYS-01  HairPhysicsConfig default values: damping ∈ (0, 1], stiffness ≥ 0, radius > 0
//   HAIR-PHYS-02  Front hair damping ≥ 0.5f (prevents overdamped washout) and stiffness ≤ 0.1f (soft)
//   HAIR-PHYS-03  Side hair gravityY ≥ front hair gravityY (heavier pull for long twin-tail)
//   HAIR-PHYS-04  Head collider radius ≥ 0.10f, Neck radius ≥ 0.05f (FR-LIFE-03 spec)
//   HAIR-PHYS-05  HairPhysicsApplicator.Apply() with null config → no exception, logs warning
//
// SRS refs: FR-LIFE-03
// Issue: #31

using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;
using System.Text.RegularExpressions;
using AITuber.Avatar;

namespace AITuber.Tests
{
    /// <summary>
    /// EditMode unit tests for HairPhysicsConfig and HairPhysicsApplicator.
    /// DynamicBone component is NOT instantiated in these tests — config data and
    /// null-safety of the applicator are verified without a live hierarchy.
    /// TC-HAIR-PHYS-01 ~ TC-HAIR-PHYS-05 / FR-LIFE-03 / Issue #31
    /// </summary>
    public class HairPhysicsTests
    {
        private HairPhysicsConfig _config;
        private GameObject        _go;
        private HairPhysicsApplicator _applicator;

        [SetUp]
        public void SetUp()
        {
            _config = ScriptableObject.CreateInstance<HairPhysicsConfig>();
            _go = new GameObject("HairPhysics_Test");
            _applicator = _go.AddComponent<HairPhysicsApplicator>();
        }

        [TearDown]
        public void TearDown()
        {
            Object.DestroyImmediate(_go);
            Object.DestroyImmediate(_config);
        }

        // ── TC-HAIR-PHYS-01 ─────────────────────────────────────────

        /// <summary>
        /// All four hair group default values must be within physically valid ranges:
        /// damping ∈ (0, 1], stiffness ≥ 0, radius > 0, gravityY ≥ 0.
        /// </summary>
        [Test]
        public void TC_HAIR_PHYS_01_DefaultGroupParams_AreValidRanges()
        {
            AssertGroupValid("front",  _config.front);
            AssertGroupValid("side",   _config.side);
            AssertGroupValid("ribbon", _config.ribbon);
            AssertGroupValid("body",   _config.body);
        }

        private static void AssertGroupValid(string label, HairGroupParams p)
        {
            Assert.Greater(p.damping,    0f,  $"{label}.damping must be > 0");
            Assert.LessOrEqual(p.damping, 1f, $"{label}.damping must be ≤ 1");
            Assert.GreaterOrEqual(p.stiffness,  0f, $"{label}.stiffness must be ≥ 0");
            Assert.Greater(p.radius,     0f,  $"{label}.radius must be > 0");
            Assert.GreaterOrEqual(p.gravityY,   0f, $"{label}.gravityY must be ≥ 0");
        }

        // ── TC-HAIR-PHYS-02 ─────────────────────────────────────────

        /// <summary>
        /// Front hair: damping ≥ 0.5 (prevents wild oscillation) and stiffness ≤ 0.1 (soft bangs).
        /// </summary>
        [Test]
        public void TC_HAIR_PHYS_02_FrontHair_DampingAndStiffnessAreInComfortRange()
        {
            Assert.GreaterOrEqual(_config.front.damping,   0.5f,
                "Front hair damping must be ≥ 0.5 to prevent oscillation during motion.");
            Assert.LessOrEqual(_config.front.stiffness, 0.1f,
                "Front hair stiffness must be ≤ 0.1 for soft, natural front bangs.");
        }

        // ── TC-HAIR-PHYS-03 ─────────────────────────────────────────

        /// <summary>
        /// Side/long hair gravityY must be ≥ front hair gravityY.
        /// Long twin-tails have heavier vertical pull than short front bangs.
        /// </summary>
        [Test]
        public void TC_HAIR_PHYS_03_SideHair_GravityY_GeqFrontHair()
        {
            Assert.GreaterOrEqual(_config.side.gravityY, _config.front.gravityY,
                "Side/long hair gravityY must be ≥ front hair gravityY — longer hair hangs heavier.");
        }

        // ── TC-HAIR-PHYS-04 ─────────────────────────────────────────

        /// <summary>
        /// Head and Neck collider radii meet FR-LIFE-03 minimum values:
        /// Head ≥ 0.10 m, Neck ≥ 0.05 m.
        /// </summary>
        [Test]
        public void TC_HAIR_PHYS_04_ColliderRadii_MeetFRLIFE03Spec()
        {
            Assert.GreaterOrEqual(_config.head.radius, 0.10f,
                "FR-LIFE-03: Head collider radius must be ≥ 0.10 m to prevent front hair clipping.");
            Assert.GreaterOrEqual(_config.neck.radius, 0.05f,
                "FR-LIFE-03: Neck collider radius must be ≥ 0.05 m.");
        }

        // ── TC-HAIR-PHYS-05 ─────────────────────────────────────────

        /// <summary>
        /// Apply() with no config assigned logs a warning and does not throw.
        /// Config is intentionally NOT set on _applicator (field is null).
        /// </summary>
        [Test]
        public void TC_HAIR_PHYS_05_Apply_WithNullConfig_DoesNotThrow_LogsWarning()
        {
            // _config is NOT assigned to _applicator — default field is null.
            LogAssert.Expect(LogType.Warning, new Regex("HairPhysicsApplicator"));

            Assert.DoesNotThrow(() => _applicator.Apply(),
                "HairPhysicsApplicator.Apply() must not throw when config is null.");
        }
    }
}
