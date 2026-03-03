using System.Collections.Generic;
using UnityEngine;
using UnityEditor;
using VRM;

/// <summary>
/// QuQu アバター用 VRM SpringBone 一括セットアップ
/// AITuber メニュー → Setup SpringBone (QuQu) から実行
/// </summary>
public static class SpringBoneSetup
{
    [MenuItem("AITuber/Setup SpringBone (QuQu)")]
    public static void Run()
    {
        var avatarRoot = GameObject.Find("AvatarRoot");
        if (avatarRoot == null)
        {
            Debug.LogError("[SpringBoneSetup] AvatarRoot が見つかりません。シーンを確認してください。");
            return;
        }

        // ── Step 1: コライダーをキーボーンに追加 ───────────────────
        // Head: 前髪にだけ使う。半径を小さくして過干渉を防ぐ
        SetCollider(avatarRoot, "Head",        new Vector3( 0,      0.03f, 0.0f),  0.055f);
        SetCollider(avatarRoot, "Neck",        new Vector3( 0,      0,     0),     0.045f);
        SetCollider(avatarRoot, "Chest",       new Vector3( 0,      0.05f, 0.02f), 0.10f);
        // 肩: ツインテールが肩を貫通しないようにカバー
        // Offset X で鎖骨〜肩峰ラインの中央に球を配置
        SetCollider(avatarRoot, "L_Shoulder",  new Vector3( 0.06f,  0,     0),     0.07f);
        SetCollider(avatarRoot, "R_Shoulder",  new Vector3(-0.06f,  0,     0),     0.07f);
        SetCollider(avatarRoot, "L_UpperArm",  new Vector3( 0.05f,  0,     0),     0.045f);
        SetCollider(avatarRoot, "R_UpperArm",  new Vector3(-0.05f,  0,     0),     0.045f);

        // ── Step 2: SpringBones ホスト作成 ─────────────────────────
        var sbHost = FindOrCreate(avatarRoot.transform, "SpringBones");

        var headCG   = GetCollider(avatarRoot, "Head");
        var neckCG   = GetCollider(avatarRoot, "Neck");
        var chestCG  = GetCollider(avatarRoot, "Chest");
        var lShldrCG = GetCollider(avatarRoot, "L_Shoulder");
        var rShldrCG = GetCollider(avatarRoot, "R_Shoulder");
        var lArmCG   = GetCollider(avatarRoot, "L_UpperArm");
        var rArmCG   = GetCollider(avatarRoot, "R_UpperArm");

        // 前髪: 頭+首だけ
        var headNeckOnly  = FilterNotNull(headCG, neckCG);
        // ツインテール: 首+両肩+上腕で「肩ライン」をカバー (Headは除外して跳ね防止)
        var sidHairColliders = FilterNotNull(neckCG, lShldrCG, rShldrCG, lArmCG, rArmCG);
        var allBody       = FilterNotNull(headCG, neckCG, chestCG, lShldrCG, rShldrCG, lArmCG, rArmCG);

        // ── Step 3: SpringBone グループ追加 ────────────────────────

        // 前髪: Head+Neck コライダーで頭への埋まり防止
        AddSpringBone(sbHost, "SpringBone_HairFront",
            new[] { "FrontA", "FrontB" },
            stiffness: 0.03f, gravity: 0.60f, drag: 0.65f, hitRadius: 0.03f,
            colliders: headNeckOnly, avatarRoot);

        // サイド髪(ツインテール): 首+肩+上腕で肩貫通を防止
        AddSpringBone(sbHost, "SpringBone_HairSide",
            new[] { "Side_L", "Side_R" },
            stiffness: 0.02f, gravity: 0.70f, drag: 0.65f, hitRadius: 0.03f,
            colliders: sidHairColliders, avatarRoot);

        // リボン: Neck コライダーのみ (頭球に当たらないようHead除外)
        AddSpringBone(sbHost, "SpringBone_Ribbon",
            new[] { "ribon", "ribon1_L", "ribon1_R" },
            stiffness: 0.08f, gravity: 0.40f, drag: 0.55f, hitRadius: 0.02f,
            colliders: FilterNotNull(neckCG), avatarRoot);

        // ボディ: 胸・お尻 (動きは控えめ)
        AddSpringBone(sbHost, "SpringBone_Body",
            new[] { "oppai_L", "oppai_R", "oshiri_L", "oshiri_R" },
            stiffness: 0.15f, gravity: 0.05f, drag: 0.80f, hitRadius: 0.04f,
            colliders: allBody, avatarRoot);

        EditorUtility.SetDirty(avatarRoot);

        Debug.Log("[SpringBoneSetup] 完了！ 4 グループ作成しました。\n" +
                  "  ・SpringBone_HairFront  (前髪)\n" +
                  "  ・SpringBone_HairSide   (サイド髪)\n" +
                  "  ・SpringBone_Ribbon     (リボン)\n" +
                  "  ・SpringBone_Body       (胸・お尻)\n" +
                  "パラメータは Inspector で調整してください。");
    }

