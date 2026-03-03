# M1 実装設計書: ActionDispatcher + GapLogger

> **マイルストーン**: M1 — Capability Gap Logの収集開始  
> **ステータス**: 設計フェーズ（2026-03-03）  
> **依存**: [autonomous-growth.md](autonomous-growth.md)

---

## 概要

本ドキュメントはM1で実装する以下のコンポーネントの**クラス設計・インターフェース・テスト仕様**を定義する。

| コンポーネント | ファイル | 役割 |
|---|---|---|
| `BehaviorPolicy` | `Assets/StreamingAssets/behavior_policy.yml` | Intent→Actionマッピングの外部データ |
| `BehaviorEntry` (data class) | `Assets/Scripts/Growth/BehaviorEntry.cs` | ポリシーエントリのC#表現 |
| `BehaviorPolicyLoader` | `Assets/Scripts/Growth/BehaviorPolicyLoader.cs` | YAMLを読み込み辞書に変換 |
| `GapEntry` (data class) | `Assets/Scripts/Growth/GapEntry.cs` | GapログエントリのC#表現 |
| `GapLogger` | `Assets/Scripts/Growth/GapLogger.cs` | Gap発生時にJSONLを書き出す |
| `ActionDispatcher` | `Assets/Scripts/Growth/ActionDispatcher.cs` | Intent→Action変換 + Gap検出ゲートウェイ |
| `AvatarIntentParams` | `Assets/Scripts/Avatar/AvatarMessage.cs` に追加 | `avatar_intent`コマンドのパラメーター型 |

---

## ディレクトリ構造

```
Assets/
  Scripts/
    Avatar/
      AvatarController.cs         (既存 - 変更あり)
      AvatarMessage.cs            (既存 - avatar_intent追加)
      AvatarWSClient.cs           (既存 - 変更なし)
    Growth/
      ActionDispatcher.cs         (新規)
      BehaviorPolicyLoader.cs     (新規)
      BehaviorEntry.cs            (新規)
      GapLogger.cs                (新規)
      GapEntry.cs                 (新規)
  StreamingAssets/
    behavior_policy.yml           (新規)
Tests/
  EditMode/
    ActionDispatcherTests.cs      (新規)
    BehaviorPolicyLoaderTests.cs  (新規)
    GapLoggerTests.cs             (新規)
    AvatarMessageParserTests.cs   (新規)
  PlayMode/
    GrowthIntegrationTests.cs     (新規)
Logs/
  capability_gaps/
    <stream_id>.jsonl             (実行時生成)
```

---

## 1. データモデル

### 1.1 BehaviorEntry

```csharp
// Assets/Scripts/Growth/BehaviorEntry.cs
namespace AITuber.Growth
{
    /// <summary>
    /// behavior_policy.yml の1エントリを表す。
    /// YAMLパーサーの都合でpublicフィールド使用。
    /// </summary>
    [System.Serializable]
    public class BehaviorEntry
    {
        /// <summary>対応するintent名（ActionDispatcherのルックアップキー）</summary>
        public string intent;

        /// <summary>実行するWSコマンド種別 ("avatar_update" or "avatar_event")</summary>
        public string cmd;

        /// <summary>
        /// cmdがavatar_updateの場合のパラメーター。
        /// gesture / emotion / look_target のいずれか or 複数。
        /// </summary>
        public string gesture;
        public string emotion;
        public string look_target;

        /// <summary>
        /// cmdがavatar_eventの場合のパラメーター。
        /// </summary>
        public string @event;
        public float intensity = 1f;

        /// <summary>このエントリの優先度（同一intentに複数エントリ可）</summary>
        public int priority = 0;

        /// <summary>説明コメント（GapDashboard表示用）</summary>
        public string notes;
    }
}
```

**制約**:
- `intent` は必須・非空。空の場合 `BehaviorPolicyLoader` に読み込まれない
- `cmd` は `"avatar_update"` または `"avatar_event"` のみ許容

---

### 1.2 GapEntry

```csharp
// Assets/Scripts/Growth/GapEntry.cs
using System;

namespace AITuber.Growth
{
    /// <summary>
    /// Capability Gap 1件のログエントリ。
    /// JSONL形式でファイルに書き出される。
    /// </summary>
    [System.Serializable]
    public class GapEntry
    {
        public string timestamp;       // ISO 8601: "2026-03-03T12:34:56Z"
        public string stream_id;       // "stream_20260303_143000"
        public string trigger;         // "avatar_intent_ws" | "behavior_missing" etc.
        public string current_state;   // AvatarControllerの現在ステート名
        public IntendedAction intended_action;
        public string fallback_used;   // 実際に実行したアクション名（"nod", "none"等）
        public GapContext context;
        public string gap_category;    // "missing_motion" | "missing_behavior" | ...
        public float priority_score;   // 0.0 (算出はReflectionRunnerが行う)

        [System.Serializable]
        public class IntendedAction
        {
            public string type;   // "gesture" | "event" | "behavior"
            public string name;   // intent名
            public string param;  // 追加パラメーター（JSON文字列）
        }

        [System.Serializable]
        public class GapContext
        {
            public string emotion;
            public string look_target;
            public string recent_comment; // 直近コメント（任意）
        }
    }
}
```

---

### 1.3 AvatarIntentParams（AvatarMessage.csへの追加）

