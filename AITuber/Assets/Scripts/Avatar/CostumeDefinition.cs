// CostumeDefinition.cs
// ScriptableObject — costumeの外見プリセット定義。
// SRS ref: FR-APPEARANCE-01
//
// 使い方:
//   Assets/Appearances/Costumes/ 以下で右クリック → Create → AITuber → Costume Definition
//   AppearanceController の Costumes [] にアサイン。
//
// costume_id は Orchestrator から appearance_update コマンドで送るキーと一致させること。

using System;
using UnityEngine;

namespace AITuber.Avatar
{
    /// <summary>1レンダラー分のマテリアル上書き定義。</summary>
    [Serializable]
    public class RendererMaterialOverride
    {
        [Tooltip("対象レンダラーを持つ GameObject の名前（階層検索）")]
        public string rendererName;

        [Tooltip("適用するマテリアル配列。スロット数はレンダラーの sharedMaterials と一致させること。")]
        public Material[] materials;
    }

    /// <summary>
    /// 衣装プリセット。AppearanceController.ApplyCostume() から参照される。
    /// FR-APPEARANCE-01
    /// </summary>
    [CreateAssetMenu(fileName = "NewCostume", menuName = "AITuber/Costume Definition", order = 60)]
    public class CostumeDefinition : ScriptableObject
    {
        [Header("識別")]
        [Tooltip("Orchestrator から送る costume_id と一致させる (例: default, casual, formal, pajama)")]
        public string costumeId;

        [Tooltip("配信上での表示名（UI/ログ用）")]
        public string displayName;

        [Header("Material Overrides")]
        [Tooltip("レンダラー名とマテリアル配列のペア。名前で検索するため部分一致可。")]
        public RendererMaterialOverride[] overrides;

        /// <summary>
        /// 指定レンダラー配列に対してマテリアルを適用する。
        /// rendererName が含まれるレンダラーをすべて上書きする。
        /// </summary>
        public void Apply(Renderer[] renderers)
        {
            if (renderers == null || overrides == null) return;

            foreach (var ov in overrides)
            {
                if (ov == null || string.IsNullOrEmpty(ov.rendererName) || ov.materials == null) continue;

                foreach (var rend in renderers)
                {
                    if (rend == null) continue;
                    if (!rend.gameObject.name.Contains(ov.rendererName)) continue;

                    var mats = rend.sharedMaterials;
                    for (int i = 0; i < mats.Length && i < ov.materials.Length; i++)
                    {
                        if (ov.materials[i] != null)
                            mats[i] = ov.materials[i];
                    }
                    rend.sharedMaterials = mats;
                }
            }
        }
    }
}
