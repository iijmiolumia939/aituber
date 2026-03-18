using UnityEditor;
using UnityEngine;

public static class TriggerEatBehavior
{
    [MenuItem("AITuber/Debug/Trigger go_eat")]
    static void Trigger()
    {
        if (!Application.isPlaying) { Debug.LogWarning("Play mode only"); return; }
        var runner = Object.FindFirstObjectByType<AITuber.Behavior.BehaviorSequenceRunner>();
        if (runner != null) { runner.StartBehavior("go_eat"); Debug.Log("[Debug] go_eat triggered"); }
        else Debug.LogWarning("[Debug] BehaviorSequenceRunner not found");
    }

    [MenuItem("AITuber/Debug/Dump Sofa Geometry")]
    static void DumpSofaGeometry()
    {
        var sofa = GameObject.Find("Sofa03_1");
        if (sofa == null) { Debug.LogError("[SofaDump] Sofa03_1 not found."); return; }

        Debug.Log($"[SofaDump] Sofa03_1 worldPos={sofa.transform.position} localPos={sofa.transform.localPosition} parent='{sofa.transform.parent?.name}'");

        // Log all renderers with bounds
        foreach (var r in sofa.GetComponentsInChildren<Renderer>(true))
        {
            var b = r.bounds;
            Debug.Log($"[SofaDump] Renderer '{r.gameObject.name}' type={r.GetType().Name} center={b.center} min={b.min} max={b.max} size={b.size}");
        }

        // Log all colliders
        foreach (var c in sofa.GetComponentsInChildren<Collider>(true))
        {
            var b = c.bounds;
            Debug.Log($"[SofaDump] Collider '{c.gameObject.name}' type={c.GetType().Name} center={b.center} min={b.min} max={b.max} size={b.size}");
        }

        // Log children transforms
        foreach (Transform child in sofa.transform)
        {
            Debug.Log($"[SofaDump] Child '{child.name}' localPos={child.localPosition} worldPos={child.position}");
        }
    }
}