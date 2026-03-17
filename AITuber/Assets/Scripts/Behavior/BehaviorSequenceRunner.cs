// BehaviorSequenceRunner.cs
// Executes multi-step BehaviorSequences loaded from behaviors.json.
// Chains zone movement (NavMeshAgent), gestures, and waits as a Coroutine.
// #67: NavMeshAgent 一本化 — CharacterController 廃止。agent.SetDestination で歩行。
//
// SRS refs: FR-LIFE-01, FR-BEHAVIOR-SEQ-01, TD-012 (#36), TD-013 (#38)
//
// Setup:
//   1. Attach to the same GameObject as AvatarController (e.g. "AvatarRoot").
//   2. Assign _avatarController and _avatarRoot in Inspector.
//   3. AvatarRoot must have AvatarGrounding + NavMeshAgent.
//   4. Ensure BehaviorDefinitionLoader is present in the scene.
//
// Wire: { "cmd": "behavior_start", "params": { "behavior": "go_sleep" } }

using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.AI;
using AITuber.Avatar;

namespace AITuber.Behavior
{
    /// <summary>
    /// Executes named behavior sequences (walk_to, gesture, wait, zone_snap).
    /// Call <see cref="StartBehavior"/> to run a sequence by name.
    /// Any running sequence is cancelled when a new one starts.
    /// </summary>
    public class BehaviorSequenceRunner : MonoBehaviour
    {
        // ── Inspector ─────────────────────────────────────────────────────────

        [Header("依存コンポーネント")]
        [Tooltip("AvatarController — HandleMessage(json) を呼ぶために必要")]
        [SerializeField] private AvatarController _avatarController;

        [Tooltip("アバターの Root Transform — walk_to で位置を移動する")]
        [SerializeField] private Transform _avatarRoot;

        [Tooltip("behavior 実行中に 1 フレームでこの距離以上移動した場合、warp 診断ログを出す。")]
        [SerializeField] private float _warpDiagnosticThreshold = 0.50f;

        // ── Singleton ─────────────────────────────────────────────────────────

        public static BehaviorSequenceRunner Instance { get; private set; }

        // ── State ─────────────────────────────────────────────────────────────

        private Coroutine         _current;
        private string            _runningBehavior;
        private bool              _currentBehaviorSuccess;  // tracks step-level failures (L-5 / Issue #50)
        // CC reference kept here so StopBehavior can restore it even if the coroutine is cancelled mid-walk
        // (removed: CC/NavMeshAgent dual management — NavMeshAgent is the sole position owner #67)
        // Locomotion Animator — lazily cached; Unity null-check handles destroyed Animator (L-3 / review perf)
        private Animator            _locomotionAnimator;
        private readonly HashSet<string> _warpDiagnosticWarnings = new();
        private const int InitialWalkFrameDiagnostics = 12;
        private const float MaxSeatSupportDrop = 0.20f;
        private static readonly Vector3 DefaultStreamCameraOffset = new(0f, 1.45f, 0.95f);
        private Animator _visualDebugAnimator;
        private SkinnedMeshRenderer _visualDebugBodyRenderer;

        /// <summary>現在実行中の behavior 名。未実行なら null。</summary>
        public string RunningBehavior => _runningBehavior;

        /// <summary>シーケンス実行中なら true。</summary>
        public bool IsBusy => _current != null;

        // ── Unity lifecycle ───────────────────────────────────────────────────

        private void Awake()
        {
            if (Instance != null && Instance != this)
            {
                Destroy(this);
                return;
            }
            Instance = this;
        }

        private void OnDestroy()
        {
            if (Instance == this) Instance = null;
        }

        /// <summary>EditMode テスト用シングルトンクリア。</summary>
        public static void ClearInstanceForTest() => Instance = null;

        // ── Public API ────────────────────────────────────────────────────────

