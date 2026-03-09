// GazeController.cs
// Manages LookAt IK, saccade micro-movement, and comment-read gaze override.
// Extracted from AvatarController as part of the Strangler Fig refactor (Issue #52, Phase 3).
//
// SRS refs: FR-A7-01, FR-WS-01

using UnityEngine;

namespace AITuber.Avatar
{
    /// <summary>
    /// Drives LookAt IK (camera/chat/down/random), saccade micro-movement,
    /// and comment-read gaze override.
    /// Attach to the same GameObject as AvatarController.
    /// </summary>
    [DisallowMultipleComponent]
    public sealed class GazeController : MonoBehaviour
    {
        // ── Inspector ──────────────────────────────────────────────────────────

        [Header("IK / Look Targets")]
        [SerializeField] private Transform _lookAtCamera;
        [SerializeField] private Transform _lookAtChat;
        [SerializeField] private Transform _lookAtDown;
        [SerializeField] private float _lookAtWeight = 0.8f;

        [Header("Comment Gaze")]
        [Tooltip("コメント読み上げ中に視線を向けるオブジェクト。AITuber/Setup Comment Area で自動配置できます。")]
        [SerializeField] private Transform _commentAreaAnchor;

        // ── Runtime refs ───────────────────────────────────────────────────────

        private Animator  _animator;
        private Transform _currentLookAtTarget;

        // ── Random look state ──────────────────────────────────────────────────

        private bool  _isRandomLook;
        private float _nextRandomLookTime;
        private const float RandomLookIntervalMin = 1.5f;
        private const float RandomLookIntervalMax = 4.0f;

        // ── Saccade state ──────────────────────────────────────────────────────

        private Vector3 _saccadeOffset;
        private Vector3 _saccadeTargetOffset;
        private float   _saccadeTimer;

        // ── Comment gaze state ─────────────────────────────────────────────────

        private bool  _hasCommentGazeOverride;
        private float _commentHeadBlend; // 0..1, lerps toward 1 on start, 0 on end

        // ── Head gesture flag (forwarded from AvatarController) ────────────────

        private bool _isHeadGestureActive;

        // ── Unity lifecycle ────────────────────────────────────────────────────

        private void Awake()
        {
            // LookAt ターゲットと CommentArea を AvatarRoot の子にする。
            // AvatarGrounding が AvatarRoot を床に吸着させると子オブジェクトも追従するため、
            // ターゲットを World 座標で再設定する必要がなくなる。
            // worldPositionStays=true により現在のワールド位置は維持される。
            ReparentIfOrphan(_lookAtCamera);
            ReparentIfOrphan(_lookAtChat);
            ReparentIfOrphan(_lookAtDown);
            ReparentIfOrphan(_commentAreaAnchor);

            // Default look target — overridden by SetTarget() before first frame.
            _currentLookAtTarget = _lookAtCamera;
        }

        private void Update()
        {
            UpdateSaccade();
        }

        // ── Public API ─────────────────────────────────────────────────────────

        /// <summary>Wires the Animator reference. Called from AvatarController.Start().</summary>
        public void Initialize(Animator animator) => _animator = animator;

        /// <summary>Sets the active look target by name (camera/chat/down/random/center).</summary>
        public void SetTarget(string target)
        {
            _isRandomLook = target == "random";
            if (_isRandomLook)
            {
                // 初回はすぐに切り替え
                _nextRandomLookTime = 0f;
                PickRandomLookTarget();
                return;
            }
            _currentLookAtTarget = target switch
            {
                "camera" => _lookAtCamera,
                "chat"   => _lookAtChat,
                "down"   => _lookAtDown,
                "center" => _lookAtCamera,
                _        => _lookAtCamera,
            };
        }

        /// <summary>Enables or disables comment-read gaze override (from avatar_event).</summary>
        public void SetCommentGazeOverride(bool active) => _hasCommentGazeOverride = active;

        /// <summary>
        /// Pass true when the current gesture uses head animation (nod/shake/facepalm),
        /// causing IK head weight to be zeroed to avoid fighting the animation.
        /// </summary>
        public void SetHeadGestureActive(bool active) => _isHeadGestureActive = active;

        /// <summary>
        /// Forwarded from AvatarIKProxy. AvatarController keeps the public method
        /// and delegates here (1-line delegate pattern, exec-plan Phase 3).
        /// </summary>
        public void OnAnimatorIKFromProxy(int layerIndex) => ApplyLookAtIK();

        /// <summary>
        /// Returns the LookAt IK influence weight for the current target.
        /// Used by Audio2GestureController to reduce head/neck weight when eyes are tracking.
        /// </summary>
        public float LookAtInfluence => (_currentLookAtTarget != null) ? _lookAtWeight : 0f;

        // ── Private methods ────────────────────────────────────────────────────

