using UnityEditor;
using UnityEngine;

public static class DiagAnimState
{
    [MenuItem("AITuber/Debug/Log Animator State")]
    static void LogState()
    {
        if (!Application.isPlaying) { Debug.LogWarning("Play mode only"); return; }
        var root = GameObject.Find("AvatarRoot");
        if (root == null) { Debug.LogError("AvatarRoot not found"); return; }

        Animator anim = null;
        foreach (var a in root.GetComponentsInChildren<Animator>(true))
        {
            if (a.gameObject != root && a.isHuman) { anim = a; break; }
        }
        if (anim == null) { Debug.LogError("No humanoid Animator"); return; }

        var info = anim.GetCurrentAnimatorStateInfo(0);
        string stateName = "unknown";
        foreach (var n in new[] {
            "Idle", "IdleAlt", "SitDown", "SitIdle", "Walk", "WalkStop",
            "WalkStart", "LocoBlend", "SitLaugh", "SitClap", "SitRead",
            "SitWrite", "SitEat", "WalkStopStart", "SleepIdle", "Stretch" })
        {
            if (info.IsName(n)) { stateName = n; break; }
        }

        var hip = anim.GetBoneTransform(HumanBodyBones.Hips);
        var lf  = anim.GetBoneTransform(HumanBodyBones.LeftFoot);
        var rf  = anim.GetBoneTransform(HumanBodyBones.RightFoot);

        Debug.Log($"[DiagAnim] state={stateName} normTime={info.normalizedTime:F2} " +
                  $"length={info.length:F2} loop={info.loop} " +
                  $"hips={hip?.position} lf={lf?.position} rf={rf?.position} " +
                  $"rootPos={root.transform.position}");
    }
}