        /// <summary>
        /// Named behavior を開始する。実行中のシーケンスがあればキャンセルしてから開始。
        /// </summary>
        /// <param name="behaviorName">behaviors.json の "behavior" キー。</param>
        public void StartBehavior(string behaviorName)
        {
            var loader = BehaviorDefinitionLoader.Instance;
            var seq = loader != null ? loader.Lookup(behaviorName) : null;
            if (seq == null)
            {
                Debug.LogWarning($"[BehaviorRunner] Unknown behavior: '{behaviorName}'");
                return;
            }

            // Cancel in-progress sequence — reuse StopBehavior() so speed reset,
            // CC restore, and interrupted completion notification all fire correctly.
            // (Architecture review Round 2: aligned StartBehavior interrupt with StopBehavior)
            StopBehavior();

            _runningBehavior = behaviorName;
            _current = StartCoroutine(RunSequence(seq));
        }

        /// <summary>実行中のシーケンスを即時キャンセルする。</summary>
        public void StopBehavior()
        {
            if (_current != null)
            {
                StopCoroutine(_current);
                _current = null;
            }
            // Critical (review): Reset LocoBlend so walk animation does not persist after interruption.
            // Without this, speed=1 stays set indefinitely when StopBehavior cancels mid-walk.
            GetLocomotionAnimator()?.SetFloat("speed", 0f);
            // Stop NavMeshAgent if walking was interrupted (#67)
            StopAgentMovement();
            // Medium (review): notify orchestrator on interrupt, closes Perception-Memory-Action loop (L-5)
            if (!string.IsNullOrEmpty(_runningBehavior))
                PerceptionReporter.Instance?.ReportBehaviorCompleted(_runningBehavior, false, "interrupted");
            _runningBehavior = null;
            // R-1 fix: reset dedup cache so next behavior can re-fire the same gesture trigger.
            _avatarController?.ResetGestureDedup();
        }

        private void StopAgentMovement()
        {
            if (_avatarRoot == null) return;
            var grounding = _avatarRoot.GetComponent<AvatarGrounding>();
            if (grounding != null && grounding.Agent != null && grounding.Agent.enabled)
            {
                grounding.Agent.isStopped = true;
                grounding.Agent.ResetPath();
                grounding.Agent.velocity = Vector3.zero;
            }
        }

        /// <summary>
        /// Returns the Animator driving the avatar locomotion (the humanoid child Animator
        /// with a RuntimeAnimatorController). Skips AvatarRoot's own Animator which may be
        /// disabled or have no controller assigned. Null-safe. L-3 / Issue #49.
        /// </summary>
        private Animator GetLocomotionAnimator()
        {
            // Re-scan if cache is stale (null or lost its controller, e.g. VRM hot-reload).
            if (_locomotionAnimator == null
                || _locomotionAnimator.runtimeAnimatorController == null)
            {
                _locomotionAnimator = null;
                if (_avatarRoot != null)
                {
                    // Mirror AvatarGrounding.Awake(): skip AvatarRoot's own Animator,
                    // find the humanoid child that has an AnimatorController assigned.
                    foreach (var a in _avatarRoot.GetComponentsInChildren<Animator>(true))
                    {
                        if (a.gameObject == _avatarRoot.gameObject) continue;
                        if (a.runtimeAnimatorController != null) { _locomotionAnimator = a; break; }
                    }
                }
            }
            return _locomotionAnimator;
        }

        // ── Coroutine ─────────────────────────────────────────────────────────

        private IEnumerator RunSequence(BehaviorSequence seq)
        {
            _warpDiagnosticWarnings.Clear();
            _visualDebugAnimator = null;
            _visualDebugBodyRenderer = null;
            yield return WaitForAvatarReady();

            Debug.Log($"[BehaviorRunner] Start '{seq.behavior}' ({seq.display_name}" +
                      $") — {seq.steps?.Length ?? 0} step(s)");

            _currentBehaviorSuccess = true;  // reset before each run (L-5 / Issue #50)

            if (seq.steps != null)
            {
                foreach (var step in seq.steps)
                    yield return RunStep(step);
            }

            Debug.Log($"[BehaviorRunner] Finished '{seq.behavior}'");
            // Notify Python orchestrator: closes Perception-Memory-Action loop (L-5 / Issue #50)
            PerceptionReporter.Instance?.ReportBehaviorCompleted(seq.behavior, _currentBehaviorSuccess);
            _current = null;
            _runningBehavior = null;
        }

