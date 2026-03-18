// AvatarGrounding.cs
// NavMeshAgent 一本化によるアバター接地管理。(#67)
// CharacterController を廃止し NavMeshAgent が唯一の位置オーナー。
// QuQu(U.fbx) は Humanoid FBX。root origin がヒップ位置のため起動時に pivot を足裏へ補正する。

using UnityEngine;
using UnityEngine.AI;

namespace AITuber.Avatar
{
    [RequireComponent(typeof(NavMeshAgent))]
    public class AvatarGrounding : MonoBehaviour
    {
        // ── Inspector ──────────────────────────────────────────────

        [Header("Snap")]
        [SerializeField] private LayerMask _snapGroundLayers = ~0;
        [SerializeField] private float     _snapTimeout      = 3.0f;

        [Header("Foot IK（段差補正・オプション）")]
        [SerializeField] private bool             _enableFootIK = false;
        [SerializeField, Range(0f, 1f)] private float _ikWeight    = 0.5f;
        [SerializeField] private float            _footHeight  = 0.05f;
        [SerializeField] private float            _rayHeight   = 0.5f;
        [SerializeField] private float            _rayDistance = 0.6f;
        [SerializeField] private bool             _matchNormal = false;

        // ── Runtime ───────────────────────────────────────────────

        private NavMeshAgent        _agent;
        private Animator            _anim;
        private bool                _pivotFixed;    // アバター子 localY 補正済みフラグ
        private FootIKTargetUpdater _footIKUpdater;

        /// <summary>NavMeshAgent の参照。BSR / RoomManager が WarpTo / SetDestination で使う。</summary>
        public NavMeshAgent Agent => _agent;

        public bool Grounded => _agent != null && _agent.enabled && _agent.isOnNavMesh;
        /// <summary>BeginSnap が実行中なら true — walk_to はこれが false になるまで待つ。</summary>
        public bool IsSnapping  { get; private set; }

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

        // ── Unity ─────────────────────────────────────────────────

        private void Awake()
        {
            _agent = GetComponent<NavMeshAgent>();
            _agent.updateRotation = false;   // BSR がローテーションを制御
            _agent.enabled = false;          // BeginSnap 完了まで無効

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
            {
                _anim.gameObject.AddComponent<AvatarIKProxy>();
                Debug.Log($"[AvatarGrounding] AvatarIKProxy を {_anim.gameObject.name} に自動追加しました。Inspector の Component リストで確認できます。");
            }

            _footIKUpdater = GetComponent<FootIKTargetUpdater>();
            if (_footIKUpdater == null)
            {
                _footIKUpdater = gameObject.AddComponent<FootIKTargetUpdater>();
                Debug.Log("[AvatarGrounding] FootIKTargetUpdater を AvatarRoot に自動追加しました。");
            }

            // Phase 1: Trigger initial grounding at startup.
            // BeginSnap handles pivot fix (FBX hip-origin → sole-origin) + floor Warp.
            BeginSnap();
        }

        private void Update()
        {
            // Deferred snap fallback: if BeginSnap started a deferred snap (for re-snap after
            // a room switch mid-gameplay), advance the state machine in Update.
            if (_snapPhase != SnapPhase.Idle)
                UpdateSnap();
        }

        // ── Public API ────────────────────────────────────────────

        /// <summary>
        /// アバターを指定位置にワープさせる。NavMeshAgent を一時無効化して安全にテレポートする。
        /// 座席など NavMesh 外の位置にもワープ可能。
        /// </summary>
        public void WarpTo(Vector3 position)
        {
            if (_agent != null && _agent.enabled)
            {
                _agent.Warp(position);
            }
            else
            {
                transform.position = position;
            }
        }

        /// <summary>
        /// NavMeshAgent を有効化し、NavMesh 上の最寄りの有効ポイントに配置する。
        /// walk_to 開始前に呼ぶ。
        /// </summary>
        public void EnableAgentOnNavMesh()
        {
            if (_agent == null) return;
            if (!_agent.enabled)
            {
                // Find nearest NavMesh point before enabling to avoid agent placement issues
                if (NavMesh.SamplePosition(transform.position, out NavMeshHit hit, 5f, NavMesh.AllAreas))
                    transform.position = hit.position;
                _agent.enabled = true;
                _agent.Warp(transform.position);
            }
        }

        /// <summary>
        /// NavMeshAgent を無効化する。zone_snap や sit_settle など NavMesh 外への配置前に呼ぶ。
        /// </summary>
        public void DisableAgent()
        {
            if (_agent != null && _agent.enabled)
            {
                _agent.ResetPath();
                _agent.enabled = false;
            }
        }

