// HairPhysicsSetup.cs — 一時セットアップ Editor スクリプト (Issue #31)
// AITuber メニュー → Setup Hair Physics Config から実行する。
// 実行後このファイルは削除して構わない。

using UnityEngine;
using UnityEditor;
using AITuber.Avatar;

public static class HairPhysicsSetup
{
    [MenuItem("AITuber/Reset Hair Physics to Defaults")]
    public static void ResetToDefaults()
    {
        const string assetPath = "Assets/Resources/HairPhysicsConfig.asset";
        var cfg = AssetDatabase.LoadAssetAtPath<HairPhysicsConfig>(assetPath);
        if (cfg == null) { Debug.LogError("[HairPhysicsSetup] HairPhysicsConfig.asset が見つかりません。先に Setup を実行してください。"); return; }

        var so = new SerializedObject(cfg);

        // ── 前髪 ──────────────────────────────────────────────────
        SetGroup(so, "front",  0.03f, 0.05f, 0.65f, 0.60f, 0.03f, 0.20f);
        // ── サイド ────────────────────────────────────────────────
        SetGroup(so, "side",   0.02f, 0.05f, 0.65f, 0.70f, 0.03f, 0.15f);
        // ── リボン ────────────────────────────────────────────────
        SetGroup(so, "ribbon", 0.08f, 0.05f, 0.55f, 0.40f, 0.02f, 0.10f);
        // ── ボディ ────────────────────────────────────────────────
        SetGroup(so, "body",   0.15f, 0.05f, 0.80f, 0.05f, 0.04f, 0.00f);

        so.ApplyModifiedProperties();
        EditorUtility.SetDirty(cfg);
        AssetDatabase.SaveAssets();

        // シーン内の Applicator にも即時反映
        var avatarRoot = GameObject.Find("AvatarRoot");
        if (avatarRoot != null)
        {
            var applicator = avatarRoot.GetComponent<HairPhysicsApplicator>();
            if (applicator != null) applicator.Apply();
        }
        Debug.Log("[HairPhysicsSetup] 推奨値にリセットしました。");
    }

    static void SetGroup(SerializedObject so, string field,
        float stiffness, float elasticity, float damping,
        float gravityY, float radius, float forceY)
    {
        var p = so.FindProperty(field);
        p.FindPropertyRelative("stiffness") .floatValue = stiffness;
        p.FindPropertyRelative("elasticity").floatValue = elasticity;
        p.FindPropertyRelative("damping")   .floatValue = damping;
        p.FindPropertyRelative("gravityY")  .floatValue = gravityY;
        p.FindPropertyRelative("radius")    .floatValue = radius;
        p.FindPropertyRelative("forceY")    .floatValue = forceY;
    }

    [MenuItem("AITuber/Setup Hair Physics Config")]
    public static void Run()
    {
        // ── アセット作成または値リセット ──────────────────────────
        const string assetPath = "Assets/Resources/HairPhysicsConfig.asset";

        var existing = AssetDatabase.LoadAssetAtPath<HairPhysicsConfig>(assetPath);
        if (existing == null)
        {
            existing = ScriptableObject.CreateInstance<HairPhysicsConfig>();
            AssetDatabase.CreateAsset(existing, assetPath);
            AssetDatabase.SaveAssets();
            Debug.Log("[HairPhysicsSetup] HairPhysicsConfig.asset を作成しました: " + assetPath);
        }
        else
        {
            // 既存アセットを推奨値にリセット（in-memory の変更を上書き）
            ResetToDefaults();
            Debug.Log("[HairPhysicsSetup] 既存の HairPhysicsConfig.asset を推奨値にリセットしました。");
        }

        // ── AvatarRoot にコンポーネントアサイン ───────────────────
        var avatarRoot = GameObject.Find("AvatarRoot");
        if (avatarRoot == null)
        {
            Debug.LogError("[HairPhysicsSetup] AvatarRoot が見つかりません。シーンを確認してください。");
            return;
        }

        var applicator = avatarRoot.GetComponent<HairPhysicsApplicator>();
        if (applicator == null)
            applicator = avatarRoot.AddComponent<HairPhysicsApplicator>();

        var so = new SerializedObject(applicator);
        so.FindProperty("_config").objectReferenceValue = existing;
        so.ApplyModifiedProperties();
        EditorUtility.SetDirty(applicator);

        // ── 即時適用（DynamicBone パラメータ書き込み）─────────────
        applicator.Apply();

        Debug.Log("[HairPhysicsSetup] 完了！ HairPhysicsApplicator に Config をアサインし Apply() を実行しました。");
    }
}