```csharp
// AvatarMessage.cs に追記

/// <summary>
/// avatar_intent コマンドのパラメーター。
/// LLMブレインが「何をしたかったか」をIntentとして送信する。
/// ActionDispatcherがBehaviorPolicyを検索し、実行またはGap記録する。
/// </summary>
[Serializable]
public class AvatarIntentParams
{
    /// <summary>実行したいintent名（例: "point_at_screen", "celebrate_milestone"）</summary>
    public string intent = "";

    /// <summary>
    /// BehaviorPolicyに登録されていない場合のフォールバックアクション。
    /// 空の場合はActionDispatcherが"none"にする。
    /// </summary>
    public string fallback = "";

    /// <summary>追加コンテキスト（JSON文字列、任意）</summary>
    public string context_json = "";
}
```

---

## 2. BehaviorPolicyLoader

### 2.1 クラス設計

```csharp
// Assets/Scripts/Growth/BehaviorPolicyLoader.cs
using System.Collections.Generic;
using UnityEngine;

namespace AITuber.Growth
{
    /// <summary>
    /// StreamingAssets/behavior_policy.yml を起動時にロードし、
    /// intent名→BehaviorEntryの辞書として提供する。
    ///
    /// YAMLパーサーはUnityに標準搭載されていないため、
    /// シンプルな行指向パーサーを自前実装する。
    /// （外部依存をゼロに保つ方針）
    /// </summary>
    public class BehaviorPolicyLoader : MonoBehaviour
    {
        // ── Singleton ─────────────────────────────────────────────────
        public static BehaviorPolicyLoader Instance { get; private set; }

        // ── State ──────────────────────────────────────────────────────
        private Dictionary<string, BehaviorEntry> _policy
            = new Dictionary<string, BehaviorEntry>();

        public IReadOnlyDictionary<string, BehaviorEntry> Policy => _policy;

        // ── Unity lifecycle ───────────────────────────────────────────
        private void Awake()
        {
            if (Instance != null && Instance != this) { Destroy(gameObject); return; }
            Instance = this;
            DontDestroyOnLoad(gameObject);
            Load();
        }

        // ── Public API ────────────────────────────────────────────────

        /// <summary>
        /// intent名に対応するBehaviorEntryを返す。
        /// 見つからない場合はnullを返す（例外を投げない）。
        /// </summary>
        public BehaviorEntry Lookup(string intent)
        {
            if (string.IsNullOrEmpty(intent)) return null;
            _policy.TryGetValue(intent, out var entry);
            return entry;
        }

        /// <summary>
        /// テスト・デバッグ用: エントリを直接注入する。
        /// </summary>
        public void InjectForTest(Dictionary<string, BehaviorEntry> entries)
        {
            _policy = entries ?? new Dictionary<string, BehaviorEntry>();
        }

        // ── Internal ──────────────────────────────────────────────────

        /// <summary>
        /// StreamingAssets/behavior_policy.yml を読み込む。
        /// ファイルが存在しない場合は空辞書のまま（起動は継続する）。
        /// </summary>
        internal void Load()    // internal for test access
        {
            _policy.Clear();
            string path = System.IO.Path.Combine(
                Application.streamingAssetsPath, "behavior_policy.yml");

            if (!System.IO.File.Exists(path))
            {
                Debug.Log("[BehaviorPolicyLoader] behavior_policy.yml not found – running with empty policy.");
                return;
            }

            string[] lines = System.IO.File.ReadAllLines(path);
            ParseYamlLines(lines);
            Debug.Log($"[BehaviorPolicyLoader] Loaded {_policy.Count} entries.");
        }

        /// <summary>
        /// 行配列をパースしてpolicyを構築する。
        /// 対応するYAML形式は behavior_policy.yml のスキーマに従う。
        /// </summary>
        internal void ParseYamlLines(string[] lines)    // internal for test
        {
            // 実装詳細はYAMLスキーマ仕様参照
            // ...
        }
    }
}
```

---

## 3. GapLogger

### 3.1 クラス設計

