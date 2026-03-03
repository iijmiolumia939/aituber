// AvatarGrounding.cs
// StarterAssets ThirdPersonController の重力・着地実装。
// VRM 1.0 の pivot は足裏にある前提 → 計算・補正なし。

using System.Collections;
using UnityEngine;

namespace AITuber.Avatar
{
    [RequireComponent(typeof(CharacterController))]
    public class AvatarGrounding : MonoBehaviour
    {
        // ── Inspector ──────────────────────────────────────────────

        [Header("CharacterController 形状")]
        [SerializeField] private float _capsuleHeight = 1.7f;
        [SerializeField] private float _capsuleRadius = 0.15f;

        [Header("Grounded Check")]
        [SerializeField] private float     _groundedRadius = 0.28f;
        [SerializeField] private LayerMask _groundLayers   = ~0;

        [Header("Snap")]
        [SerializeField] private LayerMask _snapGroundLayers = ~0;
        [SerializeField] private float     _snapTimeout      = 3.0f;

        [Header("Gravity")]
        [SerializeField] private float _gravity = -15.0f;

        [Header("Foot IK（段差補正・オプション）")]
        [SerializeField] private bool             _enableFootIK = false;
        [SerializeField, Range(0f, 1f)] private float _ikWeight    = 0.5f;
        [SerializeField] private float            _footHeight  = 0.05f;
        [SerializeField] private float            _rayHeight   = 0.5f;
        [SerializeField] private float            _rayDistance = 0.6f;
        [SerializeField] private bool             _matchNormal = false;

        // ── Runtime ───────────────────────────────────────────────

        private CharacterController _cc;
        private Animator            _anim;
        private float               _verticalVelocity;
        private bool                _pivotFixed;    // VRM 子 localY 補正済みフラグ
        private const float         _terminalVelocity = 53.0f;

        // StarterAssets デフォルト固定値（pivot = 足裏 が前提）
        private const float GroundedOffset = 0.14f;

        public bool Grounded { get; private set; } = true;

        // ── Unity ─────────────────────────────────────────────────

        private void Awake()
        {
            _cc = GetComponent<CharacterController>();
            _cc.height          = _capsuleHeight;
            _cc.radius          = _capsuleRadius;
            _cc.center          = new Vector3(0f, _capsuleHeight * 0.5f, 0f);
            _cc.skinWidth       = 0.02f;
            _cc.minMoveDistance = 0f;
            _cc.slopeLimit      = 45f;
            _cc.stepOffset      = 0.1f;

            // AvatarRoot 自身ではなく「子」の humanoid Animator を探す
            // （AvatarRoot にも Animator が付いている場合があるため除外）
            foreach (var a in GetComponentsInChildren<Animator>(true))
            {
                if (a.gameObject == gameObject) continue; // AvatarRoot 自身はスキップ
                if (a.isHuman) { _anim = a; break; }
            }
            // 子に humanoid Animator がなければ AvatarRoot 自身の Animator を使う
            if (_anim == null)
                foreach (var a in GetComponentsInChildren<Animator>(true))
                    if (a.isHuman) { _anim = a; break; }
        }

        private void Start()
        {
            if (_anim != null && _anim.gameObject != gameObject
                && _anim.gameObject.GetComponent<AvatarIKProxy>() == null)
                _anim.gameObject.AddComponent<AvatarIKProxy>();
        }

        private void Update()
        {
            if (!_cc.enabled) return;
            ApplyGravity();
            GroundedCheck();
        }

        // ── Grounded / Gravity（StarterAssets そのまま）─────────────

        private void GroundedCheck()
        {
            Grounded = Physics.CheckSphere(
                new Vector3(transform.position.x, transform.position.y - GroundedOffset, transform.position.z),
                _groundedRadius, _groundLayers, QueryTriggerInteraction.Ignore);
        }

        private void ApplyGravity()
        {
            if (Grounded && _verticalVelocity < 0f)
                _verticalVelocity = -2f;

            if (_verticalVelocity < _terminalVelocity)
                _verticalVelocity += _gravity * Time.deltaTime;

            _cc.Move(new Vector3(0f, _verticalVelocity, 0f) * Time.deltaTime);
        }

        // ── 部屋切り替えスナップ ──────────────────────────────────────