        private IEnumerator RunStep(BehaviorStep step)
        {
            Debug.Log($"[BehaviorRunner] Step '{step.type}' begin — pos={_avatarRoot?.position} {BuildVisualAnchorDebugString()}");
            switch (step.type)
            {
                case "walk_to":    yield return StepWalkTo(step);      break;
                case "face_toward": yield return StepFaceToward(step); break;  // L-2 / Issue #48
                case "gesture":    yield return StepGesture(step);     break;
                case "wait":       yield return StepWait(step);        break;
                case "zone_snap":  yield return StepZoneSnap(step);    break;
                case "sit_settle": yield return StepSitSettle(step);   break;
                case "camera_focus_avatar": yield return StepCameraFocusAvatar(step); break;
                default:
                    Debug.LogWarning($"[BehaviorRunner] Unknown step type: '{step.type}'");
                    break;
            }
            Debug.Log($"[BehaviorRunner] Step '{step.type}' end — pos={_avatarRoot?.position} {BuildVisualAnchorDebugString()}");
        }

        private IEnumerator WaitForAvatarReady()
        {
            float wait = 0f;
            const float timeout = 5f;

            while (wait < timeout)
            {
                bool snapping = false;
                if (_avatarRoot != null)
                {
                    var grounding = _avatarRoot.GetComponent<AvatarGrounding>();
                    snapping = grounding != null && grounding.IsSnapping;
                }

                var locomotionAnimator = GetLocomotionAnimator();
                bool animatorReady = locomotionAnimator != null
                    && locomotionAnimator.runtimeAnimatorController != null;

                if (!snapping && animatorReady)
                    yield break;

                wait += Time.deltaTime;
                yield return null;
            }

            var animator = GetLocomotionAnimator();
            Debug.LogWarning(
                $"[BehaviorRunner] avatar was not fully ready after {timeout:F1}s — proceeding anyway. " +
                $"avatarRoot={_avatarRoot != null} animatorReady={animator != null && animator.runtimeAnimatorController != null}");
        }

        // ── Step: walk_to ─────────────────────────────────────────────────────

