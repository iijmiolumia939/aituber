// AvatarIKProxy.cs
// OnAnimatorIK は Animator と同じ GameObject 上のスクリプトにしか呼ばれない。
// アバターモデル root (Animator あり) から、親の AvatarRoot (AvatarGrounding あり) に
// OnAnimatorIK を転送するプロキシ。
//
// セットアップ:
//   AvatarGrounding.Start() により AddComponent で自動アタッチされます。
//   手動でアバター子 GameObject（Animator が付いている方）に Attach することも可能。

using UnityEngine;

namespace AITuber.Avatar
{
    public class AvatarIKProxy : MonoBehaviour
    {
        private AvatarGrounding _grounding;
        private AvatarController _controller;

        private void Awake()
        {
            // 親階層から AvatarGrounding / AvatarController を探す
            _grounding  = GetComponentInParent<AvatarGrounding>();
            _controller = GetComponentInParent<AvatarController>();

            if (_grounding == null)
                Debug.LogWarning("[AvatarIKProxy] AvatarGrounding が親に見つかりません。");
            if (_controller == null)
                Debug.LogWarning("[AvatarIKProxy] AvatarController が親に見つかりません。");
        }

        private void OnAnimatorIK(int layerIndex)
        {
            // IK application order — must be preserved (Phase 3):
            //   1. Foot IK (AvatarGrounding)   — floor-contact corrections
            //   2. LookAt IK (AvatarController) — head/eye gaze direction
            // Note: A2G upper-body deltas are applied AFTER the IK pass in
            //   AvatarController.LateUpdate() (not here), because additive bone
            //   writes must run after Animator IK has fully settled.
            // All Animator IK API calls (SetLookAtWeight, SetIKPosition, etc.) funnel
            // through this single OnAnimatorIK receiver — do not add IK processing elsewhere.
            _grounding?.OnAnimatorIKFromProxy(layerIndex);
            _controller?.OnAnimatorIKFromProxy(layerIndex);
        }
    }
}