    // ─────────────────────────────────────────────────────────────────

    static void SetCollider(GameObject avatarRoot, string boneName, Vector3 offset, float radius)
    {
        var bone = FindBone(avatarRoot.transform, boneName);
        if (bone == null) { Debug.LogWarning($"[SpringBoneSetup] ボーン未発見: {boneName}"); return; }

        var cg = bone.GetComponent<VRMSpringBoneColliderGroup>();
        if (cg == null)
            cg = bone.gameObject.AddComponent<VRMSpringBoneColliderGroup>();

        cg.Colliders = new[]
        {
            new VRMSpringBoneColliderGroup.SphereCollider { Offset = offset, Radius = radius }
        };
    }

    static VRMSpringBoneColliderGroup GetCollider(GameObject avatarRoot, string boneName)
    {
        var bone = FindBone(avatarRoot.transform, boneName);
        return bone == null ? null : bone.GetComponent<VRMSpringBoneColliderGroup>();
    }

    static VRMSpringBoneColliderGroup[] FilterNotNull(params VRMSpringBoneColliderGroup[] groups)
    {
        var list = new List<VRMSpringBoneColliderGroup>();
        foreach (var g in groups)
            if (g != null) list.Add(g);
        return list.ToArray();
    }

    static Transform FindOrCreate(Transform parent, string name)
    {
        var t = parent.Find(name);
        if (t != null) return t;
        var go = new GameObject(name);
        go.transform.SetParent(parent, false);
        return go.transform;
    }

    static void AddSpringBone(
        Transform host,
        string goName,
        string[] rootBoneNames,
        float stiffness,
        float gravity,
        float drag,
        float hitRadius,
        VRMSpringBoneColliderGroup[] colliders,
        GameObject avatarRoot)
    {
        // 既存を削除して作り直す
        var existing = host.Find(goName);
        if (existing != null) Object.DestroyImmediate(existing.gameObject);

        var go = new GameObject(goName);
        go.transform.SetParent(host, false);

        var sb = go.AddComponent<VRMSpringBone>();
        sb.m_comment        = goName;
        sb.m_stiffnessForce = stiffness;
        sb.m_gravityPower   = gravity;
        sb.m_gravityDir     = new Vector3(0, -1f, 0);
        sb.m_dragForce      = drag;
        sb.m_hitRadius      = hitRadius;
        sb.ColliderGroups   = colliders;

        foreach (var name in rootBoneNames)
        {
            var bone = FindBone(avatarRoot.transform, name);
            if (bone != null)
                sb.RootBones.Add(bone);
            else
                Debug.LogWarning($"[SpringBoneSetup] ルートボーン未発見: {name}");
        }
    }

    static Transform FindBone(Transform root, string name)
    {
        if (root.name == name) return root;
        foreach (Transform child in root)
        {
            var result = FindBone(child, name);
            if (result != null) return result;
        }
        return null;
    }
}
