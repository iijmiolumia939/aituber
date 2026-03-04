"""アバター動作確認ツール — Python → Unity WebSocket 経路のインタラクティストテスト。

使い方:
  python -m orchestrator.debug_sender

動作:
  1. WS サーバーを起動 (Unity が接続してくる)
  2. Unity で Play Mode を開始 → 自動接続される
  3. メニューからジェスチャー / 感情 / リップシンクを選んで送信
  4. q で終了

VOICEVOX / YouTube API / LLM は不要。
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from orchestrator.avatar_ws import (
    AvatarMessage,
    AvatarWSSender,
    VisemeEvent,
)
from orchestrator.config import AvatarWSConfig

logging.basicConfig(level=logging.WARNING)  # WS 以外のログを抑制
logger = logging.getLogger(__name__)

# ── カラー出力 ────────────────────────────────────────────────────────
C_RESET = "\033[0m"
C_CYAN = "\033[36m"
C_GREEN = "\033[32m"
C_YELLOW = "\033[33m"
C_RED = "\033[31m"
C_GRAY = "\033[90m"
C_BOLD = "\033[1m"


def cprint(msg: str, color: str = C_RESET) -> None:
    print(f"{color}{msg}{C_RESET}")


# ── ジェスチャー / 感情マスター ────────────────────────────────────────
GESTURES: list[tuple[str, str]] = [
    # (コマンド名, 説明)
    ("none", "なし"),
    ("nod", "うなずく"),
    ("shake", "首を振る"),
    ("wave", "手を振る"),
    ("cheer", "両手挙げ"),
    ("shrug", "肩をすくめる"),
    ("facepalm", "顔を手で覆う"),
    ("shy", "恥ずかしい (Bashful)"),
    ("laugh", "笑い (Laughing)"),
    ("surprised", "驚き (Reacting)"),
    ("rejected", "拒否 (Rejected)"),
    ("sigh", "ため息 (Relieved Sigh)"),
    ("thankful", "感謝 (Thankful)"),
    ("sad_idle", "悲しみアイドル (Sad Idle) [ループ]"),
    ("sad_kick", "悲しみキック (Sad Idle kick)"),
    ("thinking", "考え中 (Thinking) [ループ]"),
    ("idle_alt", "代替アイドル (Idle) [ループ]"),
    ("sit_down", "座る (Sitting)"),
    ("sit_idle", "座りアイドル (Sitting Idle) [ループ]"),
    ("sit_laugh", "座り笑い (Sitting Laughing)"),
    ("sit_clap", "座り拍手 (Sitting Clap)"),
    ("sit_point", "座り指差し (Sitting And Pointing)"),
    ("sit_disbelief", "座り不信 (Sitting Disbelief)"),
    ("sit_kick", "座りキック (Sitting_kick)"),
]

EMOTIONS: list[tuple[str, str]] = [
    ("neutral", "ニュートラル"),
    ("happy", "ハッピー 😊"),
    ("thinking", "考え中 🤔"),
    ("surprised", "驚き 😮"),
    ("sad", "悲しみ 😢"),
    ("angry", "怒り 😠"),
    ("panic", "パニック 😱"),
]

LOOK_TARGETS: list[tuple[str, str]] = [
    ("camera", "カメラ（視聴者）"),
    ("chat", "チャット欄"),
    ("down", "下を向く"),
    ("random", "ランダム"),
]


# ── リップシンクデモ (日本語音節列) ──────────────────────────────────
class LipSyncDemo:
    """擬似的な音節タイムライン."""

    # (音素, オフセットms)
    SEQUENCES: dict[str, list[tuple[str, int]]] = {
        "あいうえお": [
            ("a", 0),
            ("i", 250),
            ("u", 500),
            ("e", 750),
            ("o", 1000),
            ("m", 1200),
            ("sil", 1400),
        ],
        "こんにちは": [
            ("o", 0),
            ("m", 150),
            ("i", 300),
            ("a", 450),
            ("a", 600),
            ("m", 750),
            ("sil", 900),
        ],
        "ありがとうございます": [
            ("a", 0),
            ("i", 150),
            ("a", 300),
            ("o", 450),
            ("u", 600),
            ("o", 750),
            ("a", 900),
            ("i", 1000),
            ("a", 1100),
            ("u", 1200),
            ("sil", 1400),
        ],
        "やばい！": [
            ("a", 0),
            ("a", 150),
            ("i", 300),
            ("sil", 450),
        ],
    }


# ── 送信ヘルパー ──────────────────────────────────────────────────────
async def send_update(
    sender: AvatarWSSender,
    gesture: str = "none",
    emotion: str = "neutral",
    look_target: str = "camera",
) -> None:
    msg = AvatarMessage(
        cmd="avatar_update",
        params={
            "gesture": gesture,
            "emotion": emotion,
            "look_target": look_target,
            "mouth_open": 0.0,
        },
    )
    await sender._send(msg)
    cprint(f"  → gesture={gesture}  emotion={emotion}  look={look_target}", C_GREEN)


async def send_viseme_sequence(
    sender: AvatarWSSender,
    sequence: list[tuple[str, int]],
    label: str,
) -> None:
    events = [VisemeEvent(t_ms=t, v=v) for v, t in sequence]
    await sender.send_viseme(
        utterance_id=uuid.uuid4().hex[:8],
        events=events,
        crossfade_ms=60,
        strength=0.9,
    )
    total_ms = sequence[-1][1] + 300
    cprint(f"  → viseme送信: {label}  ({len(events)} events, ~{total_ms}ms)", C_CYAN)
    # リアルタイムで口の動きを感じるため待機
    await asyncio.sleep(total_ms / 1000.0 + 0.2)


# ── メインメニュー ────────────────────────────────────────────────────
def print_header(connected: bool) -> None:
    cprint("\n" + "═" * 58, C_BOLD)
    cprint("  AITuber アバターデバッグ送信ツール", C_BOLD)
    not_connected = f"{C_RED}○ 未接続 (Unity Play Mode を起動してください)"
    status = f"{C_GREEN}● CONNECTED ({1})" if connected else not_connected
    cprint(f"  Unity: {status}{C_BOLD}", C_BOLD)
    cprint("═" * 58 + C_RESET, C_BOLD)


def print_menu() -> None:
    cprint("\n[メニュー]", C_YELLOW)
    print("  1) ジェスチャー送信")
    print("  2) 感情送信")
    print("  3) 視線ターゲット変更")
    print("  4) リップシンクデモ")
    print("  5) クイック組み合わせ送信")
    print("  r) リセット (neutral / none / camera)")
    print("  q) 終了")


def print_gesture_list() -> None:
    cprint("\n[ジェスチャー一覧]", C_CYAN)
    for i, (cmd, desc) in enumerate(GESTURES):
        print(f"  {i:2d}) {cmd:20s}  {C_GRAY}{desc}{C_RESET}")


def print_emotion_list() -> None:
    cprint("\n[感情一覧]", C_GREEN)
    for i, (cmd, desc) in enumerate(EMOTIONS):
        print(f"  {i}) {cmd:12s}  {desc}")


def print_look_list() -> None:
    cprint("\n[視線ターゲット]", C_YELLOW)
    for i, (cmd, desc) in enumerate(LOOK_TARGETS):
        print(f"  {i}) {cmd:10s}  {desc}")


def print_lipsync_list() -> None:
    cprint("\n[リップシンクデモ]", C_CYAN)
    items = list(LipSyncDemo.SEQUENCES.keys())
    for i, label in enumerate(items):
        seq = LipSyncDemo.SEQUENCES[label]
        print(f"  {i}) {label}  {C_GRAY}({len(seq)} events){C_RESET}")


def input_choice(prompt: str, count: int) -> int | None:
    raw = input(f"{prompt} [0-{count - 1}] > ").strip()
    if raw == "q":
        return None
    try:
        n = int(raw)
        if 0 <= n < count:
            return n
    except ValueError:
        pass
    cprint("  無効な入力です", C_RED)
    return -1


QUICK_COMBOS: list[tuple[str, str, str, str]] = [
    ("こんにちは！", "wave", "happy", "camera"),
    ("なるほどですね", "nod", "happy", "chat"),
    ("えー！まじで？", "surprised", "surprised", "camera"),
    ("うーん難しいな…", "thinking", "thinking", "down"),
    ("わーいやったー！", "cheer", "happy", "camera"),
    ("ちょっと悲しいな", "sad_idle", "sad", "down"),
    ("ふふ笑いたい", "laugh", "happy", "camera"),
    ("ため息…", "sigh", "sad", "down"),
    ("感謝！", "thankful", "happy", "camera"),
    ("びっくりした！", "surprised", "surprised", "camera"),
]


async def run_interactive(sender: AvatarWSSender) -> None:
    """インタラクティブメニューループ."""
    lip_seqs = list(LipSyncDemo.SEQUENCES.items())

    while True:
        print_header(sender.connected)
        print_menu()

        choice = input("\n選択 > ").strip().lower()

        if choice == "q":
            break

        elif choice == "r":
            await send_update(sender, "none", "neutral", "camera")
            cprint("  🔄 リセット完了", C_GRAY)

        elif choice == "1":
            print_gesture_list()
            idx = input_choice("ジェスチャー番号", len(GESTURES))
            if idx is None:
                break
            if idx >= 0:
                await send_update(sender, gesture=GESTURES[idx][0])

        elif choice == "2":
            print_emotion_list()
            idx = input_choice("感情番号", len(EMOTIONS))
            if idx is None:
                break
            if idx >= 0:
                await send_update(sender, emotion=EMOTIONS[idx][0])

        elif choice == "3":
            print_look_list()
            idx = input_choice("ターゲット番号", len(LOOK_TARGETS))
            if idx is None:
                break
            if idx >= 0:
                await send_update(sender, look_target=LOOK_TARGETS[idx][0])

        elif choice == "4":
            print_lipsync_list()
            idx = input_choice("シーケンス番号", len(lip_seqs))
            if idx is None:
                break
            if idx >= 0:
                label, seq = lip_seqs[idx]
                await send_viseme_sequence(sender, seq, label)

        elif choice == "5":
            cprint("\n[クイック組み合わせ]", C_YELLOW)
            for i, (label, g, e, _lt) in enumerate(QUICK_COMBOS):
                print(f"  {i}) {label:20s}  gesture={g}, emotion={e}")
            idx = input_choice("番号", len(QUICK_COMBOS))
            if idx is None:
                break
            if idx >= 0:
                _, g, e, lt = QUICK_COMBOS[idx]
                await send_update(sender, gesture=g, emotion=e, look_target=lt)

        else:
            cprint("  無効な入力", C_RED)

    cprint("\n終了します。\n", C_GRAY)


# ── エントリーポイント ─────────────────────────────────────────────────
async def main() -> None:
    cfg = AvatarWSConfig(host="127.0.0.1", port=31900)
    sender = AvatarWSSender(cfg)

    print()
    cprint("Avatar WS サーバーを起動中... (ws://127.0.0.1:31900)", C_YELLOW)
    await sender.start_server()
    cprint("✅ サーバー起動完了。Unity の接続を待っています...", C_GREEN)

    # Unity の再接続を最大 15 秒待つ (再接続間隔 3 秒 × 5 回)
    for i in range(30):
        if sender.connected:
            break
        await asyncio.sleep(0.5)
        if i % 6 == 5:
            elapsed = (i + 1) // 2
            cprint(f"  待機中 {elapsed}秒... (Unity Play Mode が起動していますか？)", C_GRAY)

    if sender.connected:
        cprint("✅ Unity 接続完了！\n", C_GREEN)
    else:
        cprint(
            "⚠  15秒待っても未接続です。そのまま操作できますがコマンドは届きません。\n"
            "  Unity の Console に [AvatarWS] のログが出ているか確認してください。\n",
            C_YELLOW,
        )

    try:
        await run_interactive(sender)
    finally:
        await sender.stop_server()


if __name__ == "__main__":
    # python orchestrator/debug_sender.py でも動く
    asyncio.run(main())
