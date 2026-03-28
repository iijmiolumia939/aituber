# B1 Runbook: Face / Eye / Mouth

## 対象

- `Face_Base`
- `Neck_Base`
- `Eye_White_L_01`, `Eye_White_R_01`
- `Eye_Iris_L_01`, `Eye_Iris_R_01`
- `Eye_Highlight_L_01`, `Eye_Highlight_R_01`
- `Eyelid_Upper_L_01`, `Eyelid_Upper_R_01`
- `Eyelid_Lower_L_01`, `Eyelid_Lower_R_01`
- `Brow_L_01`, `Brow_R_01`
- `Mouth_Upper_01`, `Mouth_Lower_01`, `Mouth_Inner_01`, `Tongue_01`

## 所要目安

- 切り出し: 90-120分
- 下地描き足し: 30-45分
- Cubism仮組みとG1判定: 45-60分

## 手順

1. `Face_Base` と `Neck_Base` を確定し、境界の下地を先に描き足す。
2. 左目を先に完了し、右目は複製ベースで調整する。
3. まぶたは閉眼時に白目へ被る量を先に決める。
4. 口は `Upper/Lower/Inner/Tongue` の順に分離する。
5. ここまでで `phase1_layers.csv` のB1行を `InProgress` に更新する。
6. Cubismで `ParamEyeLOpen`, `ParamEyeROpen`, `ParamMouthOpenY`, `ParamMouthForm` を仮接続する。
7. `phase1_qc_gates.md` のG1を判定する。
8. G1通過後、B1行を `Done` に更新する。

## 破綻修正の優先順位

1. 白目はみ出し
2. 口内の見切れ
3. 首境界の穴
4. 眉の左右バランス

## 記録ルール

- 修正1件ごとに `phase1_daily_log.md` へ追記する。
- G1未達項目は必ず再現条件（0/50/100%）を書いて残す。