        private void PickRandomLookTarget()
        {
            var targets = new[] { _lookAtCamera, _lookAtChat, _lookAtDown };
            _currentLookAtTarget = targets[UnityEngine.Random.Range(0, targets.Length)];
            _nextRandomLookTime = Time.time + UnityEngine.Random.Range(
                RandomLookIntervalMin, RandomLookIntervalMax);
        }

        private void ApplyLookAtIK()
        {
            if (_animator == null) return;

            // random モード: 一定間隔でターゲットを切り替え
            if (_isRandomLook && Time.time >= _nextRandomLookTime)
                PickRandomLookTarget();

            // コメントスキャン中は _currentLookAtTarget が null でも動作させる。
            // null のときは _lookAtCamera にフォールバック。
            // _commentHeadBlend > 0 の間はフェードアウト中なのでカメラをフォールバックに使う
            bool commentActive = _hasCommentGazeOverride || _commentHeadBlend > 0.01f;
            Transform activeLookTarget = _currentLookAtTarget
                ?? (commentActive ? _lookAtCamera : null);

            if (activeLookTarget != null || commentActive)
            {
                // 頭部アニメーションを持つジェスチャー中は headWeight=0 にする。
                // Nod/Shake/Facepalm はアニメーションで頭を動かすため IK を切る。
                // 通常は headWeight を小さくして「視線主体・顔はほぼ動かない」にする。
                //   bodyWeight = 0   : 体回転なし（アニメーション優先）
                //   headWeight = 0.1 : 顔はごく僅かに追従
                //   eyesWeight = 1.0 : 眼球は最大追従
                //   clampWeight= 0.7 : 眼球の可動範囲を広げる
                float blendTarget = _hasCommentGazeOverride ? 1f : 0f;
                _commentHeadBlend = Mathf.Lerp(_commentHeadBlend, blendTarget, Time.deltaTime * 8f);
                float headW  = _isHeadGestureActive ? 0f : Mathf.Lerp(0.1f,  0.65f, _commentHeadBlend);
                float bodyW  = Mathf.Lerp(0f,   0.12f, _commentHeadBlend);
                float clampW = Mathf.Lerp(0.8f, 0.9f,  _commentHeadBlend);
                _animator.SetLookAtWeight(_lookAtWeight, bodyW, headW, 1f, clampW);
                // end 時も gazePos → normalPos をなめらかにブレンド。
                // _commentAreaAnchor を直接読む（コルーチン不要）。
                Vector3 normalPos  = activeLookTarget != null ? activeLookTarget.position : transform.position + Vector3.forward;
                Vector3 commentPos = _commentAreaAnchor != null ? _commentAreaAnchor.position : normalPos;
                Vector3 gazePos    = Vector3.Lerp(normalPos, commentPos, _commentHeadBlend);
                _animator.SetLookAtPosition(gazePos + _saccadeOffset);
            }
            else
            {
                _animator.SetLookAtWeight(0f);
            }
        }

        // ── (A) Saccade – micro eye-movement for liveliness ───────────────────

        private void UpdateSaccade()
        {
            _saccadeTimer -= Time.deltaTime;
            if (_saccadeTimer <= 0f)
            {
                const float r = 0.015f; // ±1.5 cm amplitude
                _saccadeTargetOffset = new Vector3(
                    UnityEngine.Random.Range(-r,        r),
                    UnityEngine.Random.Range(-r * 0.4f, r * 0.4f),
                    0f);
                _saccadeTimer = UnityEngine.Random.Range(0.15f, 0.40f);
            }
            // Fast lerp so saccades feel snappy but not teleporting
            _saccadeOffset = Vector3.Lerp(_saccadeOffset, _saccadeTargetOffset,
                                          Time.deltaTime * 18f);
        }

        private void ReparentIfOrphan(Transform t)
        {
            if (t != null && t.parent == null)
                t.SetParent(transform, worldPositionStays: true);
        }

        // ── Test seams ─────────────────────────────────────────────────────────

        /// <summary>Current look target Transform. For tests only.</summary>
        public Transform CurrentLookAtTargetForTest => _currentLookAtTarget;

        /// <summary>Whether random look mode is active. For tests only.</summary>
        public bool IsRandomLookForTest => _isRandomLook;

        /// <summary>Whether comment gaze override is active. For tests only.</summary>
        public bool HasCommentGazeOverrideForTest => _hasCommentGazeOverride;

        /// <summary>Whether head gesture mode is active. For tests only.</summary>
        public bool IsHeadGestureActiveForTest => _isHeadGestureActive;

        /// <summary>Current saccade offset vector. For tests only.</summary>
        public Vector3 SaccadeOffsetForTest => _saccadeOffset;

        /// <summary>Injects an Animator for test-time IK calls. For tests only.</summary>
        public void SetAnimatorForTest(Animator animator) => _animator = animator;

        /// <summary>Injects look target Transforms. For tests only.</summary>
        public void SetLookTargetsForTest(Transform camera, Transform chat, Transform down)
        {
            _lookAtCamera = camera;
            _lookAtChat   = chat;
            _lookAtDown   = down;
        }
    }
}
