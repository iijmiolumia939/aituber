// HairPhysicsApplicator.cs
// MonoBehaviour — HairPhysicsConfig の値を DynamicBone / DynamicBoneCollider に適用する。
// Inspector の [Apply Hair Physics Config] ContextMenu か Awake() から実行する。
//
// SRS refs: FR-LIFE-03
// Issue: #31

using System.Collections.Generic;
using UnityEngine;

namespace AITuber.Avatar
{
    /// <summary>
    /// <see cref="HairPhysicsConfig"/> をアバター階層の DynamicBone / DynamicBoneCollider に適用する。
    /// AvatarRoot の同 GameObject にアタッチし、<see cref="_config"/> を Inspector でアサインすること。
    /// FR-LIFE-03
    /// </summary>
    [DisallowMultipleComponent]
    public class HairPhysicsApplicator : MonoBehaviour
    {
        [SerializeField] private HairPhysicsConfig _config;

        private void Awake()
        {
            if (_config != null)
                Apply();
        }

        // Editor / Inspector でパラメータを変更したとき即時反映する
        private void OnValidate()
        {
            if (_config != null)
                Apply();
        }

        /// <summary>
        /// 設定値を DynamicBone / DynamicBoneCollider に書き込む。
        /// Inspector の ContextMenu からも呼び出せる。
        /// </summary>
        [ContextMenu("Apply Hair Physics Config")]
        public void Apply()
        {
            if (_config == null)
            {
                Debug.LogWarning("[HairPhysicsApplicator] Config is null. Assign a HairPhysicsConfig asset in the Inspector.");
                return;
            }

            ApplyGroupParams("SpringBones/SpringBone_HairFront", _config.front);
            ApplyGroupParams("SpringBones/SpringBone_HairSide",  _config.side);
            ApplyGroupParams("SpringBones/SpringBone_Ribbon",    _config.ribbon);
            ApplyGroupParams("SpringBones/SpringBone_Body",      _config.body);

            ApplyCollider(_config.head);
            ApplyCollider(_config.neck);
            ApplyCollider(_config.chest);
            ApplyCollider(_config.lShoulder);
            ApplyCollider(_config.rShoulder);

            Debug.Log("[HairPhysicsApplicator] Hair physics config applied.");
        }

        // ── Private helpers ──────────────────────────────────────────

        private void ApplyGroupParams(string relativePath, HairGroupParams p)
        {
            var t = transform.Find(relativePath);
            if (t == null)
            {
                Debug.LogWarning($"[HairPhysicsApplicator] GameObject not found at path: {relativePath} (relative to {name})");
                return;
            }
            var db = t.GetComponent<DynamicBone>();
            if (db == null) return;

            db.m_Stiffness  = p.stiffness;
            db.m_Elasticity = p.elasticity;
            db.m_Damping    = p.damping;
            db.m_Gravity    = new Vector3(0f, -p.gravityY, 0f);
            db.m_Radius     = p.radius;
            // m_Force は DynamicBone の「休止重力キャンセル」機構に依存しない常時力。
            // 静止中でも前髪の浮きを抑制するために -Y 方向に加える。
            db.m_Force      = new Vector3(0f, -p.forceY, 0f);
            // シミュレーション中のパーティクルキャッシュ (m_LocalGravity 等) に反映
            db.UpdateParameters();
        }

        private void ApplyCollider(ColliderBoneParams p)
        {
            if (string.IsNullOrEmpty(p.boneName)) return;
            var bone = FindBoneRecursive(transform, p.boneName);
            if (bone == null) return;
            var col = bone.GetComponent<DynamicBoneCollider>();
            if (col == null) return;

            col.m_Center = p.center;
            col.m_Radius = p.radius;
        }

        private static Transform FindBoneRecursive(Transform t, string name)
        {
            if (t.name == name) return t;
            foreach (Transform child in t)
            {
                var result = FindBoneRecursive(child, name);
                if (result != null) return result;
            }
            return null;
        }
    }
}