        // ── 部屋切り替えスナップ ──────────────────────────────────

        /// <summary>
        /// Pivot 補正 + 床ワープを実行する。初回呼び出し時は同期実行、
        /// 部屋切り替え時は同期で実行し即座に完了する。
        /// RoomManager.DoSwitch() や Start() から呼ぶ。
        /// </summary>
        public void BeginSnap()
        {
            if (_snapPhase != SnapPhase.Idle)
            {
                Debug.LogWarning($"[AvatarGrounding] BeginSnap called while snap already in progress (phase={_snapPhase}) — ignoring.");
                return;
            }
            IsSnapping = true;
            _snapElapsed = 0f;

            // NavMeshAgent を無効化（直接 position を書き込むため）
            DisableAgent();

            Debug.Log($"[AvatarGrounding] BeginSnap — _pivotFixed={_pivotFixed}, _anim={((object)_anim != null ? _anim.gameObject.name : "null")}");

            // Synchronous execution: pivot fix + floor drop immediately.
            // Bone positions are valid from the Animator's initial bind-pose in Start().
            // Previously used a deferred Update state machine (PivotWait1 → PivotWait2)
            // which was unreliable in the Editor (Update() could stall).
            if (!_pivotFixed && _anim != null)
                DoFixPivot();
            StartFloorDrop();
        }

        /// <summary>
        /// Update-based snap state machine — only used as a fallback for edge cases
        /// where BeginSnap defers to the next frame (currently unused, kept for robustness).
        /// </summary>
        private void UpdateSnap()
        {
            _snapElapsed += Time.deltaTime;
            _snapPhaseTimer += Time.deltaTime;

            // Global timeout — PivotWait phases have no individual timeout,
            // so enforce the global timeout for all pre-FloorDrop phases too.
            if (_snapElapsed >= _snapTimeout && _snapPhase != SnapPhase.FloorDrop)
            {
                Debug.LogWarning($"[AvatarGrounding] Snap phase {_snapPhase} stuck for {_snapElapsed:F2}s — force-completing.");
                if (!_pivotFixed) DoFixPivot();
                StartFloorDrop();
                return;
            }

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
            // 床高さを問い合わせて root を決定論的に配置する。
            // NavMeshAgent は無効状態なので transform.position に直接書き込む。
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

            // NavMesh 上の最寄り点を使い、raycast 床高さも加味して配置する。
            var groundedPosition = new Vector3(transform.position.x, floorY, transform.position.z);
            if (NavMesh.SamplePosition(groundedPosition + Vector3.up * 0.5f, out NavMeshHit navHit, 6f, NavMesh.AllAreas))
            {
                groundedPosition = navHit.position;
                Debug.Log($"[AvatarGrounding] FloorSnap — currentY={currentY:F3} floor={floorY:F3} target={groundedPosition} ({hitName}, navMesh={navHit.position})");
            }
            else
            {
                Debug.Log($"[AvatarGrounding] FloorSnap — currentY={currentY:F3} floor={floorY:F3} target={groundedPosition} ({hitName}, no NavMesh)");
            }

            transform.position = groundedPosition;

            // NavMeshAgent を有効化して NavMesh 上に配置する
            _agent.enabled = true;
            _agent.Warp(groundedPosition);
            FinishSnap();
        }

        private void FinishSnap()
        {
            Debug.Log($"[AvatarGrounding] Snap done — y={transform.position.y:F4}" +
                      (_snapElapsed >= _snapTimeout ? " [TIMEOUT]" : $" [stable {_snapElapsed:F2}s]"));
            _snapPhase = SnapPhase.Idle;
            IsSnapping = false;
        }

        /// <summary>
        /// Debug / Editor 用: スナップが固着した場合に外部から完了を強制する。
        /// DoFixPivot + StartFloorDrop + NavMeshAgent 再有効化を含む完全なチェーンを実行する。
        /// </summary>
        public void ForceCompleteSnap()
        {
            if (!IsSnapping) return;
            Debug.LogWarning("[AvatarGrounding] ForceCompleteSnap invoked — running full chain.");
            if (!_pivotFixed) DoFixPivot();
            StartFloorDrop();
        }

        // ── Foot IK ───────────────────────────────────────────────

        private void OnAnimatorIK(int layerIndex)          => ApplyFootIK();
        public  void OnAnimatorIKFromProxy(int layerIndex) => ApplyFootIK();

        private void ApplyFootIK()
        {
            if ((_enableFootIK == false && FootIKBlend <= 0.001f) || _anim == null || !_anim.isHuman) return;
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
            Gizmos.DrawSphere(transform.position, 0.28f);
        }
#endif
    }
}