```csharp
// Assets/Scripts/Growth/GapLogger.cs
using System;
using System.IO;
using UnityEngine;

namespace AITuber.Growth
{
    /// <summary>
    /// Capability Gap発生時にJSONL形式でログファイルに書き出す。
    ///
    /// 出力先: Application.persistentDataPath/capability_gaps/<stream_id>.jsonl
    /// 書き込みは同期I/O（1件あたり数msのため許容、ゲーム用途ではないため）。
    ///
    /// SRS refs: FR-GROWTH-01 (TBD)
    /// </summary>
    public class GapLogger : MonoBehaviour
    {
        // ── Singleton ─────────────────────────────────────────────────
        public static GapLogger Instance { get; private set; }

        // ── Config ────────────────────────────────────────────────────
        [SerializeField] private string _streamId = "";  // 起動時に自動設定
        [SerializeField] private bool _enabled = true;

        // ── State ──────────────────────────────────────────────────────
        private string _logPath;
        private int _gapCountThisSession;

        // ── Unity lifecycle ───────────────────────────────────────────
        private void Awake()
        {
            if (Instance != null && Instance != this) { Destroy(gameObject); return; }
            Instance = this;
            DontDestroyOnLoad(gameObject);
            InitSession();
        }

        // ── Public API ────────────────────────────────────────────────

        /// <summary>
        /// Gap 1件を記録する。
        /// スレッドセーフではない（Unityメインスレッドから呼ぶこと）。
        /// </summary>
        /// <param name="entry">記録するGapEntry</param>
        public void Log(GapEntry entry)
        {
            if (!_enabled || entry == null) return;

            entry.stream_id = _streamId;
            entry.timestamp = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ");
            if (entry.priority_score == 0f)
                entry.priority_score = 0f;  // ReflectionRunnerが後で算出

            string json = JsonUtility.ToJson(entry);
            try
            {
                File.AppendAllText(_logPath, json + "\n");
                _gapCountThisSession++;
                Debug.Log($"[GapLogger] Logged gap #{_gapCountThisSession}: intent={entry.intended_action?.name} → fallback={entry.fallback_used}");
            }
            catch (Exception ex)
            {
                // ログ書き込みに失敗してもゲームを止めない
                Debug.LogWarning($"[GapLogger] Write failed: {ex.Message}");
            }
        }

        /// <summary>
        /// 現在のセッションで記録したGap件数を返す。
        /// </summary>
        public int GapCountThisSession => _gapCountThisSession;

        /// <summary>
        /// 現在のログファイルパスを返す（テスト・デバッグ用）。
        /// </summary>
        public string LogPath => _logPath;

        /// <summary>
        /// テスト用: ログパスを直接指定する。
        /// </summary>
        public void SetLogPathForTest(string path) => _logPath = path;

        /// <summary>
        /// テスト用: 有効・無効を切り替える。
        /// </summary>
        public void SetEnabled(bool v) => _enabled = v;

        // ── Internal ──────────────────────────────────────────────────

        private void InitSession()
        {
            if (string.IsNullOrEmpty(_streamId))
                _streamId = "stream_" + DateTime.UtcNow.ToString("yyyyMMdd_HHmmss");

            string dir = Path.Combine(Application.persistentDataPath, "capability_gaps");
            Directory.CreateDirectory(dir);
            _logPath = Path.Combine(dir, _streamId + ".jsonl");
            _gapCountThisSession = 0;
            Debug.Log($"[GapLogger] Session initialized: {_logPath}");
        }
    }
}
```

---

## 4. ActionDispatcher

### 4.1 クラス設計

```csharp
// Assets/Scripts/Growth/ActionDispatcher.cs
using UnityEngine;
using AITuber.Avatar;

namespace AITuber.Growth
{
    /// <summary>
    /// `avatar_intent` コマンドを受け取り、BehaviorPolicyを参照して
    /// 実行可能なWSアクションに変換する。
    ///
    /// 実行不可能な場合はfallbackを実行し、GapLoggerに記録する。
    ///
    /// AvatarControllerと同じGameObjectに配置するか、
    /// Inspectorで参照をワイヤリングする。
    ///
    /// SRS refs: FR-GROWTH-02 (TBD)
    /// </summary>
    public class ActionDispatcher : MonoBehaviour
    {
        // ── Dependencies ──────────────────────────────────────────────
        [SerializeField] private AvatarController _avatarController;

        // ── Result type ───────────────────────────────────────────────
        public enum DispatchResult
        {
            Executed,           // ポリシーヒット → アクション実行
            FallbackExecuted,   // ポリシーミス → フォールバック実行 + Gap記録
            Skipped,            // intentもfallbackも空 → 何もしない
            Error               // パラメーターnull等
        }

        // ── Public API ────────────────────────────────────────────────

        /// <summary>
        /// AvatarIntentParams を処理する。
        /// BehaviorPolicyLoaderとGapLoggerはシングルトン経由で取得する。
        ///
        /// 戻り値でテストからDispatch結果を確認できる。
        /// </summary>
        public DispatchResult Dispatch(AvatarIntentParams p, string currentState = "unknown")
        {
            if (p == null) return DispatchResult.Error;

            string intent = p.intent ?? "";
            string fallback = p.fallback ?? "";

            // ── ポリシー検索 ───────────────────────────────────────────
            var entry = BehaviorPolicyLoader.Instance?.Lookup(intent);

            if (entry != null)
            {
                // ヒット: ポリシー通りにアクション実行
                ExecuteEntry(entry);
                Debug.Log($"[ActionDispatcher] Executed: intent={intent} via policy");
                return DispatchResult.Executed;
            }

            // ミス: Gap記録 + フォールバック実行
            RecordGap(intent, fallback, currentState, p.context_json);

            if (!string.IsNullOrEmpty(fallback) && fallback != "none")
            {
                ExecuteFallback(fallback);
                Debug.Log($"[ActionDispatcher] Fallback: intent={intent} → {fallback}");
                return DispatchResult.FallbackExecuted;
            }

            Debug.Log($"[ActionDispatcher] Skipped: intent={intent} (no policy, no fallback)");
            return DispatchResult.Skipped;
        }

        // ── Internal ──────────────────────────────────────────────────

        private void ExecuteEntry(BehaviorEntry entry)
        {
            if (_avatarController == null) return;

            switch (entry.cmd)
            {
                case "avatar_update":
                    _avatarController.ApplyFromPolicy(
                        entry.emotion, entry.gesture, entry.look_target);
                    break;
                case "avatar_event":
                    _avatarController.TriggerEventFromPolicy(
                        entry.@event, entry.intensity);
                    break;
            }
        }

        private void ExecuteFallback(string fallback)
        {
            if (_avatarController == null) return;
            // fallbackはgesture名として解釈する（最も汎用的なフォールバック）
            _avatarController.ApplyFromPolicy(null, fallback, null);
        }

        private void RecordGap(
            string intent, string fallback, string currentState, string contextJson)
        {
            var logger = GapLogger.Instance;
            if (logger == null) return;

            var gap = new GapEntry
            {
                current_state = currentState,
                trigger = "avatar_intent_ws",
                fallback_used = string.IsNullOrEmpty(fallback) ? "none" : fallback,
                gap_category = CategorizeGap(intent),
                intended_action = new GapEntry.IntendedAction
                {
                    type = "intent",
                    name = intent,
                    param = contextJson ?? ""
                },
                context = new GapEntry.GapContext
                {
                    emotion = _avatarController?.CurrentEmotion ?? "",
                    look_target = _avatarController?.CurrentLookTarget ?? "",
                    recent_comment = ""
                }
            };

            logger.Log(gap);
        }

        /// <summary>
        /// intent名からGapカテゴリを推定する。
        /// 命名規則 "gesture_*" → missing_motion 等。
        /// </summary>
        internal static string CategorizeGap(string intent)
        {
            if (string.IsNullOrEmpty(intent))    return "unknown";
            if (intent.StartsWith("gesture_"))   return "missing_motion";
            if (intent.StartsWith("emote_"))     return "missing_motion";
            if (intent.StartsWith("event_"))     return "missing_behavior";
            if (intent.StartsWith("integrate_")) return "missing_integration";
            if (intent.StartsWith("env_"))       return "environment_limit";
            return "capability_limit";
        }
    }
}
```

