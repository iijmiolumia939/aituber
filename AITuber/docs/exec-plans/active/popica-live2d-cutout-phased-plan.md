# Popica Live2D Cutout Phased Plan exec-plan

> **作成**: 2026-03-28  
> **目標**: 天導ルミナ立ち絵を Live2D 化するため、最短版を先行実装し、標準版→こだわり版へ段階的にブラッシュアップする。  
> **関連**: `AITuber/config/characters/popica.yml`, 配信アバター準備タスク  
> **依存**: 元立ち絵PSD（高解像度）, Live2D Cubism Editor

---

## ゴール

- フェーズ1（最短版）で「口パク・瞬き・軽い揺れ」が配信品質で成立すること。
- フェーズ2/3は差分追加で品質を上げ、既存の可動を壊さず段階的に改善すること。
- 各フェーズに Done 条件を持たせ、未完のまま次フェーズへ進まないこと。

---

## スコープ

| 含む | 含まない |
|---|---|
| パーツ切り出し設計 | 原画の大幅描き直し |
| Live2D 用のレイヤー命名規約 | 配信ソフト側の細かいトラッキング調整 |
| フェーズごとの可動実装と検証 | 衣装差分・別衣装の新規制作 |

---

## 設計決定ログ

### 2026-03-28: 3フェーズ固定（1→2→3）

- 先に最短版を完成させる。
- 標準版・こだわり版は差分追加のみで進める。
- 工数爆発を防ぐため、初期段階で髪・フリルの過分割を禁止する。

### 2026-03-28: 命名規則を先に固定

- 形式: `Category_Part_Side_Index` を基本とする。
- 例: `Hair_Twin_L_01`, `Eye_Iris_R_01`, `Ribbon_Waist_C_01`

---

## タスクブレークダウン

### Phase 1: 最短版（先行実装）

- [x] Phase 1 作業台帳ファイルを作成（layers/parameters/workflow）
- [x] Phase 1 のバッチ進行・QCゲート定義を作成
- [x] B1専用Runbookと日次ログを作成
- [x] 進捗自動集計CLIを作成
- [x] PSDレイヤー書き出しCLIを作成
- [x] Phase 1一括実行パイプラインCLIを作成
- [x] 書き出し結果から台帳statusを同期するCLIを作成
- [ ] 元絵から切り出し用PSDを作成（非破壊構成）
- [ ] 顔系を分離
- [ ] 目・眉・口の可動最小構成を分離
- [ ] 髪の大ブロックを分離
- [ ] 体幹・腕・スカート本体を分離
- [ ] 主要リボンを分離
- [ ] 下地描き足し（穴埋め）を実施
- [ ] Cubismへ読み込み、最小パラメータで可動確認
- [ ] 破綻修正（目・口・髪の前後関係）

### Phase 2: 標準版（差分追加）

- [ ] ツインテを 3 分割化（根元/中間/毛先）
- [ ] フリル群を段分割
- [ ] 靴・太ももアクセを独立
- [ ] `Eye Smile`, `Skirt Swing`, `Ribbon Swing` 追加
- [ ] 物理演算の遅れ調整

### Phase 3: こだわり版（最終仕上げ）

- [ ] 細毛束・小アクセを独立
- [ ] 影パーツ（乗算）を可動部へ分配
- [ ] 表情プリセット拡張
- [ ] 全体の干渉/貫通最終調整

---

## Phase 1 実作業チェックリスト（開始用）

### 1) 必須切り出しパーツ

