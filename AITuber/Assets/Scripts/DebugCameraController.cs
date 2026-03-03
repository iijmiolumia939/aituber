// DebugCameraController.cs
// 開発時のカメラ自由操作スクリプト。
// Attach to Main Camera. キーボード + マウスでカメラを自由に動かせます。
//
// 操作方法:
//   W/S        : 前後移動
//   A/D        : 左右移動
//   Q/E        : 下上移動
//   右クリック + ドラッグ : 視点回転（Pitch / Yaw）
//   スクロール  : 前後移動（ズーム）
//   Shift      : 移動速度 x5
//   R          : 初期位置にリセット
//   F1         : デバッグ表示のオン/オフ
//
// ※ 本番ビルドでも有効ですが、UNITY_EDITOR 限定にしたい場合は
//   Start() の先頭に `if (!Debug.isDebugBuild) { enabled = false; return; }` を追加。

using UnityEngine;

namespace AITuber
{
    [RequireComponent(typeof(Camera))]
    public class DebugCameraController : MonoBehaviour
    {
        [Header("移動速度")]
        [SerializeField] private float _moveSpeed = 2f;
        [SerializeField] private float _fastMultiplier = 5f;
        [SerializeField] private float _scrollSpeed = 3f;

        [Header("回転感度")]
        [SerializeField] private float _rotSensitivity = 120f;

        [Header("デフォルト位置（R でリセット）")]
        [SerializeField] private Vector3 _defaultPosition = new Vector3(0f, 1.3f, 1.3f);
        [SerializeField] private Vector3 _defaultEuler    = new Vector3(0f, 180f, 0f);
        [SerializeField] private float   _defaultFov      = 40f;

        [Header("GUI")]
        [SerializeField] private bool _showGui = true;

        // ── private state ──────────────────────────────────────────────
        private Camera _cam;
        private float  _pitch;   // x 軸回転（上下）
        private float  _yaw;     // y 軸回転（左右）
        private bool   _dragging;
        private Vector3 _lastMousePos;

        // GUIスタイル（OnGUI 初回割り当て）
        private GUIStyle _boxStyle;
        private GUIStyle _labelStyle;

        // ──────────────────────────────────────────────────────────────

        private void Start()
        {
            _cam = GetComponent<Camera>();

            // 初期オイラー角を現在のトランスフォームから取得
            var e = transform.eulerAngles;
            _pitch = e.x;
            _yaw   = e.y;
        }

        private void Update()
        {
            HandleKeyboardMove();
            HandleMouseRotate();
            HandleScrollZoom();
            HandleReset();
            HandleToggleGui();
        }

        // ── 移動 ──────────────────────────────────────────────────────

        private void HandleKeyboardMove()
        {
            float speed = _moveSpeed * (Input.GetKey(KeyCode.LeftShift) ? _fastMultiplier : 1f);
            speed *= Time.deltaTime;

            Vector3 move = Vector3.zero;

            if (Input.GetKey(KeyCode.W) || Input.GetKey(KeyCode.UpArrow))    move += transform.forward;
            if (Input.GetKey(KeyCode.S) || Input.GetKey(KeyCode.DownArrow))  move -= transform.forward;
            if (Input.GetKey(KeyCode.D) || Input.GetKey(KeyCode.RightArrow)) move += transform.right;
            if (Input.GetKey(KeyCode.A) || Input.GetKey(KeyCode.LeftArrow))  move -= transform.right;
            if (Input.GetKey(KeyCode.E))                                      move += Vector3.up;
            if (Input.GetKey(KeyCode.Q))                                      move -= Vector3.up;

            transform.position += move * speed;
        }

        // ── 視点回転（右クリック + ドラッグ）────────────────────────

        private void HandleMouseRotate()
        {
            if (Input.GetMouseButtonDown(1))
            {
                _dragging = true;
                _lastMousePos = Input.mousePosition;
            }
            else if (Input.GetMouseButtonUp(1))
            {
                _dragging = false;
            }

            if (!_dragging) return;

            Vector3 delta = Input.mousePosition - _lastMousePos;
            _lastMousePos = Input.mousePosition;

            float sensitivity = _rotSensitivity * Time.deltaTime * 0.01f;
            _yaw   += delta.x * sensitivity;
            _pitch -= delta.y * sensitivity;
            _pitch  = Mathf.Clamp(_pitch, -89f, 89f);

            transform.rotation = Quaternion.Euler(_pitch, _yaw, 0f);
        }

        // ── スクロールズーム ──────────────────────────────────────────

        private void HandleScrollZoom()
        {
            float scroll = Input.GetAxis("Mouse ScrollWheel");
            if (Mathf.Abs(scroll) < 0.001f) return;
            transform.position += transform.forward * scroll * _scrollSpeed;
        }

        // ── リセット ─────────────────────────────────────────────────

        private void HandleReset()
        {
            if (Input.GetKeyDown(KeyCode.R))
            {
                transform.position = _defaultPosition;
                transform.eulerAngles = _defaultEuler;
                _pitch = _defaultEuler.x;
                _yaw   = _defaultEuler.y;
                if (_cam != null) _cam.fieldOfView = _defaultFov;
                Debug.Log("[DebugCamera] Reset to default position.");
            }
        }

        // ── GUI トグル ───────────────────────────────────────────────

        private void HandleToggleGui()
        {
            if (Input.GetKeyDown(KeyCode.F1))
                _showGui = !_showGui;
        }

        // ── デバッグ GUI ─────────────────────────────────────────────

        private void OnGUI()
        {
            if (!_showGui) return;

            if (_boxStyle == null)
            {
                _boxStyle = new GUIStyle(GUI.skin.box)
                {
                    fontSize  = 14,
                    alignment = TextAnchor.UpperLeft,
                };
                _labelStyle = new GUIStyle(GUI.skin.label)
                {
                    fontSize  = 13,
                    normal    = { textColor = Color.white },
                    alignment = TextAnchor.UpperLeft,
                };
            }

            var pos = transform.position;
            var rot = transform.eulerAngles;
            float fov = _cam != null ? _cam.fieldOfView : 0f;

            string text =
                $"[DebugCamera] F1: 非表示\n" +
                $"Pos  X:{pos.x:F3}  Y:{pos.y:F3}  Z:{pos.z:F3}\n" +
                $"Rot  P:{rot.x:F1}  Y:{rot.y:F1}\n" +
                $"FOV  {fov:F1}\n" +
                $"\n" +
                $"WASD/QE: 移動  Shift: 高速\n" +
                $"右クリック+ドラッグ: 回転\n" +
                $"スクロール: ズーム  R: リセット";

            float w = 310f, h = 155f;
            float x = 10f, y = 10f;

            // 背景
            GUI.color = new Color(0, 0, 0, 0.6f);
            GUI.Box(new Rect(x, y, w, h), GUIContent.none, _boxStyle);
            GUI.color = Color.white;

            GUI.Label(new Rect(x + 8f, y + 6f, w - 12f, h - 10f), text, _labelStyle);
        }
    }
}