### 4.2 AvatarControllerへの追加メソッド

`ActionDispatcher` から呼び出すために以下の `public` メソッドを `AvatarController` に追加する。

```csharp
// AvatarController.cs に追加するpublicメソッド

// ── Growth System hooks ───────────────────────────────────────────

/// <summary>ActionDispatcherがBehaviorPolicy経由でUpdateを適用する。</summary>
public void ApplyFromPolicy(string emotion, string gesture, string lookTarget)
{
    // 引数がnull/空の場合は現在値を保持（nullは「変更しない」の意味）
    if (!string.IsNullOrEmpty(emotion))    _currentEmotion    = emotion;
    if (!string.IsNullOrEmpty(gesture))    _currentGesture    = gesture;
    if (!string.IsNullOrEmpty(lookTarget)) _currentLookTarget = lookTarget;

    if (!string.IsNullOrEmpty(emotion))    ApplyEmotion(_currentEmotion);
    if (!string.IsNullOrEmpty(gesture))    ApplyGesture(_currentGesture);
    if (!string.IsNullOrEmpty(lookTarget)) ApplyLookTarget(_currentLookTarget);
}

/// <summary>ActionDispatcherがBehaviorPolicy経由でEventを発火する。</summary>
public void TriggerEventFromPolicy(string eventName, float intensity)
{
    if (string.IsNullOrEmpty(eventName)) return;
    HandleEvent(new AvatarEventParams { @event = eventName, intensity = intensity });
}

/// <summary>ActionDispatcherがGapContext取得に使用する。</summary>
public string CurrentEmotion    => _currentEmotion;
public string CurrentLookTarget => _currentLookTarget;
```

---

## 5. AvatarMessage.cs への変更

`HandleMessage` に `avatar_intent` ケースを追加し、`ActionDispatcher` に委譲する。

```csharp
// AvatarMessage.cs: AvatarIntentParams追加

[Serializable]
public class AvatarIntentParams
{
    public string intent  = "";
    public string fallback = "";
    public string context_json = "";
}

internal class AvatarIntentEnvelope
{
    public string id;
    public string ts;
    public string cmd;
    public AvatarIntentParams @params;
}

// AvatarMessageParser.Parse() の switch に追加:
case "avatar_intent":
    var intentEnv = JsonUtility.FromJson<AvatarIntentEnvelope>(json);
    typed = intentEnv?.@params;
    break;
```

```csharp
// AvatarController.HandleMessage() の switch に追加:
case "avatar_intent":
    HandleIntent(typedParams as AvatarIntentParams);
    break;

// 追加メソッド:
private void HandleIntent(AvatarIntentParams p)
{
    var dispatcher = ActionDispatcher.Instance;
    if (dispatcher != null)
        dispatcher.Dispatch(p, _currentGesture);
    else
        Debug.LogWarning("[AvatarCtrl] avatar_intent received but ActionDispatcher not found.");
}
```

---

## 6. BehaviorPolicy YAMLスキーマ

```yaml
# StreamingAssets/behavior_policy.yml
# キー: intent名 (ActionDispatcherのルックアップキー)
# 形式: シンプルな "key: value" 行指向YAML (ネストなし)
# パーサー: BehaviorPolicyLoader (自前実装)はネストなし形式のみ対応

# --- エントリ区切りは "- intent:" 行 ---

- intent: nod_agreement
  cmd: avatar_update
  gesture: nod
  priority: 0
  notes: 同意・相槌のジェスチャー（実装済み）

- intent: shake_disagreement
  cmd: avatar_update
  gesture: shake
  priority: 0
  notes: 否定・首振りのジェスチャー（実装済み）

- intent: wave_greeting
  cmd: avatar_update
  gesture: wave
  priority: 0
  notes: 挨拶の手振り（実装済み）

- intent: look_at_comment
  cmd: avatar_event
  event: comment_read_start
  intensity: 1.0
  priority: 0
  notes: コメントエリアへ視線移動（実装済み・comment_read_startに対応）

- intent: express_happy
  cmd: avatar_update
  emotion: happy
  priority: 0
  notes: 喜び表情

- intent: express_surprised
  cmd: avatar_update
  emotion: surprised
  priority: 0
  notes: 驚き表情
```

---

## 7. テスト仕様

### 7.1 EditModeテスト: BehaviorPolicyLoaderTests

