# Popica Phase 1 Daily Log

## 2026-03-28

### 実施バッチ

- [ ] B1 Face / Eye / Mouth
- [ ] B2 Hair
- [ ] B3 Body / Arm / Skirt
- [ ] B4 Ribbon / Final

### 作業記録

| Time | Batch | Layer | Action | Result | Next |
|---|---|---|---|---|---|
| --:-- | B1 | Face_Base | Started cutout | InProgress | Fill neck seam |
| --:-- | B1 | Neck_Base | Started base separation | InProgress | Verify neck-face overlap |
| --:-- | B1 | Eye_White_L_01 / Eye_White_R_01 | Started eye whites separation | InProgress | Align both eye heights |
| --:-- | B1 | Mouth_Upper_01 / Mouth_Lower_01 | Started mouth separation | InProgress | Confirm lip overlap at 0/50/100 |
| 09:54 | B1 | Session | Restarted from beginning in Cubism | InProgress | Start from Face/Neck seam fill |
| 09:55 | B1 | Face_Base / Neck_Base | Began seam underpaint pass | InProgress | Complete overlap-safe base fill |

### G1 判定

- [ ] 顔ベースと首の境界に欠けがない
- [ ] 瞬き0%/50%/100%で白目はみ出しがない
- [ ] 虹彩が左右で高さズレしない
- [ ] 口開閉0%/50%/100%で口内が破綻しない

### メモ

- 重大破綻:
- 次回開始地点: Face_Base / Neck_Base の境界下地描き足し（Runbook Step 1）
- 進捗CLIを追加: `python tools/live2d_phase1_status.py`
- 最新スナップショット: Total 37 / Done 0 / InProgress 6 / Todo 31
- PSD書き出しCLIを追加: `python tools/live2d_psd_export.py --psd <path> --csv config/live2d/popica/phase1_layers.csv --out-dir output/live2d/popica/phase1`
- 追加強化: `--validate-only` で書き出し前にレイヤー名一致チェック可能
- 一括実行CLIを追加: `python tools/live2d_phase1_pipeline.py --psd <path>`
- 台帳同期CLIを追加: `python tools/live2d_phase1_sync_status.py --report output/live2d/popica/phase1/export_report.json --apply`
- pipeline統合: `python tools/live2d_phase1_pipeline.py --psd <path> --apply-sync --reset-inprogress`
- 対象絞り込み追加: `--batch B1 --status Todo InProgress` で未完了のみ実行可能
