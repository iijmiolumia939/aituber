// TC-DEBUG: 行動シーケンスの手動テスト用コンポーネント（テスト完了後削除可）
using UnityEngine;

namespace AITuber.Behavior
{
    /// <summary>
    /// Inspector の Context Menu から BehaviorSequenceRunner を手動起動するデバッグ用コンポーネント。
    /// テスト確認後に削除してよい。
    /// </summary>
    public class DebugBehaviorTrigger : MonoBehaviour
    {
        [ContextMenu("Test: go_sleep")]
        void TestSleep() => BehaviorSequenceRunner.Instance?.StartBehavior("go_sleep");

        [ContextMenu("Test: go_stream")]
        void TestStream() => BehaviorSequenceRunner.Instance?.StartBehavior("go_stream");

        [ContextMenu("Test: go_eat")]
        void TestEat() => BehaviorSequenceRunner.Instance?.StartBehavior("go_eat");

        [ContextMenu("Test: go_read")]
        void TestRead() => BehaviorSequenceRunner.Instance?.StartBehavior("go_read");

        [ContextMenu("Test: go_walk")]
        void TestWalk() => BehaviorSequenceRunner.Instance?.StartBehavior("go_walk");

        [ContextMenu("Test: go_stretch")]
        void TestStretch() => BehaviorSequenceRunner.Instance?.StartBehavior("go_stretch");

        [ContextMenu("Test: go_wake")]
        void TestWake() => BehaviorSequenceRunner.Instance?.StartBehavior("go_wake");

        [ContextMenu("Stop Behavior")]
        void StopBehavior() => BehaviorSequenceRunner.Instance?.StopBehavior();
    }
}