        private IEnumerator StepWalkTo(BehaviorStep step)
        {
            if (string.IsNullOrEmpty(step.slot_id))
            {
                Debug.LogWarning("[BehaviorRunner] walk_to: slot_id is empty.");
                _currentBehaviorSuccess = false;
                yield break;
            }

            // Resolve target slot
            var origin = _avatarRoot != null ? _avatarRoot.position : Vector3.zero;
            var slot = InteractionSlot.FindNearest(step.slot_id, origin);
            if (slot == null)
            {
                Debug.LogWarning($"[BehaviorRunner] walk_to: no InteractionSlot found with slotId='{step.slot_id}'.");
                _currentBehaviorSuccess = false;
                yield break;
            }

            Debug.Log(
                $"[BehaviorRunner] walk_to '{slot.slotId}': resolved slot={GetTransformPath(slot.transform)} " +
                $"slotPos={slot.transform.position} standPos={slot.StandPosition} faceYaw={slot.faceYaw:F1}");

            // Wait for AvatarGrounding.BeginSnap to finish before walking.
            if (_avatarRoot != null)
            {
                var grounding = _avatarRoot.GetComponent<AvatarGrounding>();
                if (grounding != null && grounding.IsSnapping)
                {
                    float snapWait = 0f;
                    while (grounding.IsSnapping && snapWait < 5f)
                    {
                        snapWait += Time.deltaTime;
                        yield return null;
                    }
                    if (snapWait >= 5f)
                        Debug.LogWarning("[BehaviorRunner] walk_to: BeginSnap still running after 5 s — proceeding anyway.");
                }
            }

            // #67: NavMeshAgent 一本化 — EnableAgentOnNavMesh で agent を有効化し、
            // SetDestination で移動する。CC disable/enable や Lerp fallback は不要。
            var walkGrounding = _avatarRoot.GetComponent<AvatarGrounding>();
            if (walkGrounding == null)
            {
                Debug.LogWarning("[BehaviorRunner] walk_to: AvatarGrounding component not found.");
                _currentBehaviorSuccess = false;
                yield break;
            }

            // Smooth stand-up transition: if avatar is off NavMesh (e.g. seated on furniture),
            // Lerp to the nearest NavMesh point before enabling agent to avoid instant teleport.
            Vector3 preWalkPos = _avatarRoot.position;
            if (NavMesh.SamplePosition(preWalkPos, out NavMeshHit preWalkHit, 5f, NavMesh.AllAreas))
            {
                float distToNavMesh = Vector3.Distance(preWalkPos, preWalkHit.position);
                if (distToNavMesh > 0.15f)
                {
                    float standUpDuration = Mathf.Clamp(distToNavMesh / 1.5f, 0.25f, 1.0f);
                    float standUpElapsed = 0f;
                    Debug.Log($"[BehaviorRunner] walk_to '{slot.slotId}': smooth stand-up from {preWalkPos} to NavMesh {preWalkHit.position} ({distToNavMesh:F2}m, {standUpDuration:F2}s)");
                    while (standUpElapsed < standUpDuration)
                    {
                        float t = standUpElapsed / standUpDuration;
                        _avatarRoot.position = Vector3.Lerp(preWalkPos, preWalkHit.position, t);
                        standUpElapsed += Time.deltaTime;
                        yield return null;
                    }
                    _avatarRoot.position = preWalkHit.position;
                }
            }

            walkGrounding.EnableAgentOnNavMesh();
            var agent = walkGrounding.Agent;
            if (agent == null || !agent.enabled || !agent.isOnNavMesh)
            {
                Debug.LogWarning($"[BehaviorRunner] walk_to: NavMeshAgent is not on NavMesh. agent={agent != null} enabled={agent?.enabled} onNavMesh={agent?.isOnNavMesh}");
                _currentBehaviorSuccess = false;
                yield break;
            }

            // Resolve destination to nearest NavMesh point
            Vector3 dest = slot.StandPosition;
            if (NavMesh.SamplePosition(dest, out NavMeshHit destHit, 5f, NavMesh.AllAreas))
                dest = destHit.position;

            Debug.Log($"[BehaviorRunner] walk_to '{slot.slotId}': agent start={_avatarRoot.position} dest={dest}");

            // Play walk animation
            SendAvatarUpdate("walk", "neutral", "random");
            GetLocomotionAnimator()?.SetFloat("speed", 1f);

            // Navigate using NavMeshAgent
            agent.isStopped = false;
            agent.SetDestination(dest);

            // Wait for path to be computed
            yield return null;
            if (agent.pathStatus == NavMeshPathStatus.PathInvalid)
            {
                Debug.LogWarning($"[BehaviorRunner] walk_to '{slot.slotId}': invalid path — movement cancelled.");
                _currentBehaviorSuccess = false;
                GetLocomotionAnimator()?.SetFloat("speed", 0f);
                agent.isStopped = true;
                yield break;
            }

            // Poll until arrival
            const float arrivalThreshold = 0.20f;
            float timeout = Mathf.Max(step.duration * 3f, 30f);
            float elapsed = 0f;
            Vector3 previousPosition = _avatarRoot.position;
            int diagnosticFramesRemaining = InitialWalkFrameDiagnostics;

            while (elapsed < timeout)
            {
                // Face movement direction
                Vector3 vel = agent.velocity;
                vel.y = 0f;
                if (vel.sqrMagnitude > 0.01f)
                    _avatarRoot.rotation = Quaternion.LookRotation(vel.normalized);

                // Check arrival
                if (!agent.pathPending && agent.remainingDistance <= arrivalThreshold)
                    break;

                elapsed += Time.deltaTime;
                yield return null;

                if (diagnosticFramesRemaining > 0)
                {
                    float horizontalDelta = Vector2.Distance(
                        new Vector2(previousPosition.x, previousPosition.z),
                        new Vector2(_avatarRoot.position.x, _avatarRoot.position.z));
                    float verticalDelta = Mathf.Abs(_avatarRoot.position.y - previousPosition.y);
                    Debug.Log(
                        $"[BehaviorRunner] walk frame diagnostic: slot='{slot.slotId}' " +
                        $"prev={previousPosition} current={_avatarRoot.position} " +
                        $"horizontalDelta={horizontalDelta:F3} verticalDelta={verticalDelta:F3} remaining={agent.remainingDistance:F2} {BuildVisualAnchorDebugString()}");
                    diagnosticFramesRemaining--;
                }

                LogWarpDiagnostic(previousPosition, _avatarRoot.position, $"walk_to/{slot.slotId}");
                previousPosition = _avatarRoot.position;
            }

            if (elapsed >= timeout)
            {
                Debug.LogWarning($"[BehaviorRunner] walk_to '{slot.slotId}' timed out.");
                _currentBehaviorSuccess = false;
            }

            // Stop agent completely — isStopped alone causes deceleration slide
            agent.isStopped = true;
            agent.ResetPath();
            agent.velocity = Vector3.zero;
            _avatarRoot.rotation = slot.StandRotation;
            GetLocomotionAnimator()?.SetFloat("speed", 0f);
            Debug.Log($"[BehaviorRunner] walk_to '{step.slot_id}' done — AvatarRoot={_avatarRoot?.position}");
        }

