// BehaviorSequenceRunner.cs
// Executes multi-step BehaviorSequences loaded from behaviors.json.
// Chains zone movement (NavMeshAgent or Lerp fallback), gestures, and waits as a Coroutine.
//
// SRS refs: FR-LIFE-01, FR-BEHAVIOR-SEQ-01, TD-012 (#36), TD-013 (#38)
//
// Setup:
//   1. Attach to the same GameObject as AvatarController (e.g. "AvatarRoot").
//   2. Assign _avatarController and _avatarRoot in Inspector.
//   3. Optionally assign _navMeshAgent (or add NavMeshAgent to AvatarRoot) for
//      collision-aware movement. Falls back to linear Lerp when not assigned.
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

        [Tooltip("NavMeshAgent (optional) — 設定するとコリジョン回避移動が有効になる。未設定の場合は線形 Lerp へフォールバック。")]
        [SerializeField] private NavMeshAgent _navMeshAgent;

        [Tooltip("NavMesh 経路が取れない場合に、壁抜けの可能性がある直線 Lerp fallback を許可する。通常は OFF。")]
        [SerializeField] private bool _allowUnsafeLerpFallback = false;

        [Tooltip("behavior 実行中に 1 フレームでこの距離以上移動した場合、warp 診断ログを出す。")]
        [SerializeField] private float _warpDiagnosticThreshold = 0.50f;

        // ── Singleton ─────────────────────────────────────────────────────────

        public static BehaviorSequenceRunner Instance { get; private set; }

        // ── State ─────────────────────────────────────────────────────────────

        private Coroutine         _current;
        private string            _runningBehavior;
        private bool              _currentBehaviorSuccess;  // tracks step-level failures (L-5 / Issue #50)
        // CC reference kept here so StopBehavior can restore it even if the coroutine is cancelled mid-walk
        private CharacterController _walkingCC;
        // NavMeshAgent reference — enabled for walking, disabled for idle (avoids CC+agent transform conflict)
        private NavMeshAgent        _walkingAgent;
        // Locomotion Animator — lazily cached; Unity null-check handles destroyed Animator (L-3 / review perf)
        private Animator            _locomotionAnimator;
        private readonly HashSet<string> _warpDiagnosticWarnings = new();
        private const int InitialWalkFrameDiagnostics = 12;
        private const float MaxSeatSupportDrop = 0.20f;
        private const float WalkStartElevationProjectionThreshold = 0.30f;
        private const float WalkStartProjectionPreserveXZThreshold = 0.15f;
        private const float WalkStartProjectionDuration = 0.18f;
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
            // Restore CharacterController and disable NavMeshAgent if stopped mid-walk
            RestoreCharacterController();
            // Medium (review): notify orchestrator on interrupt, closes Perception-Memory-Action loop (L-5)
            if (!string.IsNullOrEmpty(_runningBehavior))
                PerceptionReporter.Instance?.ReportBehaviorCompleted(_runningBehavior, false, "interrupted");
            _runningBehavior = null;
            // R-1 fix: reset dedup cache so next behavior can re-fire the same gesture trigger.
            // Without this, an interrupted "walk" would leave the cache at "walk" and the
            // following walk_to step would be silently skipped by AvatarController's dedup guard.
            _avatarController?.ResetGestureDedup();
        }

        private void RestoreCharacterController()
        {
            // Phase 2: _walkingCC is never set (CC stays enabled during walk), so this is a no-op.
            if (_walkingCC != null)
            {
                _walkingCC.enabled = true;
                _walkingCC = null;
            }
            // Disable NavMeshAgent after walk — CC resumes sole ownership of gravity/movement.
            if (_walkingAgent != null)
            {
                _walkingAgent.enabled = false;
                _walkingAgent = null;
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
                _currentBehaviorSuccess = false;  // R3-1: step failure must propagate to completion report
                yield break;
            }

            // Resolve target slot
            var origin = _avatarRoot != null ? _avatarRoot.position : Vector3.zero;
            var slot = InteractionSlot.FindNearest(step.slot_id, origin);
            if (slot == null)
            {
                Debug.LogWarning($"[BehaviorRunner] walk_to: no InteractionSlot found with slotId='{step.slot_id}'.");
                _currentBehaviorSuccess = false;  // R3-1: slot resolution failure must propagate to completion report
                yield break;
            }

            Debug.Log(
                $"[BehaviorRunner] walk_to '{slot.slotId}': resolved slot={GetTransformPath(slot.transform)} " +
                $"slotPos={slot.transform.position} standPos={slot.StandPosition} faceYaw={slot.faceYaw:F1}");

            // Wait for AvatarGrounding.BeginSnap (state machine) to finish landing before walking.
            // If walk_to starts while snap is still in progress (e.g. room-switch or initial
            // floor-fall), disabling CC will block the snap landing, causing the avatar to
            // stay 3 m above the floor and walk on nothing.
            // Safety cap: 5 s max — if IsSnapping stays true due to an unexpected error we
            // do not block the behavior forever.
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

            // Phase 2: CC stays enabled so AvatarGrounding gravity continues throughout the walk.
            // Agent uses updatePosition=false — CC owns the transform; agent provides path/desiredVelocity.
            // _walkingCC is intentionally not set here; RestoreCharacterController is a no-op for CC.
            // (avatar-motion-roadmap.md Phase 2)

            // Recovery: if avatar is elevated above NavMesh floor (e.g. after zone_snap to sofa seat),
            // teleport to the nearest NavMesh floor position before attempting pathfinding.
            // Without this, walk_to fails with "source projection drift too large" or the CC
            // collides with sofa geometry, making the behavior appear stuck ("invalid").
            if (_avatarRoot != null)
            {
                float avatarY = _avatarRoot.position.y;
                if (NavMesh.SamplePosition(_avatarRoot.position, out NavMeshHit floorHit, 2f, NavMesh.AllAreas))
                {
                    float elevationAboveNavMesh = avatarY - floorHit.position.y;
                    if (elevationAboveNavMesh > WalkStartElevationProjectionThreshold)
                    {
                        float horizontalProjectionDrift = Vector2.Distance(
                            new Vector2(_avatarRoot.position.x, _avatarRoot.position.z),
                            new Vector2(floorHit.position.x, floorHit.position.z));
                        Debug.Log($"[BehaviorRunner] walk_to: avatar elevated {elevationAboveNavMesh:F2}m above NavMesh " +
                                  $"(pos={_avatarRoot.position}, navMesh={floorHit.position}, horizontalDrift={horizontalProjectionDrift:F2}) — projecting to floor first.");
                        var grounding = _avatarRoot.GetComponent<AITuber.Avatar.AvatarGrounding>();
                        Vector3 targetWalkStart = horizontalProjectionDrift <= WalkStartProjectionPreserveXZThreshold
                            ? new Vector3(_avatarRoot.position.x, floorHit.position.y, _avatarRoot.position.z)
                            : floorHit.position;

                        yield return SmoothProjectAvatarToWalkStart(targetWalkStart, WalkStartProjectionDuration);

                        if (grounding != null && !grounding.IsSnapping)
                        {
                            grounding.BeginSnap();
                            float dropWait = 0f;
                            while (grounding.IsSnapping && dropWait < 3f)
                            {
                                dropWait += Time.deltaTime;
                                yield return null;
                            }
                        }
                    }
                }
            }

            Vector3 dest = slot.StandPosition;
            Vector3 actualStart = _avatarRoot.position;
            bool canWalk = TryBuildReachableWalkPath(actualStart, slot, out Vector3 src, out dest, out NavMeshPath path, out string pathReason);

            if (canWalk || _allowUnsafeLerpFallback)
            {
                // Play walk animation only when an actual move will happen.
                SendAvatarUpdate("walk", "neutral", "random");
                GetLocomotionAnimator()?.SetFloat("speed", 1f);
            }

            if (canWalk)
            {
                Debug.Log(
                    $"[BehaviorRunner] walk_to '{slot.slotId}': actualStart={actualStart} navmeshStart={src} " +
                    $"dest={dest} pathCorners={path.corners.Length} ({pathReason})");
                yield return StepWalkAlongPath(path.corners, slot, step.duration);
            }
            else if (_allowUnsafeLerpFallback)
            {
                Debug.LogWarning(
                    $"[BehaviorRunner] walk_to '{slot.slotId}': {pathReason} — unsafe Lerp fallback enabled. " +
                    "gap_category=locomotion_lerp_unverified (Issue #47)");
                _currentBehaviorSuccess = false;
                yield return StepWalkToLerp(step, slot);
            }
            else
            {
                Debug.LogWarning(
                    $"[BehaviorRunner] walk_to '{slot.slotId}': {pathReason} — movement cancelled to avoid wall clipping.");
                _currentBehaviorSuccess = false;
            }

            // Restore CharacterController and stop walk blend (L-3 / Issue #49)
            GetLocomotionAnimator()?.SetFloat("speed", 0f);
            RestoreCharacterController();
            Debug.Log($"[BehaviorRunner] walk_to '{step.slot_id}' done — AvatarRoot={_avatarRoot?.position}");
        }

        private IEnumerator SmoothProjectAvatarToWalkStart(Vector3 targetPosition, float duration)
        {
            if (_avatarRoot == null)
                yield break;

            var cc = _avatarRoot.GetComponent<CharacterController>();
            Vector3 startPosition = _avatarRoot.position;
            if (Vector3.Distance(startPosition, targetPosition) <= 0.001f)
                yield break;

            if (cc != null)
                cc.enabled = false;

            float elapsed = 0f;
            float safeDuration = Mathf.Max(duration, 0.01f);
            while (elapsed < safeDuration)
            {
                float t = elapsed / safeDuration;
                _avatarRoot.position = Vector3.Lerp(startPosition, targetPosition, t);
                elapsed += Time.deltaTime;
                yield return null;
            }

            _avatarRoot.position = targetPosition;

            if (cc != null)
                cc.enabled = true;
        }

        private bool TryBuildReachableWalkPath(
            Vector3 actualStart,
            InteractionSlot slot,
            out Vector3 navMeshStart,
            out Vector3 navMeshDest,
            out NavMeshPath bestPath,
            out string reason)
        {
            navMeshStart = actualStart;
            navMeshDest = slot.StandPosition;
            bestPath = null;
            reason = "path search not evaluated";

            if (!NavMesh.SamplePosition(actualStart, out NavMeshHit sh, 1.5f, NavMesh.AllAreas))
            {
                reason = $"no NavMesh near start actual={actualStart}";
                return false;
            }

            navMeshStart = sh.position;

            float srcProjectionDrift = Vector2.Distance(
                new Vector2(actualStart.x, actualStart.z),
                new Vector2(navMeshStart.x, navMeshStart.z));
            if (srcProjectionDrift > 0.5f)
            {
                reason = $"source projection drift too large ({srcProjectionDrift:F2}m) actual={actualStart} navmesh={navMeshStart}";
                return false;
            }

            float bestScore = float.MaxValue;
            foreach (Vector3 desired in BuildWalkTargetCandidates(slot))
            {
                foreach (float radius in new[] { 0.5f, 1f, 2f, 3.5f, 5f })
                {
                    if (!NavMesh.SamplePosition(desired, out NavMeshHit dh, radius, NavMesh.AllAreas))
                        continue;

                    var path = new NavMeshPath();
                    if (!NavMesh.CalculatePath(navMeshStart, dh.position, NavMesh.AllAreas, path)
                        || path.status != NavMeshPathStatus.PathComplete)
                        continue;

                    float score = Vector3.Distance(dh.position, slot.StandPosition) + GetPathLength(path) * 0.1f;
                    if (score < bestScore)
                    {
                        bestScore = score;
                        navMeshDest = dh.position;
                        bestPath = path;
                        reason = $"candidate={desired} sampleRadius={radius:F1} slotDist={Vector3.Distance(dh.position, slot.StandPosition):F2}";
                    }

                    break;
                }
            }

            if (bestPath != null)
                return true;

            reason = $"no complete NavMesh path near slot standPos={slot.StandPosition}";
            return false;
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

        private IEnumerable<Vector3> BuildWalkTargetCandidates(InteractionSlot slot)
        {
            Vector3 basePos = slot.StandPosition;
            Quaternion rot = slot.StandRotation;

            yield return basePos;

            var directions = new[]
            {
                rot * Vector3.back,
                rot * Vector3.forward,
                rot * Vector3.left,
                rot * Vector3.right,
                (rot * (Vector3.back + Vector3.left)).normalized,
                (rot * (Vector3.back + Vector3.right)).normalized,
                (rot * (Vector3.forward + Vector3.left)).normalized,
                (rot * (Vector3.forward + Vector3.right)).normalized,
            };

            foreach (float distance in new[] { 0.35f, 0.7f, 1.1f, 1.5f })
            {
                foreach (Vector3 direction in directions)
                    yield return basePos + direction * distance;
            }
        }

        private static float GetPathLength(NavMeshPath path)
        {
            float length = 0f;
            var corners = path.corners;
            for (int i = 1; i < corners.Length; i++)
                length += Vector3.Distance(corners[i - 1], corners[i]);
            return length;
        }

        /// <summary>
        /// NavMesh パスのコーナーを CC + RequestHorizontalMove で追従する。
        /// NavMeshAgent の enable/disable は一切行わない → transform スナップなし。
        /// </summary>
        private IEnumerator StepWalkAlongPath(Vector3[] corners, InteractionSlot slot, float expectedDuration)
        {
            if (_avatarRoot == null || corners.Length < 2) yield break;

            var grounding = _avatarRoot.GetComponent<AvatarGrounding>();
            const float walkSpeed   = 1.5f;  // m/s — human walk
            const float cornerReach = 0.15f; // m — corner reached threshold
            float timeout = Mathf.Max(expectedDuration * 3f, 30f);
            float elapsed = 0f;
            Vector3 previousPosition = _avatarRoot.position;
            int diagnosticFramesRemaining = InitialWalkFrameDiagnostics;

            for (int i = 1; i < corners.Length && elapsed < timeout; i++)
            {
                Vector3 corner = corners[i];
                while (elapsed < timeout)
                {
                    float dx = corner.x - _avatarRoot.position.x;
                    float dz = corner.z - _avatarRoot.position.z;
                    if (dx * dx + dz * dz < cornerReach * cornerReach) break; // corner reached

                    Vector3 dir = new Vector3(dx, 0f, dz).normalized;
                    grounding?.RequestHorizontalMove(dir * walkSpeed);
                    _avatarRoot.rotation = Quaternion.LookRotation(dir);

                    elapsed += Time.deltaTime;
                    yield return null;

                    if (diagnosticFramesRemaining > 0)
                    {
                        float horizontalDelta = Vector2.Distance(
                            new Vector2(previousPosition.x, previousPosition.z),
                            new Vector2(_avatarRoot.position.x, _avatarRoot.position.z));
                        float verticalDelta = Mathf.Abs(_avatarRoot.position.y - previousPosition.y);
                        Debug.Log(
                            $"[BehaviorRunner] walk frame diagnostic: slot='{slot.slotId}' corner={i} " +
                            $"prev={previousPosition} current={_avatarRoot.position} " +
                            $"horizontalDelta={horizontalDelta:F3} verticalDelta={verticalDelta:F3} {BuildVisualAnchorDebugString()}");
                        diagnosticFramesRemaining--;
                    }

                    LogWarpDiagnostic(previousPosition, _avatarRoot.position, $"walk_to/{slot.slotId}/corner{i}");
                    previousPosition = _avatarRoot.position;
                }
            }

            if (elapsed >= timeout)
            {
                Debug.LogWarning($"[BehaviorRunner] walk path to '{slot.slotId}' timed out.");
                _currentBehaviorSuccess = false;
            }
            _avatarRoot.rotation = slot.StandRotation;
        }

        /// <summary>
        /// Linear-Lerp walk fallback when NavMeshAgent is unavailable.
        /// Phasing through walls is possible — bake NavMesh to avoid this.
        /// </summary>
        private IEnumerator StepWalkToLerp(BehaviorStep step, InteractionSlot slot)
        {
            if (_avatarRoot == null)
            {
                // R5-1: _avatarRoot null means locomotion is impossible — flag failure for consistency
                _currentBehaviorSuccess = false;
                yield return new WaitForSeconds(Mathf.Max(step.duration, 0.1f));
                yield break;
            }

            // Medium (review, L-1): NavMeshAgent unavailable — full Affordance Check cannot run.
            // SamplePosition provides a best-effort reachability hint only; walls are not avoided.
            // Bake a NavMesh and assign NavMeshAgent to enable complete check (Issue #47).
            if (!NavMesh.SamplePosition(slot.StandPosition, out _, 1f, NavMesh.AllAreas))
                Debug.LogWarning(
                    $"[BehaviorRunner] walk_to Lerp '{slot.slotId}': destination not found on NavMesh — " +
                    "gap_category=locomotion_lerp_unverified (Issue #47)");

            Vector3    startPos = _avatarRoot.position;
            Quaternion startRot = _avatarRoot.rotation;
            // Strip Y from slot.StandPosition: Lerp moves on the floor, not to furniture height.
            // (Warp-fix Phase 3: consistent with NavMesh path which also targets floor Y.) (#warp-bug)
            Vector3    endPos   = new Vector3(slot.StandPosition.x, startPos.y, slot.StandPosition.z);
            Quaternion endRot   = slot.StandRotation;

            // Orient toward destination at start of walk
            Vector3 dir = endPos - startPos;
            dir.y = 0f;
            if (dir.sqrMagnitude > 0.001f)
            {
                startRot = Quaternion.LookRotation(dir);
                _avatarRoot.rotation = startRot;
            }

            float duration = Mathf.Max(step.duration, 0.1f);
            float elapsed  = 0f;
            while (elapsed < duration)
            {
                elapsed += Time.deltaTime;
                float t = Mathf.Clamp01(elapsed / duration);
                _avatarRoot.position = Vector3.Lerp(startPos, endPos, t);
                _avatarRoot.rotation = Quaternion.Slerp(startRot, endRot, t);
                yield return null;
            }

            // Snap to exact slot values
            _avatarRoot.position = endPos;
            _avatarRoot.rotation = endRot;
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
            // Teleport directly onto the slot anchor and keep gravity active.
            // Seat stability should come from chair/sofa colliders, not from gravity suspension.
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

                    var cc        = _avatarRoot.GetComponent<CharacterController>();
                    Vector3 supportedPosition = slot.StandPosition;
                    supportedPosition.y = ComputeSupportedRootY(cc, seatHit.point.y, slot.StandPosition.y);

                    if (cc != null) cc.enabled = false;
                    _avatarRoot.position = supportedPosition;
                    _avatarRoot.rotation = slot.StandRotation;
                    if (cc != null) cc.enabled = true;

                    Debug.Log($"[BehaviorRunner] zone_snap: → {supportedPosition} (slot='{slot.slotId}') — gravity active.");
                }
                else
                {
                    Debug.LogWarning($"[BehaviorRunner] zone_snap: no slot found for '{step.slot_id}'.");
                    _currentBehaviorSuccess = false;
                }
            }
            yield break;
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

            // Target: hips sit 0.03 m above the surface, but never below the seat support
            // already established by zone_snap / CharacterController support alignment.
            float newRootY = (surfaceY + 0.03f) - hipAboveRoot;
            var cc = _avatarRoot.GetComponent<CharacterController>();
            float minSupportedRootY = ComputeSupportedRootY(cc, surfaceY, _avatarRoot.position.y);
            if (newRootY < minSupportedRootY)
            {
                Debug.LogWarning(
                    $"[BehaviorRunner] sit_settle: clamped root Y from {newRootY:F3} to seat-supported {minSupportedRootY:F3}.");
                newRootY = minSupportedRootY;
            }

            Debug.Log($"[BehaviorRunner] sit_settle: surface='{surfName}' Y={surfaceY:F3} " +
                      $"hipAboveRoot={hipAboveRoot:F3} → newRootY={newRootY:F3}");

            if (cc != null) cc.enabled = false;
            _avatarRoot.position = new Vector3(_avatarRoot.position.x, newRootY, _avatarRoot.position.z);
            if (cc != null) cc.enabled = true;
        }

        private bool TryFindSeatSupport(Vector3 slotPosition, out RaycastHit seatHit)
        {
            Vector3 rayOrigin = slotPosition + Vector3.up * 0.25f;
            if (!Physics.Raycast(rayOrigin, Vector3.down, out seatHit, 0.75f, Physics.DefaultRaycastLayers, QueryTriggerInteraction.Ignore))
                return false;

            float drop = slotPosition.y - seatHit.point.y;
            return drop <= MaxSeatSupportDrop;
        }

        private static float ComputeSupportedRootY(CharacterController characterController, float supportSurfaceY, float fallbackRootY)
        {
            if (characterController == null)
                return Mathf.Max(fallbackRootY, supportSurfaceY);

            float controllerBottomOffset = characterController.center.y - (characterController.height * 0.5f);
            float clearance = Mathf.Max(characterController.skinWidth, 0.01f);
            float supportedRootY = supportSurfaceY - controllerBottomOffset + clearance;
            return Mathf.Max(fallbackRootY, supportedRootY);
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
