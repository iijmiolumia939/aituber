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
            // Foot IK → AvatarGrounding へ転送
            _grounding?.OnAnimatorIKFromProxy(layerIndex);

            // Look-at IK → AvatarController へ転送
            _controller?.OnAnimatorIKFromProxy(layerIndex);
        }
    }
}
