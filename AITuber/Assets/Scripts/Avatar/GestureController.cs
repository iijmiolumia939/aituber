// GestureController.cs
// Extracted from AvatarController (Issue #52, Phase 1: God Object split).
// Owns Animator gesture trigger dispatch, deduplication, idle-alt initialisation,
// and breathing animation.
//
// SRS refs: FR-A7-01, FR-BEHAVIOR-SEQ-01
// Unity de facto: Animator parameter as SSoT for gesture state. No redundant flags.

using System.Collections;
using UnityEngine;

namespace AITuber.Avatar
{
    /// <summary>
    /// Gesture trigger dispatch, dedup tracking, and breathing.
    /// Attach to the same GameObject as AvatarController.
    /// Acquires the humanoid Animator via <see cref="GetComponentsInChildren{Animator}"/>
    /// in Awake() – same pattern as AvatarGrounding.
    /// </summary>
    public class GestureController : MonoBehaviour
    {
        private Animator  _animator;
        private string    _lastAppliedGesture = "none";
        private bool      _wasInGestureState;
        private float     _breathPhase;
        private Transform _breathBone;
        private string    _idleMotion = "default";

        // ── Lifecycle ────────────────────────────────────────────────

        private void Awake()
        {
            ResolveAnimator();
        }

        private void Start()
        {
            ResolveAnimator();

            // Cache chest bone once; LateUpdate guard handles null skeleton cases.
            if (_animator != null)
                _breathBone = _animator.GetBoneTransform(HumanBodyBones.Chest);

            // FR-A7-01: Play IdleAlt as the default pose once Animator is ready.
            StartCoroutine(PlayInitialIdleAlt());
        }

        private void OnDestroy() => StopAllCoroutines();

        private void Update()
        {
            ResolveAnimator();

            // ── Gesture→Idle 遷移検出: dedup tracker リセット ──
            // non-loop (gesture) → loop (Idle) への状態遷移を毎フレーム監視し、
            // 同一ジェスチャーが再度発動できるように dedup cache をリセットする。
            if (_animator == null || _animator.runtimeAnimatorController == null) return;
            bool inGesture = !_animator.GetCurrentAnimatorStateInfo(0).loop;
            ProcessDedupTransition(inGesture);
        }

        private void ProcessDedupTransition(bool inGesture)
        {
            if (_wasInGestureState && !inGesture && _lastAppliedGesture != "none")
            {
                Debug.Log($"[GestureCtrl] Gesture '{_lastAppliedGesture}' finished → resetting dedup tracker");
                _lastAppliedGesture = "none";
            }
            _wasInGestureState = inGesture;
        }

        private void LateUpdate()
        {
            // (C) Breathing: additive chest rotation on top of whatever Animator set this frame.
            // _breathBone is cached in Start(); null means skeleton has no Chest bone — skip.
            if (_animator == null || _breathBone == null) return;

            const float cycle   = 4.0f;  // seconds per breath cycle
            const float degrees = 0.6f;  // ±0.6° pitch on chest bone
            _breathPhase += Time.deltaTime * (Mathf.PI * 2f / cycle);
            float angle = Mathf.Sin(_breathPhase) * degrees;
            _breathBone.localRotation *= Quaternion.Euler(angle, 0f, 0f);
        }

        // ── Public API ───────────────────────────────────────────────