        private static string GetTransformPath(Transform transform)
        {
            if (transform == null) return "(null)";

            var path = transform.name;
            var current = transform.parent;
            while (current != null)
            {
                path = current.name + "/" + path;
                current = current.parent;
            }

            return path;
        }

        // ── Step: face_toward ─────────────────────────────────────────────────

        /// <summary>
        /// Smoothly rotates the avatar to face an <see cref="InteractionSlot"/> over
        /// <see cref="BehaviorStep.duration"/> seconds before the subsequent walk_to step.
        /// VirtualHome atomic-action decomposition (Issue #48 / FR-BEHAVIOR-SEQ-01).
        /// </summary>
        private IEnumerator StepFaceToward(BehaviorStep step)
        {
            if (string.IsNullOrEmpty(step.slot_id))
            {
                Debug.LogWarning("[BehaviorRunner] face_toward: slot_id is empty.");
                _currentBehaviorSuccess = false;  // R4-1: step definition error must propagate
                yield break;
            }
            if (_avatarRoot == null)
            {
                Debug.LogWarning("[BehaviorRunner] face_toward: _avatarRoot is null — skip.");
                _currentBehaviorSuccess = false;  // R4-1: runtime init error must propagate
                yield break;
            }

            var slot = InteractionSlot.FindNearest(step.slot_id, _avatarRoot.position);
            if (slot == null)
            {
                Debug.LogWarning($"[BehaviorRunner] face_toward: no slot found for '{step.slot_id}'.");
                _currentBehaviorSuccess = false;  // R3-1: slot resolution failure must propagate to completion report
                yield break;
            }

            Vector3 dir = slot.StandPosition - _avatarRoot.position;
            dir.y = 0f;
            if (dir.sqrMagnitude < 0.001f) yield break;  // already at slot, no turn needed

            Quaternion targetRot = Quaternion.LookRotation(dir);
            Quaternion startRot  = _avatarRoot.rotation;
            Vector3 startPos = _avatarRoot.position;
            float      duration  = step.duration > 0f ? step.duration : 0.4f;
            float      elapsed   = 0f;

            while (elapsed < duration)
            {
                _avatarRoot.rotation = Quaternion.Slerp(startRot, targetRot, elapsed / duration);
                elapsed += Time.deltaTime;
                yield return null;
            }
            _avatarRoot.rotation = targetRot;
            LogWarpDiagnostic(startPos, _avatarRoot.position, $"face_toward/{step.slot_id}");
        }

        // ── Step: gesture ─────────────────────────────────────────────────────

        private IEnumerator StepGesture(BehaviorStep step)
        {
            SendAvatarUpdate(step.gesture, step.emotion, step.look_target);
            yield break;
        }

        // ── Step: wait ────────────────────────────────────────────────────────

        private IEnumerator StepWait(BehaviorStep step)
        {
            yield return new WaitForSeconds(Mathf.Max(step.duration, 0f));
        }

        // ── Step: zone_snap ───────────────────────────────────────────────────

