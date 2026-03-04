// RoomDefinition.cs
// ScriptableObject — 1ルームの設定をエディタで定義する。
// SRS ref: FR-ROOM-01
//
// 使い方:
//   Assets/Rooms/ 以下で右クリック → Create → AITuber → Room Definition
//   RoomManager の Rooms [] にアサイン。
//
// room_id は Orchestrator から room_change コマンドで送るキーと一致させること。

using System;
using UnityEngine;

namespace AITuber.Room
{
    /// <summary>ゾーン（同一部屋内のエリア）のアバター・カメラ位置を定義する。</summary>
    [Serializable]
    public class AvatarZone
    {
        [Tooltip("zone_id (Python の zone_id と一致させる 例: pc_area, sleep_area)")]
        public string zoneId;

        [Header("アバター配置")]
        public Vector3 avatarPosition = Vector3.zero;
        public Vector3 avatarEuler    = Vector3.zero;

        [Header("カメラ設定")]
        public Vector3 cameraPosition = new Vector3(0f,  1.3f, -1.5f);
        public Vector3 cameraEuler    = new Vector3(5f,  0f,    0f);
        public float   cameraFov      = 40f;
    }

    [CreateAssetMenu(fileName = "NewRoom", menuName = "AITuber/Room Definition", order = 50)]
    public class RoomDefinition : ScriptableObject
    {
        [Header("識別")]
        [Tooltip("Orchestrator から送る room_id と一致させる (例: alchemist, library)")]
        public string roomId;

        [Tooltip("配信上での表示名（未使用でも可）")]
        public string displayName;

        [Header("ルーム Prefab")]
        [Tooltip("事前に用意した部屋 Prefab を Assign。ライト・小道具を含む。")]
        public GameObject roomPrefab;

        [Header("カメラ設定（この部屋でのデフォルト）")]
        public Vector3    cameraPosition = new Vector3(0f,  1.3f, -1.5f);
        public Vector3    cameraEuler    = new Vector3(5f,  0f,    0f);
        public float      cameraFov      = 40f;

        [Header("アバター配置")]
        [Tooltip("アバターを置くワールド座標")]
        public Vector3    avatarPosition = Vector3.zero;
        public Vector3    avatarEuler    = Vector3.zero;

        [Header("カメラカット演出")]
        [Tooltip("有効時: 部屋切り替え時にフェード or スムーズ移動")]
        public bool       useFadeTransition = true;
        [Tooltip("フェードアウト + フェードイン の合計秒数")]
        public float      transitionDuration = 0.4f;
        [Header("ゾーン定義（同一部屋内のエリア切替）")]
        [Tooltip("例: PCエリア, スリープエリア, リラックスエリア")]
        public AvatarZone[] zones = Array.Empty<AvatarZone>();    }
}
