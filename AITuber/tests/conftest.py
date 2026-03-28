"""pytest 共通設定 – メモリ節約・GC 制御.

バッチ実行推奨: run_tests.ps1 を使うとファイル単位で別プロセス実行されるため、
OS がバッチ終了ごとにメモリを完全回収し 32GB OOM を防げる。
  .\run_tests.ps1                   # 通常
  .\run_tests.ps1 -BatchSize 2      # メモリが厳しいとき
"""

from __future__ import annotations

import gc

import pytest


@pytest.fixture(autouse=True)
def _gc_after_test() -> None:  # type: ignore[return]
    """テスト前後に GC を 2 世代分強制実行。

    - yield 前: 前テストの残留オブジェクトを解放してからテスト開始
    - yield 後: AsyncMock/Mock の循環参照・残留 coroutine を即時回収

    asyncio_mode=auto の async テストは event loop が閉じた直後に
    この fixture が yield 後処理を実行するため、loop 内オブジェクトも回収される。
    """
    gc.collect()  # 前テスト残留を先に解放
    yield
    gc.collect()  # 今テストの残留を解放