        private IEnumerator StepZoneSnap(BehaviorStep step)
        {
            // #67: NavMeshAgent 一本化 — agent を無効化してスムーズに seat position へ移動。
            if (!string.IsNullOrEmpty(step.slot_id) && _avatarRoot != null)
            {
                var slot      = InteractionSlot.FindNearest(step.slot_id, _avatarRoot.position);
                if (slot != null)
                {
                    if (!TryFindSeatSupport(slot.StandPosition, out RaycastHit seatHit))
                    {
                        Debug.LogWarning(
                            $"[BehaviorRunner] zone_snap: skipped unsupported seat anchor at {slot.StandPosition} " +
                            $"(slot='{slot.slotId}'). Add a seat collider near the slot before using zone_snap.");
                        _avatarRoot.rotation = slot.StandRotation;
                        _currentBehaviorSuccess = false;
                        yield break;
                    }

                    Vector3 supportedPosition = slot.StandPosition;
                    supportedPosition.y = Mathf.Max(seatHit.point.y, slot.StandPosition.y);

                    // Disable agent before position transition
                    var grounding = _avatarRoot.GetComponent<AvatarGrounding>();
                    grounding?.DisableAgent();

                    // Smooth transition to seat position — duration scales with distance (~2 m/s)
                    Vector3 startPos = _avatarRoot.position;
                    Quaternion startRot = _avatarRoot.rotation;
                    Quaternion targetRot = slot.StandRotation;
                    float snapDistance = Vector3.Distance(startPos, supportedPosition);
                    float snapDuration = Mathf.Clamp(snapDistance / 2f, 0.2f, 0.8f);
                    float snapElapsed = 0f;
                    while (snapElapsed < snapDuration)
                    {
                        float t = snapElapsed / snapDuration;
                        _avatarRoot.position = Vector3.Lerp(startPos, supportedPosition, t);
                        _avatarRoot.rotation = Quaternion.Slerp(startRot, targetRot, t);
                        snapElapsed += Time.deltaTime;
                        yield return null;
                    }
                    _avatarRoot.position = supportedPosition;
                    _avatarRoot.rotation = targetRot;

                    Debug.Log($"[BehaviorRunner] zone_snap: → {supportedPosition} (slot='{slot.slotId}')");
                }
                else
                {
                    Debug.LogWarning($"[BehaviorRunner] zone_snap: no slot found for '{step.slot_id}'.");
                    _currentBehaviorSuccess = false;
                }
            }
        }

        // ── Step: sit_settle ───────────────────────────────────────────────

        /// <summary>
        /// 座りアニメーションのブレンド待機後、Hips ボーン実測 + Raycast で
        /// 座面高さを自動模索して AvatarRoot Y を補正。
        /// standOffset.y の手動チューニング帎。
        /// </summary>
        private IEnumerator StepSitSettle(BehaviorStep step)
        {
            if (_avatarRoot == null) yield break;

            var anim = GetLocomotionAnimator();
            if (anim == null) yield break;

            // Wait for sitting animation to blend in
            float blendWait = step.duration > 0f ? step.duration : 0.5f;
            yield return new WaitForSeconds(blendWait);

            if (!TryFindSeatSupport(_avatarRoot.position, out RaycastHit settledSeatHit))
            {
                Debug.LogWarning(
                    $"[BehaviorRunner] sit_settle: skipped Y correction because no seat support was found near {_avatarRoot.position}.");
                yield break;
            }

            var hip = anim.GetBoneTransform(HumanBodyBones.Hips);
            if (hip == null)
            {
                Debug.LogWarning("[BehaviorRunner] sit_settle: Hips bone not found — skip.");
                yield break;
            }

            // Measure hip height relative to root in the current sitting pose
            float hipAboveRoot = hip.position.y - _avatarRoot.position.y;

            // Raycast straight down from above the avatar to find the seating surface
            // (sofa cushion, chair, floor — whichever is directly below)
            Vector3 rayOrigin = new Vector3(_avatarRoot.position.x,
                                             hip.position.y + 0.5f,
                                             _avatarRoot.position.z);
            float rayLen    = hip.position.y + 1.0f;
            float surfaceY  = settledSeatHit.point.y;
            string surfName = settledSeatHit.collider != null ? settledSeatHit.collider.name : "(seat support)";
            if (Physics.Raycast(rayOrigin, Vector3.down, out RaycastHit hit, rayLen))
            {
                float seatDistance = Mathf.Abs(settledSeatHit.point.y - _avatarRoot.position.y);
                float hitDistance = Mathf.Abs(hit.point.y - _avatarRoot.position.y);
                if (hitDistance <= seatDistance + MaxSeatSupportDrop)
                {
                    surfaceY = hit.point.y;
                    surfName = hit.collider.name;
                }
            }

            // Target: hips sit 0.03 m above the surface
            float newRootY = (surfaceY + 0.03f) - hipAboveRoot;
            float minSupportedRootY = Mathf.Max(_avatarRoot.position.y, surfaceY);
            if (newRootY < minSupportedRootY)
            {
                Debug.LogWarning(
                    $"[BehaviorRunner] sit_settle: clamped root Y from {newRootY:F3} to seat-supported {minSupportedRootY:F3}.");
                newRootY = minSupportedRootY;
            }

            Debug.Log($"[BehaviorRunner] sit_settle: surface='{surfName}' Y={surfaceY:F3} " +
                      $"hipAboveRoot={hipAboveRoot:F3} → newRootY={newRootY:F3}");

            // Agent is already disabled by zone_snap — smooth Y correction to avoid visible warp
            Vector3 settleStart = _avatarRoot.position;
            Vector3 settleTarget = new Vector3(_avatarRoot.position.x, newRootY, _avatarRoot.position.z);
            const float settleDuration = 0.25f;
            float settleElapsed = 0f;
            while (settleElapsed < settleDuration)
            {
                float t = settleElapsed / settleDuration;
                _avatarRoot.position = Vector3.Lerp(settleStart, settleTarget, t);
                settleElapsed += Time.deltaTime;
                yield return null;
            }
            _avatarRoot.position = settleTarget;
        }

