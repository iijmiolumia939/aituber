// AvatarGrounding.cs
// StarterAssets ThirdPersonController の重力・着地実装。
// QuQu(U.fbx) は Humanoid FBX。root origin がヒップ位置のため起動時に pivot を足裏へ補正する。

using UnityEngine;
using UnityEngine.AI;

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
        [SerializeField] private float     _navMeshSnapRadius = 6.0f;
        [SerializeField] private float     _maxNavMeshSnapDrift = 0.35f;

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
        private bool                _pivotFixed;    // アバター子 localY 補正済みフラグ
        private const float         _terminalVelocity = 53.0f;

        // Phase 2: horizontal velocity injected each frame by locomotion (BSR walk).
        // Consumed in ApplyGravity() each frame.
        private Vector3 _externalHorizontalVelocity;

        // StarterAssets デフォルト固定値（pivot = 足裏 が前提）
        private const float GroundedOffset = 0.14f;

        public bool Grounded   { get; private set; } = true;
        /// <summary>BeginSnap が実行中なら true — walk_to はこれが false になるまで待つ。</summary>
        public bool IsSnapping  { get; private set; }
        /// <summary>zone_snap 中に重力を一時停止するフラグ。</summary>
        private bool _gravitySuspended;

        /// <summary>
        /// 座席スナップ中に重力を停止／再開する。<br/>
        /// true: CC gravity を止め、蓄積速度もリセット。<br/>
        /// false: 重力再開（続けて BeginSnap を呼ぶこと）。
        /// </summary>
        public void SuspendGravity(bool suspended)
        {
            _gravitySuspended = suspended;
            if (suspended)
            {
                _verticalVelocity            = 0f;
                _externalHorizontalVelocity  = Vector3.zero;
            }
        }
        /// <summary>
        /// Phase 5: Foot IK の実効ウェイト乗数（0=OFF, 1=_ikWeight をフル適用）。
        /// FootIKTargetUpdater が idle/walk/snap 状態に応じて毎フレーム書き込む。
        /// デフォルト 0 = FootIKTargetUpdater が存在しない場合は IK 無効。
        /// </summary>
        public float FootIKBlend { get; set; } = 0f;
        /// <summary>
        /// Issue #51 (revised): Animator の "speed" parameter が 0 超なら歩行中と判定する computed プロパティ。
        /// BehaviorSequenceRunner が SetFloat("speed", 1f/0f) を呼ぶことがすでに Single Source of Truth 。
        /// 手動で true/false を外部から小ける必要がないため、
        /// セット漏れによる Foot IK フリーズバグが発生しない。
        /// </summary>
        public bool IsLocomoting => _anim != null && _anim.GetFloat("speed") > 0.05f;

        // ── Snap state machine ──────────────────────────────────────
        private enum SnapPhase { Idle, PivotWait1, PivotWait2, FloorDrop }
        private SnapPhase _snapPhase     = SnapPhase.Idle;
        private float     _snapPhaseTimer;
        private float     _snapElapsed;
        private float     _snapLastY;
        private int       _snapStableFrames;

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

            // Disable NavMeshAgent at startup so it doesn't interfere with
            // CharacterController gravity or coroutine scheduling on this GO.
            // BehaviorSequenceRunner enables it explicitly when walking starts.
            var startAgent = GetComponent<UnityEngine.AI.NavMeshAgent>();
            if (startAgent != null) startAgent.enabled = false;

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

            // Phase 1: Trigger initial grounding at startup.
            // BeginSnap handles pivot fix (FBX hip-origin → sole-origin) + floor-drop via CC gravity.
            // Prevents avatar from floating in mid-air when the scene first loads.
            BeginSnap();
        }

        private void Update()
        {
            if (_cc.enabled)
            {
                ApplyGravity();
                GroundedCheck();
            }
            if (_snapPhase != SnapPhase.Idle)
                UpdateSnap();
        }

        // ── Grounded / Gravity（StarterAssets そのまま）─────────────

        private void GroundedCheck()
        {
            // CharacterController already resolves actual contact against the world during Move().
            // Using it as the single source of truth avoids startup false positives from nearby
            // colliders when the avatar is still visibly above the floor.
            Grounded = _cc.isGrounded;
        }

        /// <summary>
        /// 外部ロコモーションソース（walk_to コルーチン）から 1 フレーム分の水平速度を注入する。
        /// ApplyGravity() で重力と合算して CC.Move に渡す。
        /// </summary>
        public void RequestHorizontalMove(Vector3 worldVelocity)
        {
            _externalHorizontalVelocity.x = worldVelocity.x;
            _externalHorizontalVelocity.z = worldVelocity.z;
        }

        private void ApplyGravity()
        {
            if (_gravitySuspended) return;
            if (Grounded && _verticalVelocity < 0f)
                _verticalVelocity = -2f;

            if (_verticalVelocity < _terminalVelocity)
                _verticalVelocity += _gravity * Time.deltaTime;

            // Combine external horizontal (locomotion) + vertical gravity in one CC.Move.
            var move = _externalHorizontalVelocity + new Vector3(0f, _verticalVelocity, 0f);
            _cc.Move(move * Time.deltaTime);
            _externalHorizontalVelocity = Vector3.zero; // consumed each frame
        }

        // ── 部屋切り替えスナップ（Update state machine）──────────────

        /// <summary>
        /// 部屋切り替え時に呼ぶ。pivot 補正 → 落下着地を Update ループで実行する。
        /// コルーチンを使わないので MonoBehaviour の有効状態に依存しない。
        /// RoomManager.DoSwitch() から呼ぶ。
        /// </summary>
        public void BeginSnap()
        {
            if (_snapPhase != SnapPhase.Idle)
            {
                // Reliability (review): log so caller knows the re-entry was dropped.
                // RoomManager should wait for IsSnapping==false before calling BeginSnap again.
                Debug.LogWarning($"[AvatarGrounding] BeginSnap called while snap already in progress (phase={_snapPhase}) — ignoring.");
                return;
            }
            IsSnapping = true;

            // NavMeshAgent を無効化（CC と競合防止）
            var agent = GetComponent<NavMeshAgent>();
            if (agent != null && agent.enabled) agent.enabled = false;

            Debug.Log($"[AvatarGrounding] BeginSnap — _pivotFixed={_pivotFixed}, _anim={((object)_anim != null ? _anim.gameObject.name : "null")}");

            if (!_pivotFixed && _anim != null)
            {
                _snapPhaseTimer = 0f;
                _snapPhase      = SnapPhase.PivotWait1;
            }
            else
            {
                StartFloorDrop();
            }
        }

        private void UpdateSnap()
        {
            _snapElapsed += Time.deltaTime;
            _snapPhaseTimer += Time.deltaTime;

            switch (_snapPhase)
            {
                case SnapPhase.PivotWait1:
                    // Animator 初期化直後は Humanoid bone のワールド位置が安定しないことがある。
                    if (_snapPhaseTimer >= 0.1f)
                    {
                        _snapPhaseTimer = 0f;
                        _snapPhase = SnapPhase.PivotWait2;
                    }
                    break;

                case SnapPhase.PivotWait2:
                    if (_snapPhaseTimer >= 0.1f)
                    {
                        DoFixPivot();
                        StartFloorDrop();
                    }
                    break;

                case SnapPhase.FloorDrop:
                    if (_snapElapsed >= _snapTimeout)
                        FinishSnap();
                    break;
            }
        }

        private void DoFixPivot()
        {
            if (_anim == null) { _pivotFixed = true; return; }

            var lf = _anim.GetBoneTransform(HumanBodyBones.LeftFoot);
            var rf = _anim.GetBoneTransform(HumanBodyBones.RightFoot);
            if (lf != null && rf != null)
            {
                float ankleLocal = ((lf.position.y + rf.position.y) * 0.5f) - transform.position.y;
                float soleLocal  = ankleLocal - _footHeight;
                var avatarTr = _anim.transform;
                var lp       = avatarTr.localPosition;
                lp.y        -= soleLocal;
                avatarTr.localPosition = lp;
                Debug.Log($"[AvatarGrounding] Pivot fixed: Avatar localY += {-soleLocal:F4}m");
            }
            _pivotFixed = true;
        }

        private void StartFloorDrop()
        {
            // 起動時/テレポート時の接地は、Rigging や重力落下で解くより
            // 「床高さを問い合わせて root を決定論的に置く」方が安定する。
            // Rigging / Foot IK は最終見た目の補正であって、root 配置の責務ではない。
            _cc.enabled       = false;
            _verticalVelocity = 0f;

            // 床候補は「現在の root より下」にあり、かつ上向き法線を持つ hit に限定する。
            // これで天井や梁の下面を誤採用しない。
            float currentY = transform.position.y;
            float floorY   = currentY;
            string hitName = "(none)";
            var origin     = transform.position + Vector3.up * 30f;
            var allHits    = Physics.RaycastAll(new Ray(origin, Vector3.down), 50f,
                                                _snapGroundLayers, QueryTriggerInteraction.Ignore);
            if (allHits.Length > 0)
            {
                float bestY = float.MinValue;
                foreach (var h in allHits)
                {
                    if (h.point.y > currentY + 0.05f)
                        continue;

                    if (h.normal.y < 0.5f)
                        continue;

                    if (h.point.y > bestY)
                    {
                        bestY = h.point.y;
                        hitName = h.collider.name;
                    }
                }

                if (bestY > float.MinValue)
                    floorY = bestY;
                else
                    Debug.LogWarning($"[AvatarGrounding] 床候補が見つかりませんでした。currentY={currentY:F3}, hits={allHits.Length}");
            }
            else
            {
                Debug.LogWarning("[AvatarGrounding] 床を検出できませんでした。");
            }

            // CharacterController の底面が床に軽く接する Y を直接求める。
            // 手動で Y=0 を入れた後に約 0.055 へ落ち着くのは skinWidth 分だけ浮くためで、
            // 初期配置でも同じ値を使うのが最も一貫する。
            float groundedY = floorY + _cc.skinWidth;
            var groundedPosition = new Vector3(transform.position.x, groundedY, transform.position.z);
            if (TryProjectToNearestNavMesh(groundedPosition, out Vector3 navMeshPosition, out string navMeshReason))
            {
                groundedPosition = navMeshPosition;
                Debug.Log($"[AvatarGrounding] FloorSnap — currentY={currentY:F3} floor={floorY:F3} target={groundedPosition} ({hitName}, {navMeshReason})");
            }
            else
            {
                Debug.Log($"[AvatarGrounding] FloorSnap NavMesh projection skipped: {navMeshReason}");
                Debug.Log($"[AvatarGrounding] FloorSnap — currentY={currentY:F3} floor={floorY:F3} targetY={groundedY:F3} ({hitName})");
            }

            transform.position = groundedPosition;

            _cc.enabled = true;
            GroundedCheck();
            FinishSnap();
        }

        private bool TryProjectToNearestNavMesh(Vector3 groundedPosition, out Vector3 projectedPosition, out string reason)
        {
            projectedPosition = groundedPosition;
            reason = "no NavMesh projection attempted";

            var sampleOrigin = groundedPosition + Vector3.up * 0.5f;
            if (!NavMesh.SamplePosition(sampleOrigin, out NavMeshHit hit, _navMeshSnapRadius, NavMesh.AllAreas))
            {
                reason = $"no NavMesh within {_navMeshSnapRadius:F1}m of {groundedPosition}";
                return false;
            }

            float horizontalDrift = Vector2.Distance(
                new Vector2(groundedPosition.x, groundedPosition.z),
                new Vector2(hit.position.x, hit.position.z));
            if (horizontalDrift > _maxNavMeshSnapDrift)
            {
                reason = $"nearest NavMesh drift too large ({horizontalDrift:F2}m > {_maxNavMeshSnapDrift:F2}m)";
                return false;
            }

            projectedPosition = new Vector3(hit.position.x, groundedPosition.y, hit.position.z);
            reason = $"navMeshXZ={hit.position} drift={horizontalDrift:F2}m";
            return true;
        }

        private void FinishSnap()
        {
            Debug.Log($"[AvatarGrounding] Snap done — y={transform.position.y:F4}" +
                      (_snapElapsed >= _snapTimeout ? " [TIMEOUT]" : $" [stable {_snapElapsed:F2}s]"));
            _snapPhase = SnapPhase.Idle;
            IsSnapping = false;
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

            // Phase 5: multiply inspector weight by runtime blend set by FootIKTargetUpdater.
            // FootIKBlend == 0 when walking or snapping → IK is effectively off.
            float w = _ikWeight * FootIKBlend;
            if (w <= 0.001f)
            {
                _anim.SetIKPositionWeight(goal, 0f);
                _anim.SetIKRotationWeight(goal, 0f);
                return;
            }

            var origin = footTr.position + Vector3.up * _rayHeight;
            if (Physics.Raycast(origin, Vector3.down, out var hit,
                                _rayHeight + _rayDistance, Physics.DefaultRaycastLayers,
                                QueryTriggerInteraction.Ignore)
                && Mathf.Abs(hit.point.y - footTr.position.y) <= 0.8f)
            {
                _anim.SetIKPositionWeight(goal, w);
                _anim.SetIKPosition(goal, hit.point + Vector3.up * _footHeight);
                if (_matchNormal)
                {
                    var rot = Quaternion.LookRotation(
                        Vector3.Cross(hit.normal, -transform.right), hit.normal);
                    _anim.SetIKRotationWeight(goal, w);
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