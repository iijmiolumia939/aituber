// SpringBoneSetup.cs
// QuQu アバター用 Dynamic Bone 一括セットアップ (FR-DB-01)
// UniVRM 依存を排除し Dynamic Bone (Asset Store) API を直接使用する。
//
// AITuber メニュー → Setup SpringBone (QuQu) から実行。
// 実行前にシーンに AvatarRoot GameObject が存在すること。

using System.Collections.Generic;
using UnityEngine;
using UnityEditor;

/// <summary>
/// QuQu アバター用 Dynamic Bone 一括セットアップ。
/// AITuber メニュー → Setup SpringBone (QuQu) から実行。
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

        // ── Step 1: DynamicBoneCollider をキーボーンに追加 ─────────
        // Head: 前髪にだけ使う。半径を小さくして過干渉を防ぐ
        SetCollider(avatarRoot, "Head",        new Vector3( 0,      0.03f, 0.0f),  0.055f);
        SetCollider(avatarRoot, "Neck",        new Vector3( 0,      0,     0),     0.045f);
        SetCollider(avatarRoot, "Chest",       new Vector3( 0,      0.05f, 0.02f), 0.10f);
        // 肩: ツインテールが肩を貫通しないようカバー
        SetCollider(avatarRoot, "L_Shoulder",  new Vector3( 0.06f,  0,     0),     0.07f);
        SetCollider(avatarRoot, "R_Shoulder",  new Vector3(-0.06f,  0,     0),     0.07f);
        SetCollider(avatarRoot, "L_UpperArm",  new Vector3( 0.05f,  0,     0),     0.045f);
        SetCollider(avatarRoot, "R_UpperArm",  new Vector3(-0.05f,  0,     0),     0.045f);

        // ── Step 2: SpringBones ホスト作成 ─────────────────────────
        var sbHost = FindOrCreate(avatarRoot.transform, "SpringBones");

        var headCol  = GetCollider(avatarRoot, "Head");
        var neckCol  = GetCollider(avatarRoot, "Neck");
        var chestCol = GetCollider(avatarRoot, "Chest");
        var lShldr   = GetCollider(avatarRoot, "L_Shoulder");
        var rShldr   = GetCollider(avatarRoot, "R_Shoulder");
        var lArm     = GetCollider(avatarRoot, "L_UpperArm");
        var rArm     = GetCollider(avatarRoot, "R_UpperArm");

        // 前髪: 頭+首だけ
        var headNeck  = FilterNotNull(headCol, neckCol);
        // ツインテール: 首+両肩+上腕で肩ラインをカバー
        var sideHair  = FilterNotNull(neckCol, lShldr, rShldr, lArm, rArm);
        var allBody   = FilterNotNull(headCol, neckCol, chestCol, lShldr, rShldr, lArm, rArm);

        // ── Step 3: DynamicBone グループ追加 ───────────────────────

        // 前髪: Head+Neck コライダーで頭への埋まり防止
        AddDynamicBone(sbHost, "SpringBone_HairFront",
            new[] { "FrontA", "FrontB" },
            stiffness: 0.03f, elasticity: 0.05f, damping: 0.65f, gravity: 0.60f, radius: 0.03f,
            colliders: headNeck, avatarRoot);

        // サイド髪 (ツインテール): 首+肩+上腕で肩貫通を防止
        AddDynamicBone(sbHost, "SpringBone_HairSide",
            new[] { "Side_L", "Side_R" },
            stiffness: 0.02f, elasticity: 0.05f, damping: 0.65f, gravity: 0.70f, radius: 0.03f,
            colliders: sideHair, avatarRoot);

        // リボン: Neck コライダーのみ (Head 球に当たらないよう Head 除外)
        AddDynamicBone(sbHost, "SpringBone_Ribbon",
            new[] { "ribon", "ribon1_L", "ribon1_R" },
            stiffness: 0.08f, elasticity: 0.05f, damping: 0.55f, gravity: 0.40f, radius: 0.02f,
            colliders: FilterNotNull(neckCol), avatarRoot);

        // ボディ: 胸・お尻 (動きは控えめ)
        AddDynamicBone(sbHost, "SpringBone_Body",
            new[] { "oppai_L", "oppai_R", "oshiri_L", "oshiri_R" },
            stiffness: 0.15f, elasticity: 0.05f, damping: 0.80f, gravity: 0.05f, radius: 0.04f,
            colliders: allBody, avatarRoot);

        EditorUtility.SetDirty(avatarRoot);

        Debug.Log("[SpringBoneSetup] 完了！ 4 グループ作成しました。\n" +
                  "  ・SpringBone_HairFront  (前髪)\n" +
                  "  ・SpringBone_HairSide   (サイド髪)\n" +
                  "  ・SpringBone_Ribbon     (リボン)\n" +
                  "  ・SpringBone_Body       (胸・お尻)\n" +
                  "パラメータは Inspector で調整してください。");
    }

    // ── Helpers ──────────────────────────────────────────────────────

    static void SetCollider(GameObject avatarRoot, string boneName, Vector3 center, float radius)
    {
        var bone = FindBone(avatarRoot.transform, boneName);
        if (bone == null) { Debug.LogWarning($"[SpringBoneSetup] ボーン未発見: {boneName}"); return; }

        // 既存コライダーを削除して作り直す
        var existing = bone.GetComponent<DynamicBoneCollider>();
        if (existing != null) Object.DestroyImmediate(existing);

        var col = bone.gameObject.AddComponent<DynamicBoneCollider>();
        col.m_Center = center;
        col.m_Radius = radius;
    }

    static DynamicBoneCollider GetCollider(GameObject avatarRoot, string boneName)
    {
        var bone = FindBone(avatarRoot.transform, boneName);
        return bone == null ? null : bone.GetComponent<DynamicBoneCollider>();
    }

    static DynamicBoneCollider[] FilterNotNull(params DynamicBoneCollider[] colliders)
    {
        var list = new List<DynamicBoneCollider>();
        foreach (var c in colliders)
            if (c != null) list.Add(c);
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

    static void AddDynamicBone(
        Transform host,
        string goName,
        string[] rootBoneNames,
        float stiffness,
        float elasticity,
        float damping,
        float gravity,
        float radius,
        DynamicBoneCollider[] colliders,
        GameObject avatarRoot)
    {
        // 既存を削除して作り直す
        var existing = host.Find(goName);
        if (existing != null) Object.DestroyImmediate(existing.gameObject);

        var go = new GameObject(goName);
        go.transform.SetParent(host, false);

        var db = go.AddComponent<DynamicBone>();
        db.m_Stiffness  = stiffness;
        db.m_Elasticity = elasticity;
        db.m_Damping    = damping;
        db.m_Gravity    = new Vector3(0, -gravity, 0);
        db.m_Radius     = radius;
        db.m_Colliders  = new List<DynamicBoneColliderBase>(colliders);

        // 複数ルートボーン: 最初を m_Root、残りを m_Roots
        db.m_Roots = new List<Transform>();
        bool first = true;
        foreach (var boneName in rootBoneNames)
        {
            var bone = FindBone(avatarRoot.transform, boneName);
            if (bone == null) { Debug.LogWarning($"[SpringBoneSetup] ルートボーン未発見: {boneName}"); continue; }
            if (first) { db.m_Root = bone; first = false; }
            else db.m_Roots.Add(bone);
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
