// HairstyleDefinition.cs
// ScriptableObject — 髪型の外見プリセット定義。
// SRS ref: FR-APPEARANCE-02
//
// 使い方:
//   Assets/Appearances/Hairstyles/ 以下で右クリック → Create → AITuber → Hairstyle Definition
//   AppearanceController の Hairstyles [] にアサイン。
//
// hair_id は Orchestrator から appearance_update コマンドで送るキーと一致させること。

using System;
using UnityEngine;

namespace AITuber.Avatar
{
    /// <summary>
    /// 髪型プリセット。AppearanceController.ApplyHair() から参照される。
    /// FR-APPEARANCE-02
    /// </summary>
    [CreateAssetMenu(fileName = "NewHairstyle", menuName = "AITuber/Hairstyle Definition", order = 61)]
    public class HairstyleDefinition : ScriptableObject
    {
        [Header("識別")]
        [Tooltip("Orchestrator から送る hair_id と一致させる (例: default, ponytail, short, twin_tails)")]
        public string hairId;

        [Tooltip("配信上での表示名（UI/ログ用）")]
        public string displayName;

        [Header("Material Overrides")]
        [Tooltip("髪レンダラーとマテリアル配列のペア。CostumeDefinition と同じ仕組み。")]
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