        /// <summary>
        /// Fire the Animator trigger for the given gesture.
        /// Deduplicated: same gesture in consecutive calls is suppressed to avoid
        /// rapid-repeat loops from consecutive avatar_update messages. FR-WS-01
        /// </summary>
        public void Apply(string gesture)
        {
            ResolveAnimator();

            if (_animator == null)
            {
                Debug.LogWarning("[GestureCtrl] Apply: _animator is NULL");
                return;
            }
            if (_animator.runtimeAnimatorController == null)
            {
                Debug.LogWarning($"[GestureCtrl] Apply: runtimeAnimatorController is NULL (gesture='{gesture}')");
                return;
            }
            if (gesture == "none")
            {
                _lastAppliedGesture = "none";
                return;
            }
            if (gesture == _lastAppliedGesture) return;
            _lastAppliedGesture = gesture;

            // Map gesture names to Animator triggers.
            // Trigger names match AnimationGenerator.cs AddOrUpdateGestureState().
            string trigger = gesture switch
            {
                // ── 既存ジェスチャー ──
                "nod"            => "Nod",
                "shake"          => "Shake",
                "wave"           => "Wave",
                "cheer"          => "Cheer",
                "shrug"          => "Shrug",
                "facepalm"       => "Facepalm",

                // ── 感情・リアクション系 ──
                "shy"            => "Shy",
                "laugh"          => "Laugh",
                "surprised"      => "Surprised",
                "rejected"       => "Rejected",
                "sigh"           => "Sigh",
                "thankful"       => "Thankful",

                // ── 悲しみ系 ──
                "sad_idle"       => "SadIdle",
                "sad_kick"       => "SadKick",

                // ── 思考系 ──
                "thinking"       => "Thinking",

                // ── 代替アイドル ──
                "idle_alt"       => "IdleAlt",

                // ── 座り系 ──
                "sit_down"       => "SitDown",
                "sit_idle"       => "SitIdle",
                "sit_laugh"      => "SitLaugh",
                "sit_clap"       => "SitClap",
                "sit_point"      => "SitPoint",
                "sit_disbelief"  => "SitDisbelief",
                "sit_kick"       => "SitKick",

                // ── M4: スタンドアップ追加ジェスチャー ──
                "bow"            => "Bow",
                "clap"           => "Clap",
                "thumbs_up"      => "ThumbsUp",
                "point_forward"  => "PointForward",
                "spin"           => "Spin",

                // ── M19: 日常生活 Sims-like (FR-LIFE-01) ──
                "walk"           => "Walk",
                "walk_stop"      => "WalkStop",
                "walk_stop_start"=> "WalkStopStart",
                "sit_read"       => "SitRead",
                "sit_eat"        => "SitEat",
                "sit_write"      => "SitWrite",
                "sleep_idle"     => "SleepIdle",
                "stretch"        => "Stretch",

                _                => null,
            };

            if (trigger != null)
            {
                Debug.Log($"[GestureCtrl] SetTrigger: gesture='{gesture}' → trigger='{trigger}'");
                _animator.SetTrigger(trigger);
#if UNITY_EDITOR
                if (gesture == "wave")
                    StartCoroutine(DiagnoseWaveBone());
#endif
            }
            else
            {
                Debug.LogWarning($"[GestureCtrl] Unknown gesture: '{gesture}'");
            }
        }

        /// <summary>
        /// Resets the dedup cache so the next identical gesture fires correctly.
        /// Call this when BSR cancels a behavior mid-execution (StopBehavior). FR-BEHAVIOR-SEQ-01
        /// </summary>
        public void ResetGestureDedup() => _lastAppliedGesture = "none";

        /// <summary>
        /// Apply the idle-motion config and drive the <c>IdleMotionIndex</c> Animator float.
        /// </summary>
        public void SetIdleMotion(string idleMotion)
        {
            _idleMotion = idleMotion ?? "default";
            ResolveAnimator();
            if (_animator != null)
                _animator.SetFloat("IdleMotionIndex", _idleMotion == "energetic" ? 1f : 0f);
        }

        /// <summary>Current idle motion name (for logging).</summary>
        public string IdleMotion => _idleMotion;

        // ── Internal helpers ──────────────────────────────────────────

        /// <summary>
        /// Wait for Animator initialisation then transition to IdleAlt as the default pose.
        /// Coroutine started from <see cref="Start"/> so it runs after scene setup.
        /// FR-A7-01: アイドル状態は IdleAlt (自然な立ちポーズ) を使用する.
        /// </summary>
        internal IEnumerator PlayInitialIdleAlt()
        {
            ResolveAnimator();

            // Animator が完全に初期化されるまで待つ（最大 30 フレーム = 約 0.5 秒）
            int safety = 30;
            while (_animator != null && !_animator.isInitialized && safety-- > 0)
                yield return null;
            yield return null; // 初期化直後のフレームをさらに 1 つスキップ
            if (_animator != null)
            {
                _animator.Play("IdleAlt", 0, 0f);
                _lastAppliedGesture = "idle_alt";
                Debug.Log("[GestureCtrl] Initial motion set to IdleAlt.");
            }
        }

