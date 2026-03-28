# Popica Live2D Phase 1 Workflow

## 目的

- 最短版の切り出しと可動確認を 1 サイクルで完了する。
- 口パク・瞬き・軽い揺れを成立させる。

## 事前準備

1. 元絵を複製し、作業PSDを新規作成する。
2. 線画と塗りを可能な限り一体で保持し、可動境界のみを分離する。
3. 欠けが出る部位は下地描き足しを先に行う。

## レイヤー命名

- 規則: `Category_Part_Side_Index`
- 例:
  - `Hair_Twin_L_01`
  - `Eye_Iris_R_01`
  - `Ribbon_Waist_C_01`

## 切り出し順序

1. Face / Eye / Brow / Mouth
2. Hair（前髪 -> 横髪 -> 後ろ髪 -> ツインテ）
3. Body / Arm / Hand / Skirt
4. Ribbon（頭 -> 胸 -> 腰）

## Cubism 実装順序

1. 画像読み込み
2. パーツID確認
3. `ParamAngleX/Y/Z` と `ParamBodyX/Z`
4. `ParamEyeLOpen/ParamEyeROpen`
5. `ParamMouthOpenY/ParamMouthForm`
6. `ParamBreath`
7. 髪揺れパラメータ

## 検証チェック

- 白目はみ出しがない
- 口開閉で歯・舌が不自然に飛び出ない
- 顔振り時に髪の穴が見えない
- リボンの遅れが過剰でない

## 出力物

- `.psd`: 切り出し済み
- `.cmo3`: Phase 1 可動入り
- `.model3.json`: パラメータ接続済み
- 検証メモ: 破綻箇所と修正履歴

## 運用ファイル

- `phase1_layers.csv`: レイヤー進捗台帳（Todo/InProgress/Done）
- `phase1_qc_gates.md`: バッチごとの品質判定
- `b1_face_eye_mouth_runbook.md`: B1専用の手順書
- `phase1_daily_log.md`: 日次ログ

## 実行ループ

1. 対象バッチのRunbookを開く。
2. `phase1_layers.csv` の対象行を `InProgress` にする。
3. 作業後にQC Gateを判定する。
4. 通過した行を `Done` に更新する。
5. `phase1_daily_log.md` に記録する。

## 進捗確認コマンド

- AITuber 直下で実行:
  - `python tools/live2d_phase1_status.py`
- 別CSVを指定して実行:
  - `python tools/live2d_phase1_status.py --csv config/live2d/popica/phase1_layers.csv`

## PSD書き出し補助コマンド

- レイヤー一覧を確認:
  - `python tools/live2d_psd_export.py --psd path/to/popica.psd --list`
- 書き出し前に台帳名との一致を検証:
  - `python tools/live2d_psd_export.py --psd path/to/popica.psd --csv config/live2d/popica/phase1_layers.csv --validate-only`
- 不一致が1件でもあれば失敗で止める:
  - `python tools/live2d_psd_export.py --psd path/to/popica.psd --csv config/live2d/popica/phase1_layers.csv --validate-only --strict`
- Phase 1台帳にあるレイヤー名を一括書き出し:
  - `python tools/live2d_psd_export.py --psd path/to/popica.psd --csv config/live2d/popica/phase1_layers.csv --out-dir output/live2d/popica/phase1`
- B1かつ未完了だけ書き出し:
  - `python tools/live2d_psd_export.py --psd path/to/popica.psd --csv config/live2d/popica/phase1_layers.csv --batch B1 --status Todo InProgress`
- 失敗時に即停止（不足レイヤー検出）:
  - `python tools/live2d_psd_export.py --psd path/to/popica.psd --csv config/live2d/popica/phase1_layers.csv --strict`

## 一括実行パイプライン

- 検証 + 書き出し + 進捗サマリ:
  - `python tools/live2d_phase1_pipeline.py --psd path/to/popica.psd`
- 不一致がある場合は失敗で停止:
  - `python tools/live2d_phase1_pipeline.py --psd path/to/popica.psd --strict`
- 書き出しはせず検証のみ:
  - `python tools/live2d_phase1_pipeline.py --psd path/to/popica.psd --validate-only`
- 書き出し後にstatus同期の候補も同時表示:
  - `python tools/live2d_phase1_pipeline.py --psd path/to/popica.psd --sync-status`
- status同期までCSVへ反映:
  - `python tools/live2d_phase1_pipeline.py --psd path/to/popica.psd --apply-sync --reset-inprogress`
- B1の未完了だけを対象に一括実行:
  - `python tools/live2d_phase1_pipeline.py --psd path/to/popica.psd --batch B1 --status Todo InProgress --apply-sync --reset-inprogress`

## 台帳status同期コマンド

- 書き出し結果から更新候補を確認（dry-run）:
  - `python tools/live2d_phase1_sync_status.py --report output/live2d/popica/phase1/export_report.json`
- 実際にCSVへ反映:
  - `python tools/live2d_phase1_sync_status.py --report output/live2d/popica/phase1/export_report.json --apply`
- 未書き出しのInProgressをTodoへ戻す:
  - `python tools/live2d_phase1_sync_status.py --report output/live2d/popica/phase1/export_report.json --apply --reset-inprogress`
