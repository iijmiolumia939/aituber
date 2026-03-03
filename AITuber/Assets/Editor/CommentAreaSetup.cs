// CommentAreaSetup.cs
// AITuber メニュー → "Setup Comment Area" でシーンに CommentArea オブジェクトを配置し
// AvatarController._commentAreaAnchor に自動ワイヤリングする。
//
// ■ CommentArea オブジェクトの意味
//   アバターがコメントを読む際に「視線を向ける先」を表す。
//   アバターの右斜め前 (カメラから見て右) に置くことで、
//   視線がコメント方向へ自然に動く。
//   Scene ビューで自由に移動・回転できる。

using UnityEngine;
using UnityEditor;
using AITuber.Avatar;

namespace AITuber.Editor
{
    public static class CommentAreaSetup
    {
        private const string ObjName = "CommentArea";

        [MenuItem("AITuber/Setup Comment Area")]
        public static void SetupCommentArea()
        {
            // 既存オブジェクトがあれば再選択するだけ
            var existing = GameObject.Find(ObjName);
            if (existing != null)
            {
                Selection.activeGameObject = existing;
                Debug.Log($"[CommentAreaSetup] '{ObjName}' already exists. Selected it.");
                SceneView.FrameLastActiveSceneView();
                WireToController(existing.transform);
                return;
            }

            // 新規作成
            var go = new GameObject(ObjName);
            Undo.RegisterCreatedObjectUndo(go, "Create CommentArea");

            // デフォルト位置: アバター右斜め前(カメラから見て右)、目線高さ
            // X+1.2 = 右, Y+1.1 = 目線高さ, Z+0.6 = 前方
            go.transform.position = new Vector3(1.2f, 1.1f, 0.6f);

            // アバターの方向(−Z前方)を向くように Y 回転
            // 実際にはシーンに合わせてユーザーが調整するが初期値として設定
            go.transform.rotation = Quaternion.Euler(0f, -20f, 0f);

            // AvatarController._commentAreaAnchor にワイヤリング
            WireToController(go.transform);

            Selection.activeGameObject = go;
            SceneView.FrameLastActiveSceneView();

            Debug.Log($"[CommentAreaSetup] '{ObjName}' created at {go.transform.position}.\n" +
                      "Scene ビューで位置・回転を調整しシーンを保存してください。\n" +
                      "AvatarController の Gizmo (シアン枠) でスキャン範囲が確認できます。");
        }

        private static void WireToController(Transform anchor)
        {
            var ctrl = Object.FindFirstObjectByType<AvatarController>();
            if (ctrl == null)
            {
                Debug.LogWarning("[CommentAreaSetup] AvatarController が見つかりません。手動でワイヤリングしてください。");
                return;
            }

            var so   = new SerializedObject(ctrl);
            var prop = so.FindProperty("_commentAreaAnchor");
            if (prop == null)
            {
                Debug.LogWarning("[CommentAreaSetup] _commentAreaAnchor フィールドが見つかりません。");
                return;
            }

            prop.objectReferenceValue = anchor;
            so.ApplyModifiedProperties();
            EditorUtility.SetDirty(ctrl);
            Debug.Log($"[CommentAreaSetup] AvatarController._commentAreaAnchor → '{anchor.name}'");
        }
    }
}