        private bool TryFindSeatSupport(Vector3 slotPosition, out RaycastHit seatHit)
        {
            Vector3 rayOrigin = slotPosition + Vector3.up * 0.25f;
            if (!Physics.Raycast(rayOrigin, Vector3.down, out seatHit, 0.75f, Physics.DefaultRaycastLayers, QueryTriggerInteraction.Ignore))
                return false;

            float drop = slotPosition.y - seatHit.point.y;
            return drop <= MaxSeatSupportDrop;
        }

        // ── Step: camera_focus_avatar ──────────────────────────────────────

        private IEnumerator StepCameraFocusAvatar(BehaviorStep step)
        {
            if (_avatarRoot == null)
            {
                Debug.LogWarning("[BehaviorRunner] camera_focus_avatar: avatarRoot is null.");
                _currentBehaviorSuccess = false;
                yield break;
            }

            var activeCamera = Camera.main;
            if (activeCamera == null)
            {
                Debug.LogWarning("[BehaviorRunner] camera_focus_avatar: Main Camera not found.");
                _currentBehaviorSuccess = false;
                yield break;
            }

            var localOffset = step.camera_local_offset == Vector3.zero
                ? DefaultStreamCameraOffset
                : step.camera_local_offset;
            float lookHeight = step.camera_target_height > 0f ? step.camera_target_height : 1.45f;
            float targetFov = step.camera_fov > 0f ? step.camera_fov : activeCamera.fieldOfView;

            Vector3 targetPosition = _avatarRoot.TransformPoint(localOffset);
            Vector3 lookTarget = _avatarRoot.position + Vector3.up * lookHeight;
            Vector3 forward = lookTarget - targetPosition;
            if (forward.sqrMagnitude < 0.0001f)
                forward = _avatarRoot.forward.sqrMagnitude > 0.0001f ? -_avatarRoot.forward : Vector3.back;

            Quaternion targetRotation = Quaternion.LookRotation(forward.normalized, Vector3.up);
            float duration = Mathf.Max(step.duration, 0f);
            if (duration <= 0.01f)
            {
                activeCamera.transform.SetPositionAndRotation(targetPosition, targetRotation);
                activeCamera.fieldOfView = targetFov;
                yield break;
            }

            Vector3 startPosition = activeCamera.transform.position;
            Quaternion startRotation = activeCamera.transform.rotation;
            float startFov = activeCamera.fieldOfView;
            float elapsed = 0f;

            while (elapsed < duration)
            {
                float t = elapsed / duration;
                activeCamera.transform.SetPositionAndRotation(
                    Vector3.Lerp(startPosition, targetPosition, t),
                    Quaternion.Slerp(startRotation, targetRotation, t));
                activeCamera.fieldOfView = Mathf.Lerp(startFov, targetFov, t);
                elapsed += Time.deltaTime;
                yield return null;
            }

            activeCamera.transform.SetPositionAndRotation(targetPosition, targetRotation);
            activeCamera.fieldOfView = targetFov;
        }

