# Sonnet 4.6 実装指示プロンプト

以下は AITuber Unity プロジェクト向けの実装タスクです。設計方針は確定済みです。コードベースを確認した上で、下記の順序を厳守して実装してください。

## 目的

アバターのモーション系を、責務が衝突しない構造へ段階的に整理する。

特に解決したい問題は以下です。

- 起動時やテレポート後の接地が不安定
- `Audio2GestureController` が `LateUpdate` でボーンを直書きし、Animator と競合する
- `CharacterController` と `NavMeshAgent` の ownership が曖昧
- `OnAnimatorIK` の責務が分散しており、LookAt / FootIK / A2G を安全に統合できない

## 参照ドキュメント

- 改訂ロードマップ: [avatar-motion-roadmap.md](./avatar-motion-roadmap.md)
- 現行の主要実装:
  - `Assets/Scripts/Avatar/AvatarGrounding.cs`
  - `Assets/Scripts/Avatar/AvatarController.cs`
  - `Assets/Scripts/Avatar/Audio2GestureController.cs`
  - `Assets/Scripts/Avatar/AvatarIKProxy.cs`
  - `Assets/Scripts/Behavior/BehaviorSequenceRunner.cs`

## 実装順序

次の順序を崩さないこと。

1. 接地を最小化する
2. ロコモーション ownership を整理する
3. IK の窓口を 1 か所に統合する
4. A2G を `LateUpdate` 直書きから外す
5. Foot IK は idle から導入する

今回は全部を一気に終わらせる必要はないが、少なくとも 1〜4 の設計に矛盾しないように進めること。

## ハード制約

- 既存機能を壊さないこと
- `LateUpdate` での A2G ボーン直書き依存を最終的に消せる方向で進めること
- `OnAnimatorIK` を複数コンポーネントでバラバラに拡張しないこと
- `SkinWidth` を見た目の接地問題の唯一の解決策として扱わないこと
- `AvatarGrounding` をいきなり全削除しないこと
- `BehaviorSequenceRunner` から `CharacterController.enabled` 切り替え前提の構造を徐々に外すこと
- 変更は最小限かつ段階的に行うこと

## 非目標

今回は以下をゴールにしないこと。

- Final IK 導入
- 歩行時の完全な足IK完成
- 見た目の接地を 1 回の調整で完全解決すること
- 大規模な Animator Controller 再設計

## 実装方針

### Phase 1 相当: 接地の最小化

やること:

- `CharacterController` の `height` / `radius` / `center` を見直す
- 起動時にも接地処理が走るようにする
- 起動時・テレポート時に必要な最小限の visual root 校正だけ残す
- `DoFixPivot()` のような骨依存補正は縮退または限定利用にする

期待する状態:

- 起動直後にアバターが空中待機しない
- 部屋切替や teleport 後に極端な浮き・沈みがない

### Phase 2 相当: ロコモーション ownership 整理

やること:

- `NavMeshAgent.updatePosition = false`
- `NavMeshAgent.updateRotation = false`
- Agent は経路と希望速度の計算だけを担当
- 実際の移動は CC 側に寄せる
- `desiredVelocity` をそのまま使うだけで済ませず、水平移動・垂直移動・回転・到達判定を分ける

期待する状態:

- CC と Agent の transform ownership 競合が減る
- `_walkingCC` のような退避ロジックを将来的に削れる構造になる

### Phase 3 相当: IK 窓口統合

やること:

- `OnAnimatorIK` の実処理を 1 か所へ寄せる
- `AvatarIKProxy` は必要なら通知窓口に限定する
- LookAt / FootIK / 将来の A2G が同じ窓口から扱える構造にする

期待する状態:

- IK の最終責任コンポーネントが明確になる
- Head / Foot / Body の更新順が追える

### Phase 4 相当: A2G 移行

やること:

- `Audio2GestureController` は最終的に「デルタ生成」へ寄せる
- ボーン適用は統合済み IK / bone application 窓口で行う
- `AvatarController.LateUpdate()` からの A2G 直接適用を外す方向にする

重要:

- `OnAnimatorIK` に移すだけで解決した扱いにしないこと
- LookAt と Head / Neck を同時に触る場合の優先順位を設計すること

## 期待する成果物

- 実装コード
- 必要なドキュメント更新
- 変更理由が分かる最小限のコメント
- 受け入れ条件に対する確認結果

## 受け入れ条件

最低でも以下を満たすこと。

1. 起動時の接地が改善される
2. room switch / teleport 相当の位置変更後に大崩れしない
3. A2G が Animator と競合しにくい構造へ前進している
4. IK の責務が今より明確になっている
5. NavMeshAgent と CharacterController の ownership 整理が進んでいる

## テストと検証

可能な範囲で以下を確認すること。

- Unity コンパイルエラーが出ない
- 起動直後の接地
- room switch 後の接地
- A2G 発話中と非発話中の姿勢遷移
- LookAt が壊れていないこと
- 歩行開始 / 停止時に明らかな jitter や stuck が増えていないこと

## 実装時の注意

- いきなり大規模に削除しないこと
- 先に ownership を整理してから削除すること
- 既存の `AvatarGrounding`, `AvatarController`, `AvatarIKProxy` の責務を観察してから手を入れること
- 一時的な互換レイヤが必要なら許容するが、最終方向は明確にすること

## 実装の進め方

以下の流れで進めてください。

1. 現行コードを確認し、ownership の現状を要約する
2. 最小変更で Phase 1 を実装する
3. 動作確認できる単位でコミット相当の差分に分けて進める
4. その後 Phase 2〜4 に進む
5. 各フェーズごとに「何を所有しているか」を短く記録する

## 最後に

「見た目の接地」「物理的な接地」「IK の最終書き込み」「移動の ownership」を混ぜないこと。今回の本質は機能追加ではなく、責務の整理です。