```csharp
// Assets/Tests/EditMode/BehaviorPolicyLoaderTests.cs
// [TC-BPOL-01] ~ [TC-BPOL-05]

[TestFixture]
public class BehaviorPolicyLoaderTests
{
    private BehaviorPolicyLoader _loader;

    [SetUp]
    public void SetUp()
    {
        var go = new GameObject("BPL");
        _loader = go.AddComponent<BehaviorPolicyLoader>();
        // Awake()はAddComponent時に呼ばれるが、Loadはファイル依存
        // テストではParseYamlLinesを直接呼ぶ
    }

    [TearDown]
    public void TearDown() => Object.DestroyImmediate(_loader.gameObject);

    // [TC-BPOL-01] 正常なYAML行列をパースするとentryが辞書に登録される
    [Test]
    public void ParseYamlLines_ValidEntry_RegistersEntry()
    {
        var lines = new[]
        {
            "- intent: nod_agreement",
            "  cmd: avatar_update",
            "  gesture: nod",
            "  priority: 0"
        };
        _loader.ParseYamlLines(lines);
        var entry = _loader.Lookup("nod_agreement");
        Assert.IsNotNull(entry);
        Assert.AreEqual("nod", entry.gesture);
        Assert.AreEqual("avatar_update", entry.cmd);
    }

    // [TC-BPOL-02] intentフィールドが空のエントリは無視される
    [Test]
    public void ParseYamlLines_EmptyIntent_Ignored()
    {
        var lines = new[]
        {
            "- intent:",
            "  cmd: avatar_update",
            "  gesture: nod"
        };
        _loader.ParseYamlLines(lines);
        Assert.AreEqual(0, _loader.Policy.Count);
    }

    // [TC-BPOL-03] 未登録intentのLookupはnullを返す（例外なし）
    [Test]
    public void Lookup_UnregisteredIntent_ReturnsNull()
    {
        Assert.IsNull(_loader.Lookup("no_such_intent"));
        Assert.IsNull(_loader.Lookup(""));
        Assert.IsNull(_loader.Lookup(null));
    }

    // [TC-BPOL-04] 複数エントリが正しく登録される
    [Test]
    public void ParseYamlLines_MultipleEntries_AllRegistered()
    {
        var lines = new[]
        {
            "- intent: gesture_a",
            "  cmd: avatar_update",
            "  gesture: wave",
            "- intent: gesture_b",
            "  cmd: avatar_event",
            "  event: comment_read_start",
            "  intensity: 1.0"
        };
        _loader.ParseYamlLines(lines);
        Assert.AreEqual(2, _loader.Policy.Count);
        Assert.IsNotNull(_loader.Lookup("gesture_a"));
        Assert.IsNotNull(_loader.Lookup("gesture_b"));
    }

    // [TC-BPOL-05] #コメント行はスキップされる
    [Test]
    public void ParseYamlLines_CommentLines_Skipped()
    {
        var lines = new[]
        {
            "# これはコメント",
            "- intent: nod_agreement",
            "  # インラインコメント",
            "  cmd: avatar_update",
            "  gesture: nod"
        };
        _loader.ParseYamlLines(lines);
        Assert.AreEqual(1, _loader.Policy.Count);
    }
}
```

---

### 7.2 EditModeテスト: GapLoggerTests

```csharp
// Assets/Tests/EditMode/GapLoggerTests.cs
// [TC-GLOG-01] ~ [TC-GLOG-05]

[TestFixture]
public class GapLoggerTests
{
    private GapLogger _logger;
    private string _tempPath;

    [SetUp]
    public void SetUp()
    {
        var go = new GameObject("GL");
        _logger = go.AddComponent<GapLogger>();
        _tempPath = Path.Combine(Path.GetTempPath(), $"gap_test_{Guid.NewGuid()}.jsonl");
        _logger.SetLogPathForTest(_tempPath);
        _logger.SetEnabled(true);
    }

    [TearDown]
    public void TearDown()
    {
        if (File.Exists(_tempPath)) File.Delete(_tempPath);
        Object.DestroyImmediate(_logger.gameObject);
    }

    // [TC-GLOG-01] Log()を呼ぶとファイルにJSON行が書き出される
    [Test]
    public void Log_ValidEntry_WritesJsonLine()
    {
        var entry = new GapEntry
        {
            intended_action = new GapEntry.IntendedAction { name = "point_at_screen" },
            fallback_used = "nod",
            gap_category = "missing_motion"
        };
        _logger.Log(entry);

        Assert.IsTrue(File.Exists(_tempPath));
        string content = File.ReadAllText(_tempPath);
        Assert.IsTrue(content.Contains("\"point_at_screen\""));
        Assert.IsTrue(content.Contains("\"nod\""));
        Assert.IsTrue(content.Contains("\"missing_motion\""));
    }

    // [TC-GLOG-02] 複数回Log()を呼ぶと行が複数追記される
    [Test]
    public void Log_MultipleCalls_AppendsLines()
    {
        for (int i = 0; i < 3; i++)
        {
            _logger.Log(new GapEntry
            {
                intended_action = new GapEntry.IntendedAction { name = $"intent_{i}" },
                fallback_used = "nod"
            });
        }
        string[] lines = File.ReadAllLines(_tempPath);
        Assert.AreEqual(3, lines.Length);
        Assert.AreEqual(3, _logger.GapCountThisSession);
    }

    // [TC-GLOG-03] timestampフィールドが自動設定される（空でない）
    [Test]
    public void Log_TimestampAutoSet()
    {
        _logger.Log(new GapEntry
        {
            intended_action = new GapEntry.IntendedAction { name = "x" }
        });
        string content = File.ReadAllText(_tempPath);
        Assert.IsTrue(content.Contains("\"timestamp\":\"20"));  // "2026..."など
    }

    // [TC-GLOG-04] nullエントリを渡しても例外が発生しない
    [Test]
    public void Log_NullEntry_NoException()
    {
        Assert.DoesNotThrow(() => _logger.Log(null));
    }

    // [TC-GLOG-05] enabled=falseの場合は書き込まれない
    [Test]
    public void Log_Disabled_NoWrite()
    {
        _logger.SetEnabled(false);
        _logger.Log(new GapEntry
        {
            intended_action = new GapEntry.IntendedAction { name = "x" }
        });
        Assert.IsFalse(File.Exists(_tempPath));
    }
}
```

