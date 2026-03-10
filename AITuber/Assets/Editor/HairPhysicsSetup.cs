// HairPhysicsSetup.cs — 一時セットアップ Editor スクリプト (Issue #31)
// AITuber メニュー → Setup Hair Physics Config から実行する。
// 実行後このファイルは削除して構わない。

using UnityEngine;
using UnityEditor;
using AITuber.Avatar;

public static class HairPhysicsSetup
{
    [MenuItem("AITuber/Setup Hair Physics Config")]
    public static void Run()
    {
        // ── アセット作成 ──────────────────────────────────────────
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
            Debug.Log("[HairPhysicsSetup] 既存の HairPhysicsConfig.asset を使用します: " + assetPath);
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