        private void ResolveAnimator()
        {
            if (_animator != null && _animator.runtimeAnimatorController != null)
                return;

            Animator fallbackHuman = null;
            foreach (var animator in GetComponentsInChildren<Animator>(true))
            {
                if (!animator.isHuman)
                    continue;

                if (animator.runtimeAnimatorController != null)
                {
                    _animator = animator;
                    _breathBone = _animator.GetBoneTransform(HumanBodyBones.Chest);
                    return;
                }

                fallbackHuman ??= animator;
            }

            if (_animator == null)
            {
                _animator = fallbackHuman;
                if (_animator != null)
                    _breathBone = _animator.GetBoneTransform(HumanBodyBones.Chest);
            }
        }

#if UNITY_EDITOR
        private IEnumerator DiagnoseWaveBone()
        {
            var rightArm  = _animator.GetBoneTransform(HumanBodyBones.RightUpperArm);
            var rightHand = _animator.GetBoneTransform(HumanBodyBones.RightHand);
            float elapsed = 0f;
            int frame = 0;
            while (elapsed < 2f)
            {
                yield return null;
                elapsed += Time.deltaTime;
                frame++;
                if (frame % 10 == 0)
                {
                    var stateInfo = _animator.GetCurrentAnimatorStateInfo(0);
                    string armRot  = rightArm  != null ? rightArm.localEulerAngles.ToString("F1")  : "null";
                    string handRot = rightHand != null ? rightHand.localEulerAngles.ToString("F1") : "null";
                    Debug.Log($"[Wave診断] t={elapsed:F2}s frame={frame} state=loop:{stateInfo.loop} nTime={stateInfo.normalizedTime:F2} " +
                              $"RightUpperArm={armRot} RightHand={handRot}");
                }
            }
        }
#endif

        // ── Test seams ───────────────────────────────────────────────────────────

        /// <summary>Inject a pre-built Animator in tests that cannot set up a full humanoid rig.</summary>
        public void SetAnimatorForTest(Animator a) => _animator = a;

        /// <summary>Expose the selected Animator for assertions in tests.</summary>
        public Animator AnimatorForTest => _animator;

        /// <summary>Exposes dedup cache for assertions in tests.</summary>
        public string LastAppliedGestureForTest => _lastAppliedGesture;

        /// <summary>
        /// Drive the dedup-transition logic directly without a running Animator state machine.
        /// Equivalent to one <see cref="Update"/> tick with the given simulated loop state.
        /// </summary>
        public void SimulateDedupTransitionForTest(bool animatorLooping)
            => ProcessDedupTransition(!animatorLooping);

        // ── Animator setup (moved from AvatarController.Start, Issue #52) ──

        /// <summary>
        /// Assign AvatarAnimatorController and disable conflicting child Animators.
        /// Called from AvatarController.Start() after _animator is resolved. FR-A7-01.
        /// </summary>
        public void InitializeAnimator(Animator mainAnimator)
        {
            if (mainAnimator == null) return;
            _animator = mainAnimator;

            RuntimeAnimatorController ourCtrl = null;
            if (mainAnimator.runtimeAnimatorController != null
                && mainAnimator.runtimeAnimatorController.name == "AvatarAnimatorController")
            {
                ourCtrl = mainAnimator.runtimeAnimatorController;
                Debug.Log($"[GestureCtrl] Animator '{mainAnimator.gameObject.name}' already uses AvatarAnimatorController.");
            }
            else
            {
                var allCtrl = Resources.FindObjectsOfTypeAll<RuntimeAnimatorController>();
                foreach (var c in allCtrl)
                    if (c.name == "AvatarAnimatorController") { ourCtrl = c; break; }
                if (ourCtrl != null)
                {
                    var prev = mainAnimator.runtimeAnimatorController?.name ?? "none";
                    mainAnimator.runtimeAnimatorController = ourCtrl;
                    Debug.Log($"[GestureCtrl] Replaced controller '{prev}' -> 'AvatarAnimatorController' on '{mainAnimator.gameObject.name}'");
                }
                else
                    Debug.LogError("[GestureCtrl] AvatarAnimatorController not found! Gestures will not work.");
            }

            mainAnimator.applyRootMotion = false;

            // Disable conflicting child Animators (VRC HandsLayer/SittingLayer etc.)
            foreach (var a in GetComponentsInChildren<Animator>(true))
            {
                if (a == mainAnimator) continue;
                if (a.avatar != null && (a.runtimeAnimatorController == null
                    || a.runtimeAnimatorController.name != "AvatarAnimatorController"))
                {
                    a.enabled = false;
                    Debug.Log($"[GestureCtrl] Disabled conflicting Animator '{a.gameObject.name}' (ctrl='{a.runtimeAnimatorController?.name ?? "none"}').");
                }
            }
            var selfAnim = GetComponent<Animator>();
            if (selfAnim != null && selfAnim != mainAnimator && selfAnim.avatar != null
                && (selfAnim.runtimeAnimatorController == null
                    || selfAnim.runtimeAnimatorController.name != "AvatarAnimatorController"))
            {
                selfAnim.enabled = false;
                Debug.Log($"[GestureCtrl] Disabled conflicting self-Animator '{selfAnim.gameObject.name}'.");
            }
        }
    }
}