        /// <summary>RoomManager.DoSwitch() から呼ぶ。</summary>
        public IEnumerator SnapCoroutine()
        {
            _cc.enabled       = false;
            _verticalVelocity = 0f;

            // ── 初回のみ: VRM の pivot を足裏に合わせる ─────────────────
            // VRoid Studio は VRM 1.0 でも root origin がヒップ位置にある。
            // 足ボーンのワールド Y を実測して VRM 子 GO を上にずらし、
            // pivot = 足裏（AvatarRoot.y = 足裏の高さ）を成立させる。
            // これが済めば以後は StarterAssets の数値をそのまま使える。
            if (!_pivotFixed && _anim != null)
            {
                yield return null; // Animator がアイドルポーズを適用するまで1フレーム待つ
                yield return null;

                var lf = _anim.GetBoneTransform(HumanBodyBones.LeftFoot);
                var rf = _anim.GetBoneTransform(HumanBodyBones.RightFoot);
                if (lf != null && rf != null)
                {
                    // 足裏のローカル Y（= 足首Y − footHeight − AvatarRoot.y）
                    float ankleLocal = ((lf.position.y + rf.position.y) * 0.5f) - transform.position.y;
                    float soleLocal  = ankleLocal - _footHeight;
                    // soleLocal を 0 にするには VRM 子を -soleLocal 分上にずらす
                    var vrmTr     = _anim.transform;
                    var lp        = vrmTr.localPosition;
                    lp.y         -= soleLocal;
                    vrmTr.localPosition = lp;
                    Debug.Log($"[AvatarGrounding] Pivot fixed: VRM localY += {-soleLocal:F4}m (soleLocal was {soleLocal:F4}m)");
                }
                _pivotFixed = true;
            }

            // 床を Raycast で探す
            float floorY   = transform.position.y;
            string hitName = "(none)";
            var origin     = transform.position + Vector3.up * 30f;
            if (Physics.Raycast(new Ray(origin, Vector3.down), out var hit, 50f,
                                _snapGroundLayers, QueryTriggerInteraction.Ignore))
            {
                floorY  = hit.point.y;
                hitName = hit.collider.name;
            }
            else
            {
                Debug.LogWarning("[AvatarGrounding] 床を検出できませんでした。");
            }

            // 床面から 3m 上に配置して落下（pivot = 足裏なので transform.y = 足裏の高さ）
            transform.position = new Vector3(transform.position.x, floorY + 3.0f, transform.position.z);
            Debug.Log($"[AvatarGrounding] Snap start — floor={floorY:F3} ({hitName})");

            _cc.enabled       = true;
            _verticalVelocity = 0f;

            // 着地を待つ
            float elapsed    = 0f;
            int   stableFrames = 0;
            float lastY      = transform.position.y;

            while (elapsed < _snapTimeout)
            {
                yield return null;
                elapsed += Time.deltaTime;
                float dy = Mathf.Abs(transform.position.y - lastY);
                lastY = transform.position.y;

                if (Grounded && dy < 0.002f) { if (++stableFrames >= 5) break; }
                else stableFrames = 0;
            }

            Debug.Log($"[AvatarGrounding] Snap done — y={transform.position.y:F4}" +
                      (elapsed >= _snapTimeout ? " [TIMEOUT]" : $" [stable {elapsed:F2}s]"));
        }

        // ── Foot IK ───────────────────────────────────────────────

        private void OnAnimatorIK(int layerIndex)          => ApplyFootIK();
        public  void OnAnimatorIKFromProxy(int layerIndex) => ApplyFootIK();

        private void ApplyFootIK()
        {
            if (!_enableFootIK || _anim == null || !_anim.isHuman) return;
            UpdateFootIK(AvatarIKGoal.LeftFoot);
            UpdateFootIK(AvatarIKGoal.RightFoot);
        }

        private void UpdateFootIK(AvatarIKGoal goal)
        {
            var bone   = goal == AvatarIKGoal.LeftFoot ? HumanBodyBones.LeftFoot : HumanBodyBones.RightFoot;
            var footTr = _anim.GetBoneTransform(bone);
            if (footTr == null) return;

            var origin = footTr.position + Vector3.up * _rayHeight;
            if (Physics.Raycast(origin, Vector3.down, out var hit,
                                _rayHeight + _rayDistance, Physics.DefaultRaycastLayers,
                                QueryTriggerInteraction.Ignore)
                && Mathf.Abs(hit.point.y - footTr.position.y) <= 0.8f)
            {
                _anim.SetIKPositionWeight(goal, _ikWeight);
                _anim.SetIKPosition(goal, hit.point + Vector3.up * _footHeight);
                if (_matchNormal)
                {
                    var rot = Quaternion.LookRotation(
                        Vector3.Cross(hit.normal, -transform.right), hit.normal);
                    _anim.SetIKRotationWeight(goal, _ikWeight);
                    _anim.SetIKRotation(goal, rot);
                }
            }
            else
            {
                _anim.SetIKPositionWeight(goal, 0f);
                _anim.SetIKRotationWeight(goal, 0f);
            }
        }

#if UNITY_EDITOR
        private void OnDrawGizmosSelected()
        {
            Gizmos.color = Application.isPlaying && Grounded
                ? new Color(0f, 1f, 0f, 0.35f) : new Color(1f, 0f, 0f, 0.35f);
            Gizmos.DrawSphere(
                new Vector3(transform.position.x, transform.position.y - GroundedOffset, transform.position.z),
                _groundedRadius);
        }
#endif
    }
}