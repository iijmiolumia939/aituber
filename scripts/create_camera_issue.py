#!/usr/bin/env python3
"""Create GitHub Issue E-8: Virtual Camera World + Self-Perception"""
import json
import urllib.request

REPO = "iijmiolumia939/aituber"
TOKEN = open(
    "scripts/create_embodied_ai_issues.py", encoding="utf-8"
).read().split('TOKEN  = "')[1].split('"')[0]

HEADERS = {
    "Authorization": f"token {TOKEN}",
    "Accept": "application/vnd.github+json",
    "Content-Type": "application/json",
}


def api(method, url, data=None):
    req = urllib.request.Request(url, headers=HEADERS, method=method)
    if data:
        req.data = json.dumps(data).encode()
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


body = """\
## 概要

Unity ワールド上に複数の仮想カメラを配置し、YouTube 配信ではそのカメラ映像を使用する。
アバター (YUI.A) は「今どのカメラで自分がどう映っているか」を認識し、
最適なカメラへの自律切替や自己表現の調整ができる。

アバターが「自分の OBS 画面を見ながら配信を演出している」という体験を実現する。

## 背景・動機

現在の配信構成ではカメラ位置が固定で、YUI.A は自分がどう映っているかを認識できない。
Embodied AI として Unity の世界に「体を持つ」ならば、視覚フィードバックによる自己認識と
演出判断が自然な拡張となる。

参考:
- Park et al. (2023) "Generative Agents" (arXiv:2304.03442):
  エージェントが自分の行動と周囲への影響を観察・記憶して次の行動を計画する
- Durante et al. (2024) "Agent AI" (arXiv:2401.03568):
  マルチモーダル知覚 (視覚) を意思決定に統合する

## アーキテクチャ設計

```
[Unity World]
  VirtualCamera_A (正面) ─┐
  VirtualCamera_B (斜め)  ├─→ [VirtualCameraManager.cs]
  VirtualCamera_C (引き)  ┘     ↓ active_camera_index
                                WS {"type":"camera_switched","camera":"A"}
                                     ↓
                            [OBSController (Python)]
                              SetCurrentProgramScene("Scene_CamA")
                              or SetSceneItemEnabled(camA_source, true)

[Self-Perception Loop]
  OBSController.GetSourceScreenshot()
    → base64 PNG
    → VisionPerception.analyze(image, prompt="あなたはどう映っていますか？")
    → AvatarSelfState { composition, emotion_visible, framing }
    → Orchestrator LLM context に注入
    → 必要なら intent_camera_switch を生成
```

## コンポーネント詳細

### Unity C# (Assets/Scripts/)

#### `VirtualCameraManager.cs`
```csharp
// FR-CAM-01: 複数カメラの登録・切替
public class VirtualCameraManager : MonoBehaviour
{
    [SerializeField] Camera[] _cameras;      // Inspector で配置
    [SerializeField] RenderTexture[] _rts;   // 各カメラのRenderTexture
    public int ActiveIndex { get; private set; }

    // WS message: {"type":"camera_switch","index":1}
    public void SwitchCamera(int index);
    public Texture2D CaptureFrame(int index); // 自己視覚用キャプチャ
}
```

#### `CameraPerceptionReporter.cs`
```csharp
// FR-CAM-02: アバターへの自己視覚フィードバック
// 定期的に active カメラの RenderTexture を PNG エンコード → WS送信
// {"type":"camera_frame","camera":"A","base64":"...","width":320,"height":180}
```

### Python (orchestrator/)

#### `obs_camera_controller.py`
```python
# OBS シーン/ソース操作
class OBSCameraController:
    def switch_to_scene(self, scene_name: str)  # SetCurrentProgramScene
    def set_source_visible(self, scene, source, visible: bool)  # SetSceneItemEnabled
    def get_screenshot(self, source_name: str) -> bytes  # GetSourceScreenshot
```

#### `vision_perception.py`
```python
# GPT-4o Vision で自己映像を分析
class VisionPerception:
    async def analyze_self(self, image_b64: str) -> SelfViewState:
        # prompt: "あなたはYUI.Aというアバターです。この映像で自分がどう映っているか教えてください"
        # return: { "framing": "too_close|good|too_far", "emotion_visible": bool, "suggestion": str }
```

#### `camera_context.py`
```python
# Orchestrator の LLM context にカメラ状態を注入
class CameraContext:
    active_camera: str           # "A" | "B" | "C"
    last_self_view: SelfViewState
    available_cameras: list[str]

    def to_prompt_fragment(self) -> str:
        # "[CAMERA] 現在カメラAで正面から映っています。フレーミングは良好です。"
```

#### WS intent (yuia.yml)
```yaml
- intent: camera_switch
  patterns:
    - "カメラ切り替えて"
    - "引きにして"
    - "アップにして"
  action: camera_switch
  params:
    camera: "{camera_id}"

- intent: check_self_view
  patterns:
    - "今どう映ってる"
    - "自分の映り確認して"
  action: request_self_perception
```

## OBS 連携設計

### パターンA: OBS シーン = カメラ (推奨)
```
OBS Scene: "CamA_正面"   → GameCapture / Virtual Camera A
OBS Scene: "CamB_斜め"   → GameCapture / Virtual Camera B
OBS Scene: "CamC_引き"   → GameCapture / Virtual Camera C

切替: SetCurrentProgramScene(scene_name)
```

### パターンB: 1シーン内でソース切替
```
OBS Scene: "Main"
  Source: "UnityCapture_A" (enabled/disabled)
  Source: "UnityCapture_B" (enabled/disabled)

切替: SetSceneItemEnabled(source_id, true/false)
```

### 自己視覚: GetSourceScreenshot
```json
{
  "requestType": "GetSourceScreenshot",
  "requestData": {
    "sourceName": "UnityCapture_A",
    "imageFormat": "png",
    "imageWidth": 320,
    "imageHeight": 180
  }
}
```
→ `imageData` (base64) を GPT-4o Vision に送信

## 実装タスク

### Unity C#
- [ ] `VirtualCameraManager.cs`: カメラ配列管理、WS受信でアクティブカメラ切替
- [ ] `CameraPerceptionReporter.cs`: RenderTexture → PNG → WS送信 (interval: 5s)
- [ ] WS protocol 拡張: `camera_switch`, `camera_frame` メッセージ型

### Python
- [ ] `obs_camera_controller.py`: シーン切替・ソース切替・スクリーンショット
- [ ] `vision_perception.py`: GPT-4o Vision 呼び出し + `SelfViewState`
- [ ] `camera_context.py`: Orchestrator context への統合
- [ ] `yuia.yml` intent 追加: `camera_switch`, `check_self_view`

### テスト
- `test_obs_camera_controller.py`: TC-CAM-01〜05 (OBS WS mock)
- `test_vision_perception.py`: TC-CAM-06〜10 (Vision API mock)
- `test_camera_context.py`: TC-CAM-11〜15 (context injection)
- Unity EditMode: TC-CAM-U-01〜05 (VirtualCameraManager)

## 機能要件 (FR/NFR)

- FR-CAM-01: Unity ワールドに複数カメラを配置し OBS ソースとして使えること
- FR-CAM-02: アバターが WS メッセージでカメラを切り替えられること
- FR-CAM-03: `GetSourceScreenshot` でアバターが自己映像を取得できること
- FR-CAM-04: GPT-4o Vision で自己映像を分析し `SelfViewState` を生成できること
- FR-CAM-05: 自己映像の分析結果が Orchestrator の LLM context に注入されること
- NFR-CAM-01: カメラフレーム送信は配信品質に影響しない低解像度 (320x180) で行うこと
- NFR-CAM-02: Vision API 呼び出しは最大 10s/回 (高頻度回避)

## Unity カメラ配置例

```
Scene
├── VirtualCamera_A [Camera, tag="StreamCam"]  position=(0,1.5,-2)  看板正面
├── VirtualCamera_B [Camera, tag="StreamCam"]  position=(1,1.2,-1.5) 斜め45度
└── VirtualCamera_C [Camera, tag="StreamCam"]  position=(0,3,-4)     引きショット
```

## 関連 Issue

- #17 E-7: 自律配信ライフサイクル — OBSController を共有使用  
- #11 E-1 Situatedness: ワールドコンテキストにカメラ情報を含める
- #14 E-4 AvatarPerception: 知覚システムの拡張としてカメラ視覚を統合

## 参考文献

- obs-websocket v5 `GetSourceScreenshot`, `SetCurrentProgramScene`: https://github.com/obsproject/obs-websocket
- OpenAI GPT-4o Vision API: https://platform.openai.com/docs/guides/vision
- Park et al. (2023) arXiv:2304.03442 — Generative Agents: self-observation
- Durante et al. (2024) arXiv:2401.03568 — Agent AI: multimodal visual perception
"""

result = api(
    "POST",
    f"https://api.github.com/repos/{REPO}/issues",
    {
        "title": "[Embodied AI] E-8: ワールド内仮想カメラ + アバター自己視覚 (OBS自律切替)",
        "body": body,
        "labels": ["embodied-ai", "enhancement"],
    },
)
print(f"✅ #{result['number']} {result['title']}")
print(f"   {result['html_url']}")
