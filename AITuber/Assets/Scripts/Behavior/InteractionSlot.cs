// InteractionSlot.cs
// MonoBehaviour — marks an interaction position on a furniture or prop.
// Attach to a child GameObject of a bed / PC / chair / etc. and set slotId
// to match the "slot_id" value used in behaviors.json.
// SRS refs: FR-BEHAVIOR-SEQ-01

using UnityEngine;

namespace AITuber.Behavior
{
    /// <summary>
    /// Marks a world-space interaction position on a prop.
    /// The avatar walks (or snaps) to this slot when a behavior step uses the
    /// matching <see cref="slotId"/>.
    /// </summary>
    public class InteractionSlot : MonoBehaviour
    {
        [Tooltip("Slot identifier — must match 'slot_id' in behaviors.json " +
                 "(e.g. 'sleep', 'sit_work', 'eat', 'read')")]
        public string slotId;

        [Tooltip("Avatar stands at this LOCAL offset from the slot transform " +
                 "(default: directly at the transform)")]
        public Vector3 standOffset = Vector3.zero;

        [Tooltip("Avatar faces this world-Y rotation when using the slot. " +
                 "-1 = inherit the slot transform's own forward direction")]
        public float faceYaw = -1f;

        // ── Computed positions ────────────────────────────────────────────────

        /// <summary>World position where the avatar should stand.</summary>
        public Vector3 StandPosition =>
            transform.position + transform.TransformVector(standOffset);

        /// <summary>Avatar rotation at this slot.</summary>
        public Quaternion StandRotation =>
            faceYaw >= 0f
                ? Quaternion.Euler(0f, faceYaw, 0f)
                : Quaternion.Euler(0f, transform.eulerAngles.y, 0f);

        // ── Static finder ─────────────────────────────────────────────────────

        /// <summary>
        /// Find the nearest active <see cref="InteractionSlot"/> in the scene
        /// whose <see cref="slotId"/> matches <paramref name="id"/>.
        /// Returns <c>null</c> when no matching slot is found.
        /// </summary>
        public static InteractionSlot FindNearest(string id, Vector3 from)
        {
            if (string.IsNullOrEmpty(id)) return null;

            var all = FindObjectsByType<InteractionSlot>(FindObjectsSortMode.None);
            InteractionSlot best = null;
            float bestSqDist = float.MaxValue;

            foreach (var s in all)
            {
                if (!s.isActiveAndEnabled) continue;
                if (s.slotId != id)        continue;

                float sqDist = (s.StandPosition - from).sqrMagnitude;
                if (sqDist < bestSqDist)
                {
                    bestSqDist = sqDist;
                    best = s;
                }
            }

            return best;
        }

        // ── Gizmo ─────────────────────────────────────────────────────────────
#if UNITY_EDITOR
        private void OnDrawGizmosSelected()
        {
            Vector3 pos = StandPosition;
            Gizmos.color = Color.cyan;
            Gizmos.DrawSphere(pos, 0.08f);
            Gizmos.DrawLine(pos, pos + StandRotation * Vector3.forward * 0.4f);
            UnityEditor.Handles.Label(pos + Vector3.up * 0.18f,
                $"slot: {slotId}");
        }
#endif
    }
}