        private void SendAvatarUpdate(string gesture, string emotion, string lookTarget)
        {
            if (_avatarController == null)
            {
                Debug.LogWarning($"[BehaviorRunner] SendAvatarUpdate('{gesture}'): _avatarController is NULL — gesture will not fire.");
                return;
            }
            Debug.Log($"[BehaviorRunner] SendAvatarUpdate → gesture='{gesture}' locoAnim={GetLocomotionAnimator()?.gameObject.name ?? "NULL"}");
            // Bug fix (FR-BEHAVIOR-SEQ-01): Use ApplyBehaviorGesture instead of routing
            // through HandleMessage/HandleUpdate. HandleUpdate blocks gesture changes when
            // bsr.IsBusy==true to protect against orchestrator overrides, but that guard
            // was also silently dropping BSR's own walk/walk_stop triggers.
            _avatarController.ApplyBehaviorGesture(gesture, emotion, lookTarget);
        }

        private void LogWarpDiagnostic(Vector3 previousPosition, Vector3 currentPosition, string phase)
        {
            float horizontalDelta = Vector2.Distance(
                new Vector2(previousPosition.x, previousPosition.z),
                new Vector2(currentPosition.x, currentPosition.z));
            float verticalDelta = Mathf.Abs(currentPosition.y - previousPosition.y);
            if (horizontalDelta < _warpDiagnosticThreshold && verticalDelta < _warpDiagnosticThreshold)
                return;

            if (!_warpDiagnosticWarnings.Add(phase))
                return;

            Debug.LogWarning(
                $"[BehaviorRunner] warp diagnostic: phase='{phase}' prev={previousPosition} current={currentPosition} " +
                $"horizontalDelta={horizontalDelta:F2}m verticalDelta={verticalDelta:F2}m " +
                $"threshold={_warpDiagnosticThreshold:F2}m behavior='{_runningBehavior}' {BuildVisualAnchorDebugString()}");
        }

        private string BuildVisualAnchorDebugString()
        {
            if (_avatarRoot == null)
                return "visual=(avatarRoot:null)";

            var humanoidAnimator = _visualDebugAnimator;
            if (humanoidAnimator == null)
            {
                humanoidAnimator = GetLocomotionAnimator();
                if (humanoidAnimator == null)
                {
                    foreach (var animator in _avatarRoot.GetComponentsInChildren<Animator>(true))
                    {
                        if (animator.gameObject == _avatarRoot.gameObject || !animator.isHuman)
                            continue;

                        humanoidAnimator = animator;
                        break;
                    }
                }

                _visualDebugAnimator = humanoidAnimator;
            }

            var hips = humanoidAnimator != null ? humanoidAnimator.GetBoneTransform(HumanBodyBones.Hips) : null;

            var bodyRenderer = _visualDebugBodyRenderer;
            if (bodyRenderer == null)
            {
                float largestExtent = -1f;
                foreach (var renderer in _avatarRoot.GetComponentsInChildren<SkinnedMeshRenderer>(true))
                {
                    float extentMagnitude = renderer.bounds.extents.sqrMagnitude;
                    if (extentMagnitude > largestExtent)
                    {
                        largestExtent = extentMagnitude;
                        bodyRenderer = renderer;
                    }
                }

                _visualDebugBodyRenderer = bodyRenderer;
            }

            string hipsInfo = hips != null ? $"hips={hips.position}" : "hips=null";
            string rendererInfo = bodyRenderer != null
                ? $"bodyCenter={bodyRenderer.bounds.center} body='{bodyRenderer.name}'"
                : "bodyCenter=null";
            return $"visual=({hipsInfo}, {rendererInfo})";
        }
    }
}
