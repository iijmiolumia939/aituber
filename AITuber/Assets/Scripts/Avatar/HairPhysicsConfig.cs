// HairPhysicsConfig.cs
// ScriptableObject — 髪物理パラメータ一元管理 (FR-LIFE-03)
// SpringBoneSetup.cs のハードコード値をアセットとして Inspector で調整可能にする。
//
// 使い方:
//   Assets/ 以下で右クリック → Create → AITuber → Hair Physics Config
//   AvatarRoot の HairPhysicsApplicator コンポーネントにアサイン。
//
// SRS refs: FR-LIFE-03
// Issue: #31

using UnityEngine;

namespace AITuber.Avatar
{
    /// <summary>
    /// DynamicBone グループ 1 本分のパラメータ。
    /// </summary>
    [System.Serializable]
    public struct HairGroupParams
    {
        [Tooltip("DynamicBone.m_Stiffness — ボーンの剛性 (0=柔, 1=硬)")]
        [Range(0f, 1f)] public float stiffness;

        [Tooltip("DynamicBone.m_Elasticity — 元位置への戻り力")]
        [Range(0f, 1f)] public float elasticity;

        [Tooltip("DynamicBone.m_Damping — 振動減衰 (高いほど早く止まる)")]
        [Range(0f, 1f)] public float damping;

        [Tooltip("DynamicBone.m_Gravity の -Y 成分 (重力の強さ)")]
        [Range(0f, 2f)] public float gravityY;

        [Tooltip("DynamicBone.m_Radius — ボーンの當たり判定半径 [m]")]
        [Range(0f, 0.2f)] public float radius;

        [Tooltip("DynamicBone.m_Force の -Y 成分 — 休止重力キャンセルに依存しない常時下向き力 (浮きぐせがある場合に増やす)")]
        [Range(0f, 1f)] public float forceY;
    }

    /// <summary>
    /// 単一コライダーボーンのパラメータ。
    /// </summary>
    [System.Serializable]
    public struct ColliderBoneParams
    {
        [Tooltip("ボーン名 (FindBone で前方一致検索)")]
        public string boneName;

        [Tooltip("DynamicBoneCollider.m_Center — ローカルオフセット")]
        public Vector3 center;

        [Tooltip("DynamicBoneCollider.m_Radius — 球コライダー半径 [m]")]
        [Range(0f, 0.3f)] public float radius;
    }

    /// <summary>
    /// QuQu アバター髪グループ・コライダー全パラメータ。FR-LIFE-03
    /// HairPhysicsApplicator が参照してランタイムに DynamicBone へ適用する。
    /// </summary>
    [CreateAssetMenu(fileName = "HairPhysicsConfig", menuName = "AITuber/Hair Physics Config", order = 62)]
    public class HairPhysicsConfig : ScriptableObject
    {
        // ── 髪グループ ──────────────────────────────────────────────

        [Header("前髪 (SpringBone_HairFront: FrontA, FrontB)")]
        public HairGroupParams front = new HairGroupParams
        {
            stiffness  = 0.03f,
            elasticity = 0.05f,
            damping    = 0.65f,
            gravityY   = 0.60f,
            radius     = 0.03f,
            forceY     = 0.20f,  // 常時下向き力: 休止重力キャンセルを補正
        };

        [Header("サイド/ロング髪 (SpringBone_HairSide: Side_L, Side_R)")]
        public HairGroupParams side = new HairGroupParams
        {
            stiffness  = 0.02f,
            elasticity = 0.05f,
            damping    = 0.65f,
            gravityY   = 0.70f,
            radius     = 0.03f,
            forceY     = 0.15f,
        };

        [Header("リボン (SpringBone_Ribbon: ribon, ribon1_L, ribon1_R)")]
        public HairGroupParams ribbon = new HairGroupParams
        {
            stiffness  = 0.08f,
            elasticity = 0.05f,
            damping    = 0.55f,
            gravityY   = 0.40f,
            radius     = 0.02f,
            forceY     = 0.10f,
        };

        [Header("ボディ (SpringBone_Body: 胸・お尻)")]
        public HairGroupParams body = new HairGroupParams
        {
            stiffness  = 0.15f,
            elasticity = 0.05f,
            damping    = 0.80f,
            gravityY   = 0.05f,
            radius     = 0.04f,
        };

        // ── コライダーボーン (FR-LIFE-03: Head 0.12 m / Neck 0.06 m) ────

        [Header("コライダー設定 — FR-LIFE-03 推奨値に調整済み")]

        [Tooltip("頭球コライダー。前髪の頭へのめり込みを防ぐ。FR-LIFE-03 推奨: 0.12 m")]
        public ColliderBoneParams head = new ColliderBoneParams
        {
            boneName = "Head",
            center   = new Vector3(0f, 0.03f, 0f),
            radius   = 0.12f,
        };

        [Tooltip("首球コライダー。FR-LIFE-03 推奨: 0.06 m")]
        public ColliderBoneParams neck = new ColliderBoneParams
        {
            boneName = "Neck",
            center   = Vector3.zero,
            radius   = 0.06f,
        };

        [Tooltip("胸球コライダー。ロング/サイド髪が胸を貫通しないようにする。")]
        public ColliderBoneParams chest = new ColliderBoneParams
        {
            boneName = "Chest",
            center   = new Vector3(0f, 0.05f, 0.02f),
            radius   = 0.10f,
        };

        [Tooltip("左肩コライダー。ツインテールが肩ラインを貫通しないようにする。")]
        public ColliderBoneParams lShoulder = new ColliderBoneParams
        {
            boneName = "L_Shoulder",
            center   = new Vector3(0.06f, 0f, 0f),
            radius   = 0.07f,
        };

        [Tooltip("右肩コライダー。")]
        public ColliderBoneParams rShoulder = new ColliderBoneParams
        {
            boneName = "R_Shoulder",
            center   = new Vector3(-0.06f, 0f, 0f),
            radius   = 0.07f,
        };

#if UNITY_EDITOR
        // Inspector でこのアセットのスライダーを変更したとき、
        // シーン内の全 HairPhysicsApplicator へ即時伝播する。
        // (MonoBehaviour.OnValidate はアセット側の変更では発火しないため、
        //  ScriptableObject 側でグローバルに通知する必要がある)
        private void OnValidate()
        {
            var applicators = FindObjectsByType<HairPhysicsApplicator>(FindObjectsSortMode.None);
            foreach (var a in applicators)
                a.Apply();
        }
#endif
    }
}