---

### 7.3 EditModeテスト: ActionDispatcherTests

```csharp
// Assets/Tests/EditMode/ActionDispatcherTests.cs
// [TC-ADSP-01] ~ [TC-ADSP-08]

[TestFixture]
public class ActionDispatcherTests
{
    private ActionDispatcher _dispatcher;
    private GapLogger _logger;
    private BehaviorPolicyLoader _policyLoader;
    private string _tempLogPath;

    [SetUp]
    public void SetUp()
    {
        var go = new GameObject("AD");

        _dispatcher  = go.AddComponent<ActionDispatcher>();
        _logger      = go.AddComponent<GapLogger>();
        _policyLoader = go.AddComponent<BehaviorPolicyLoader>();

        _tempLogPath = Path.Combine(Path.GetTempPath(), $"gap_test_{Guid.NewGuid()}.jsonl");
        _logger.SetLogPathForTest(_tempLogPath);
        _logger.SetEnabled(true);

        // ポリシーを注入
        _policyLoader.InjectForTest(new Dictionary<string, BehaviorEntry>
        {
            ["nod_agreement"] = new BehaviorEntry
            {
                intent = "nod_agreement",
                cmd = "avatar_update",
                gesture = "nod"
            }
        });
    }

    [TearDown]
    public void TearDown()
    {
        if (File.Exists(_tempLogPath)) File.Delete(_tempLogPath);
        Object.DestroyImmediate(_dispatcher.gameObject);
    }

    // [TC-ADSP-01] ポリシーに登録されたintentはExecutedを返す
    [Test]
    public void Dispatch_PolicyHit_ReturnsExecuted()
    {
        var p = new AvatarIntentParams { intent = "nod_agreement" };
        var result = _dispatcher.Dispatch(p);
        Assert.AreEqual(ActionDispatcher.DispatchResult.Executed, result);
    }

    // [TC-ADSP-02] ポリシーHitの場合GapLoggerに記録しない
    [Test]
    public void Dispatch_PolicyHit_NoGapLogged()
    {
        var p = new AvatarIntentParams { intent = "nod_agreement" };
        _dispatcher.Dispatch(p);
        Assert.AreEqual(0, _logger.GapCountThisSession);
    }

    // [TC-ADSP-03] 未登録intentはFallbackExecuted or Skippedを返す
    [Test]
    public void Dispatch_UnknownIntent_ReturnsFallbackOrSkipped()
    {
        var p = new AvatarIntentParams { intent = "point_at_screen", fallback = "nod" };
        var result = _dispatcher.Dispatch(p);
        Assert.AreEqual(ActionDispatcher.DispatchResult.FallbackExecuted, result);
    }

    // [TC-ADSP-04] 未登録intentはGapLoggerに記録される
    [Test]
    public void Dispatch_UnknownIntent_GapLogged()
    {
        var p = new AvatarIntentParams { intent = "point_at_screen", fallback = "nod" };
        _dispatcher.Dispatch(p);
        Assert.AreEqual(1, _logger.GapCountThisSession);

        string content = File.ReadAllText(_tempLogPath);
        Assert.IsTrue(content.Contains("\"point_at_screen\""));
        Assert.IsTrue(content.Contains("\"nod\""));
    }

    // [TC-ADSP-05] fallbackが"none"または空の場合はSkippedを返す
    [Test]
    public void Dispatch_UnknownIntent_EmptyFallback_ReturnsSkipped()
    {
        var p = new AvatarIntentParams { intent = "unknown_xyz", fallback = "" };
        var result = _dispatcher.Dispatch(p);
        Assert.AreEqual(ActionDispatcher.DispatchResult.Skipped, result);
    }

    // [TC-ADSP-06] nullパラメーターはErrorを返す（例外なし）
    [Test]
    public void Dispatch_NullParams_ReturnsError()
    {
        var result = _dispatcher.Dispatch(null);
        Assert.AreEqual(ActionDispatcher.DispatchResult.Error, result);
    }

    // [TC-ADSP-07] 未登録intentのGapカテゴリが命名規則で自動推定される
    [Test]
    public void CategorizeGap_ByNamingConvention()
    {
        Assert.AreEqual("missing_motion",      ActionDispatcher.CategorizeGap("gesture_point_forward"));
        Assert.AreEqual("missing_motion",      ActionDispatcher.CategorizeGap("emote_laugh_big"));
        Assert.AreEqual("missing_behavior",    ActionDispatcher.CategorizeGap("event_superchat"));
        Assert.AreEqual("missing_integration", ActionDispatcher.CategorizeGap("integrate_bgm"));
        Assert.AreEqual("environment_limit",   ActionDispatcher.CategorizeGap("env_prop_book"));
        Assert.AreEqual("capability_limit",    ActionDispatcher.CategorizeGap("do_something_new"));
        Assert.AreEqual("unknown",             ActionDispatcher.CategorizeGap(""));
        Assert.AreEqual("unknown",             ActionDispatcher.CategorizeGap(null));
    }

    // [TC-ADSP-08] 同一セッションで複数Gapが記録される
    [Test]
    public void Dispatch_MultipleGaps_AllLogged()
    {
        _dispatcher.Dispatch(new AvatarIntentParams { intent = "gesture_a", fallback = "nod" });
        _dispatcher.Dispatch(new AvatarIntentParams { intent = "gesture_b", fallback = "nod" });
        _dispatcher.Dispatch(new AvatarIntentParams { intent = "gesture_c", fallback = "" });
        Assert.AreEqual(3, _logger.GapCountThisSession);
    }
}
```