- [ ] Face_Base
- [ ] Neck_Base
- [ ] Eye_White_L_01
- [ ] Eye_White_R_01
- [ ] Eye_Iris_L_01
- [ ] Eye_Iris_R_01
- [ ] Eye_Highlight_L_01
- [ ] Eye_Highlight_R_01
- [ ] Eyelid_Upper_L_01
- [ ] Eyelid_Upper_R_01
- [ ] Eyelid_Lower_L_01
- [ ] Eyelid_Lower_R_01
- [ ] Brow_L_01
- [ ] Brow_R_01
- [ ] Mouth_Upper_01
- [ ] Mouth_Lower_01
- [ ] Mouth_Inner_01
- [ ] Tongue_01
- [ ] Hair_Bangs_C_01
- [ ] Hair_Side_L_01
- [ ] Hair_Side_R_01
- [ ] Hair_Back_L_01
- [ ] Hair_Back_R_01
- [ ] Hair_Twin_L_01
- [ ] Hair_Twin_R_01
- [ ] Body_Upper_01
- [ ] Arm_Upper_L_01
- [ ] Arm_Upper_R_01
- [ ] Arm_Fore_L_01
- [ ] Arm_Fore_R_01
- [ ] Hand_L_01
- [ ] Hand_R_01
- [ ] Skirt_Base_01
- [ ] Ribbon_Head_L_01
- [ ] Ribbon_Head_R_01
- [ ] Ribbon_Chest_C_01
- [ ] Ribbon_Waist_C_01

### 2) Cubism 最小パラメータ

- [ ] ParamAngleX
- [ ] ParamAngleY
- [ ] ParamAngleZ
- [ ] ParamBodyX
- [ ] ParamBodyZ
- [ ] ParamEyeLOpen
- [ ] ParamEyeROpen
- [ ] ParamBrowLY
- [ ] ParamBrowRY
- [ ] ParamMouthOpenY
- [ ] ParamMouthForm
- [ ] ParamBreath
- [ ] ParamHairFrontSwing
- [ ] ParamHairTwinLSwing
- [ ] ParamHairTwinRSwing

### 3) Phase 1 Done条件

- [ ] 口パクが破綻なく成立
- [ ] 瞬きで白目はみ出しなし
- [ ] 頭振り時に髪の穴・欠けが目立たない
- [ ] 30分想定で違和感の強い揺れがない

---

## 進捗ログ

### 2026-03-28

- 実行計画ファイルを作成。
- 3フェーズ方針と最短版着手チェックリストを確定。
- Phase 1 着手用の実務ファイルを作成。
	- `AITuber/config/live2d/popica/phase1_layers.csv`
	- `AITuber/config/live2d/popica/phase1_parameters.json`
	- `AITuber/config/live2d/popica/phase1_workflow.md`
- バッチ進行とQCゲートを追加。
	- `AITuber/config/live2d/popica/phase1_qc_gates.md`
	- `phase1_layers.csv` に `batch/dependency/qc_gate` 列を追加
- B1運用ファイルを追加。
	- `AITuber/config/live2d/popica/b1_face_eye_mouth_runbook.md`
	- `AITuber/config/live2d/popica/phase1_daily_log.md`
- 進捗可視化CLIを追加。
	- `AITuber/tools/live2d_phase1_status.py`
- CLI実行で現在値を確認（Done 0 / InProgress 6 / Todo 31）。
- PSD書き出し補助CLIを追加。
	- `AITuber/tools/live2d_psd_export.py`
	- `pyproject.toml` に optional dependency `live2d` を追加
- PSD書き出しCLIに検証モードを追加。
	- `--validate-only` で台帳名とPSDレイヤー名の一致チェック
	- `validation_report.json` を出力
- 一括実行CLIを追加。
	- `AITuber/tools/live2d_phase1_pipeline.py`
	- validate -> export -> status を1コマンド化
- status同期CLIを追加。
	- `AITuber/tools/live2d_phase1_sync_status.py`
	- `export_report.json` を元に `phase1_layers.csv` の status を更新
- pipeline CLIを拡張。
	- `live2d_phase1_pipeline.py` で `--sync-status` / `--apply-sync` 対応
	- validate -> export -> status sync -> status summary を単一コマンドで実行可能
- export/pipelineに対象絞り込みを追加。
	- `--batch` / `--status` で B1のみ・未完了のみ等の実行に対応
- 次アクション: 作業PSDを作成し、Runbookに沿って B1 の切り出しと G1 判定を実施する。

---

## 完了チェック

- [ ] Phase 1 完了
- [ ] Phase 2 完了
- [ ] Phase 3 完了
- [ ] 完了後に `completed/` へ移動
