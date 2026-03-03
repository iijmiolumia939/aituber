"""YouTube OAuth 2.0 認証セットアップ。

初回のみブラウザが開いて Google 認証画面が表示されます。
認証完了後、トークンが config/youtube_token.json に保存され、
以降は自動的にリフレッシュされます。

前提:
  1. Google Cloud Console で OAuth 2.0 クライアントIDを作成
  2. ダウンロードした JSON を config/client_secret.json に配置
  3. このスクリプトを実行: python tools/youtube_auth.py

参考: https://developers.google.com/youtube/v3/guides/authentication
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# YouTube Live Streaming API に必要なスコープ
SCOPES = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

PROJECT_ROOT = Path(__file__).parent.parent
CLIENT_SECRET_PATH = PROJECT_ROOT / "config" / "client_secret.json"
TOKEN_PATH = PROJECT_ROOT / "config" / "youtube_token.json"


def authenticate() -> Credentials:
    """OAuth 2.0 認証を実行し、Credentials を返す。

    既存トークンがあればリフレッシュ、なければブラウザ認証。
    """
    creds: Credentials | None = None

    # 既存トークンの読み込み
    if TOKEN_PATH.exists():
        from google.auth.transport.requests import Request

        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        if creds and creds.expired and creds.refresh_token:
            print("トークンをリフレッシュ中...")
            creds.refresh(Request())
            _save_token(creds)
            print("✅ トークンをリフレッシュしました")
            return creds
        if creds and creds.valid:
            print("✅ 既存トークンが有効です")
            return creds

    # 新規認証
    if not CLIENT_SECRET_PATH.exists():
        print(
            "ERROR: config/client_secret.json が見つかりません。\n"
            "\n"
            "セットアップ手順:\n"
            "  1. Google Cloud Console (https://console.cloud.google.com/) を開く\n"
            "  2. プロジェクトを選択 or 新規作成\n"
            "  3. 「APIとサービス」→「認証情報」→「認証情報を作成」→「OAuth クライアント ID」\n"
            "  4. アプリケーションの種類: 「デスクトップ アプリ」\n"
            "  5. 作成後、JSONをダウンロード\n"
            "  6. config/client_secret.json として保存\n"
            "  7. 「APIとサービス」→「ライブラリ」→ YouTube Data API v3 を有効化\n"
            "  8. OAuth 同意画面でテストユーザーに配信アカウントを追加\n",
            file=sys.stderr,
        )
        sys.exit(1)

    print("ブラウザで Google 認証画面を開きます...")
    flow = InstalledAppFlow.from_client_secrets_file(
        str(CLIENT_SECRET_PATH),
        scopes=SCOPES,
    )
    creds = flow.run_local_server(port=8090, prompt="consent")
    _save_token(creds)
    print(f"✅ 認証成功。トークンを保存しました: {TOKEN_PATH}")
    return creds


def _save_token(creds: Credentials) -> None:
    """トークンをファイルに保存。"""
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes or SCOPES,
    }
    TOKEN_PATH.write_text(json.dumps(token_data, indent=2), encoding="utf-8")


def load_credentials() -> Credentials:
    """保存済みトークンを読み込む。なければ認証フローを実行。"""
    if TOKEN_PATH.exists():
        from google.auth.transport.requests import Request

        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            _save_token(creds)
        if creds and creds.valid:
            return creds
    return authenticate()


if __name__ == "__main__":
    authenticate()