---

### 7.4 EditModeテスト: AvatarMessageParserTests（avatar_intent追加）

```csharp
// Assets/Tests/EditMode/AvatarMessageParserTests.cs
// [TC-MSG-01] ~ [TC-MSG-04]

[TestFixture]
public class AvatarMessageParserTests
{
    // [TC-MSG-01] avatar_intentコマンドがAvatarIntentParamsにパースされる
    [Test]
    public void Parse_AvatarIntent_ReturnsIntentParams()
    {
        string json = @"{""cmd"":""avatar_intent"",""params"":{""intent"":""point_at_screen"",""fallback"":""nod""}}";
        var (msg, typed) = AvatarMessageParser.Parse(json);
        Assert.AreEqual("avatar_intent", msg.cmd);
        Assert.IsInstanceOf<AvatarIntentParams>(typed);
        var p = (AvatarIntentParams)typed;
        Assert.AreEqual("point_at_screen", p.intent);
        Assert.AreEqual("nod", p.fallback);
    }

    // [TC-MSG-02] intentフィールドなしでも例外が発生しない
    [Test]
    public void Parse_AvatarIntent_MissingFields_NoException()
    {
        string json = @"{""cmd"":""avatar_intent"",""params"":{}}";
        Assert.DoesNotThrow(() => AvatarMessageParser.Parse(json));
    }

    // [TC-MSG-03] 既存コマンドが引き続きパースされる（後方互換性）
    [Test]
    public void Parse_AvatarUpdate_BackwardCompatible()
    {
        string json = @"{""cmd"":""avatar_update"",""params"":{""emotion"":""happy""}}";
        var (msg, typed) = AvatarMessageParser.Parse(json);
        Assert.AreEqual("avatar_update", msg.cmd);
        Assert.IsInstanceOf<AvatarUpdateParams>(typed);
    }

    // [TC-MSG-04] 不正JSONはnullを返す（例外なし）
    [Test]
    public void Parse_InvalidJson_ReturnsNull()
    {
        var (msg, typed) = AvatarMessageParser.Parse("not_json{{{");
        Assert.IsNull(msg);
    }
}
```

---

### 7.5 PlayModeテスト: GrowthIntegrationTests

```csharp
// Assets/Tests/PlayMode/GrowthIntegrationTests.cs
// [TC-INTG-01] ~ [TC-INTG-03]
// PlayModeテスト: AvatarControllerを含む実際のシーン構成で動作を確認

[UnityTestFixture]
public class GrowthIntegrationTests
{
    private GameObject _root;
    private AvatarController _controller;
    private ActionDispatcher _dispatcher;
    private GapLogger _logger;
    private string _tempLogPath;

    [UnitySetUp]
    public IEnumerator SetUp()
    {
        _root = new GameObject("IntegrationRoot");
        _controller = _root.AddComponent<AvatarController>();
        _dispatcher = _root.AddComponent<ActionDispatcher>();
        _logger = _root.AddComponent<GapLogger>();

        _tempLogPath = Path.Combine(Path.GetTempPath(), $"intg_{Guid.NewGuid()}.jsonl");
        _logger.SetLogPathForTest(_tempLogPath);

        yield return null; // Awake完了まで待機
    }

    [UnityTearDown]
    public IEnumerator TearDown()
    {
        if (File.Exists(_tempLogPath)) File.Delete(_tempLogPath);
        Object.Destroy(_root);
        yield return null;
    }

    // [TC-INTG-01] avatar_intentメッセージ → ActionDispatcher経由 → Gapが記録される
    [UnityTest]
    public IEnumerator WsMessage_AvatarIntent_TriggersGapLog()
    {
        string json = @"{""cmd"":""avatar_intent"",""params"":{""intent"":""gesture_dance"",""fallback"":""nod""}}";
        var (msg, typed) = AvatarMessageParser.Parse(json);
        // HandleMessageを直接呼ぶ（WSClient不要）
        _controller.HandleMessageForTest(msg, typed);

        yield return null;

        Assert.AreEqual(1, _logger.GapCountThisSession,
            "gesture_dance はポリシー未登録なのでGapが1件記録されるべき");
    }

    // [TC-INTG-02] ポリシー登録済みintentはGapを記録しない
    [UnityTest]
    public IEnumerator WsMessage_PolicyHitIntent_NoGapLog()
    {
        // ポリシーを注入
        var loader = _root.AddComponent<BehaviorPolicyLoader>();
        loader.InjectForTest(new Dictionary<string, BehaviorEntry>
        {
            ["nod_agreement"] = new BehaviorEntry { intent = "nod_agreement", cmd = "avatar_update", gesture = "nod" }
        });

        string json = @"{""cmd"":""avatar_intent"",""params"":{""intent"":""nod_agreement""}}";
        var (msg, typed) = AvatarMessageParser.Parse(json);
        _controller.HandleMessageForTest(msg, typed);

        yield return null;

        Assert.AreEqual(0, _logger.GapCountThisSession,
            "ポリシーヒットのためGapは記録されない");
    }

    // [TC-INTG-03] avatar_update (既存コマンド) は引き続き正常動作する
    [UnityTest]
    public IEnumerator WsMessage_AvatarUpdate_StillWorks()
    {
        string json = @"{""cmd"":""avatar_update"",""params"":{""emotion"":""happy"",""gesture"":""wave""}}";
        var (msg, typed) = AvatarMessageParser.Parse(json);
        _controller.HandleMessageForTest(msg, typed);

        yield return null;

        Assert.AreEqual("happy", _controller.CurrentEmotion);
        Assert.AreEqual(0, _logger.GapCountThisSession,
            "avatar_updateはActionDispatcherを通らずGapは記録されない");
    }
}
```

