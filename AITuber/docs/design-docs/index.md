# 設計ドキュメント索引

> **このファイルはすべての設計ドキュメントのインデックスです。**  
> 新しい設計書を追加したら必ずここに追記してください。  
> 古くなったドキュメントはステータスを「⚠️要更新」に変更し、`tech-debt-tracker.md` に追記してください。

---

## アクティブ（最新）

| ドキュメント | ステータス | 内容 | 最終更新 |
|---|---|---|---|
| [SRS.md](../SRS.md) | ✅ 最新 | システム要件定義（FR/NFR の人間可読版、詳細は `.github/srs/` YAML） | 2026-03 |
| [autonomous-growth.md](../autonomous-growth.md) | ✅ 最新 | 自律成長システム全体設計・LLM-Modulo・Reflection Loop・文献サーベイ | 2026-03-03 |
| [m1-design.md](../m1-design.md) | ✅ 最新 | M1 実装設計・クラス仕様・テストケース一覧（TC-ADSP/GLOG/BPOL/MSG/INTG） | 2026-03-03 |
| [animation-technical-stack.md](../animation-technical-stack.md) | ✅ 最新 | Unity アニメーション技術スタック・コンポーネント構成 | 2026-03 |
| [lipsync.md](../lipsync.md) | ✅ 最新 | LipSync 実装方針・音素→BlendShape マッピング | 2026-03 |
| [testing.md](../testing.md) | ✅ 最新 | テスト方針・TC ID 体系・テスト実行方法 | 2026-03 |
| [obs_setup.md](../obs_setup.md) | ✅ 最新 | OBS セットアップ手順 | 2026-03 |

---

## 予定（作成予定の設計書）

| ドキュメント | 優先度 | 概要 |
|---|---|---|
| `m2-design.md` | 🔴 高 | M2 ReflectionRunner 詳細設計（実装前に作成） |
| `ws-protocol.md` | 🟡 中 | WebSocket プロトコル完全仕様（.github/srs/protocols/avatar_ws.yml の人間可読版） |
| `security.md` | 🟡 中 | セキュリティ要件・実装状況・リスク |
| `reliability.md` | 🟠 低 | 信頼性要件（NFR-LAT/RES/SEC）の達成状況 |

---

## 参照資料（外部文献）

| 文献 | 採用知見 |
|---|---|
| Park et al. 2023「Generative Agents」arXiv:2304.03442 | 観察→計画→振り返りサイクル → Growth System の Reflection Loop |
| Kambhampati et al. 2024「LLMs Can't Plan」arXiv:2402.01817 | LLM-Modulo パターン → M2 ProposalValidator |
| Hong et al. 2023「MetaGPT」arXiv:2308.00352 | SOP（標準作業手順）事前定義 → Growth System の段階的拡張方針 |
| OpenAI 2026「Harness Engineering」 | AGENTS.md TOC化・exec-plans・品質スコア・ゴールデン原則 |