---

## 8. テストマトリックス

| TC ID | コンポーネント | テスト内容 | モード | 優先度 |
|---|---|---|---|---|
| TC-BPOL-01 | BehaviorPolicyLoader | 正常YAML行→エントリ登録 | EditMode | High |
| TC-BPOL-02 | BehaviorPolicyLoader | 空intentエントリは無視 | EditMode | High |
| TC-BPOL-03 | BehaviorPolicyLoader | 未登録Lookupはnull | EditMode | High |
| TC-BPOL-04 | BehaviorPolicyLoader | 複数エントリ登録 | EditMode | Medium |
| TC-BPOL-05 | BehaviorPolicyLoader | コメント行スキップ | EditMode | Medium |
| TC-GLOG-01 | GapLogger | Log→ファイルにJSON行出力 | EditMode | High |
| TC-GLOG-02 | GapLogger | 複数Log→行追記 | EditMode | High |
| TC-GLOG-03 | GapLogger | timestamp自動設定 | EditMode | High |
| TC-GLOG-04 | GapLogger | nullエントリ→例外なし | EditMode | High |
| TC-GLOG-05 | GapLogger | disabled→書き込みなし | EditMode | Medium |
| TC-ADSP-01 | ActionDispatcher | PolicyHit→Executed | EditMode | High |
| TC-ADSP-02 | ActionDispatcher | PolicyHit→Gap記録なし | EditMode | High |
| TC-ADSP-03 | ActionDispatcher | 未登録→FallbackExecuted | EditMode | High |
| TC-ADSP-04 | ActionDispatcher | 未登録→Gap記録あり | EditMode | High |
| TC-ADSP-05 | ActionDispatcher | 空fallback→Skipped | EditMode | Medium |
| TC-ADSP-06 | ActionDispatcher | nullパラメーター→Error・例外なし | EditMode | High |
| TC-ADSP-07 | ActionDispatcher | Gapカテゴリ命名規則推定 | EditMode | Medium |
| TC-ADSP-08 | ActionDispatcher | 複数Gap記録 | EditMode | Medium |
| TC-MSG-01 | AvatarMessageParser | avatar_intent→AvatarIntentParamsパース | EditMode | High |
| TC-MSG-02 | AvatarMessageParser | 不完全intentフィールド→例外なし | EditMode | High |
| TC-MSG-03 | AvatarMessageParser | 既存コマンド後方互換 | EditMode | High |
| TC-MSG-04 | AvatarMessageParser | 不正JSON→null返却 | EditMode | High |
| TC-INTG-01 | 統合 | avatar_intent→Gap記録エンドツーエンド | PlayMode | High |
| TC-INTG-02 | 統合 | PolicyHit→Gap記録なし エンドツーエンド | PlayMode | High |
| TC-INTG-03 | 統合 | avatar_update後方互換（Gap記録なし） | PlayMode | High |

**合計**: 24テストケース（EditMode: 21 / PlayMode: 3）

---

## 9. 実装順序

M1実装は以下の順序で進める。後のステップが前のステップに依存する。

```
Step 1: GapEntry.cs               // データのみ・依存なし
Step 2: BehaviorEntry.cs          // データのみ・依存なし
Step 3: AvatarMessage.cs 修正     // AvatarIntentParams追加
Step 4: GapLogger.cs              // GapEntry依存
Step 5: BehaviorPolicyLoader.cs   // BehaviorEntry依存
Step 6: ActionDispatcher.cs       // 全依存
Step 7: AvatarController.cs 修正  // ApplyFromPolicy等追加・HandleIntent追加
Step 8: behavior_policy.yml       // 初期ポリシー
Step 9: テストファイル作成        // 全ステップ完了後
Step 10: behavior_policy.yml 検証 // ActionDispatcher + テスト動作確認
```

---

## 10. 受け入れ基準

M1完了の判定基準:

- [ ] 全24テストケースがパス（Unity Test Runner: EditMode + PlayMode）
- [ ] Play Mode中にWebSocketで `avatar_intent` を送信すると `Logs/capability_gaps/` にJSONLが書き出される
- [ ] ポリシー登録済みintentではGapが記録されない
- [ ] 既存の `avatar_update` / `avatar_event` コマンドが引き続き正常動作する（回帰なし）
- [ ] `_logger.GapCountThisSession` が配信セッション中に正しく増加する
- [ ] `autonomous-growth.md` M1チェックボックスにチェックが入る
