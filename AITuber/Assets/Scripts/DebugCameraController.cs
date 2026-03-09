// DebugCameraController.cs
// 開発時のカメラ自由操作スクリプト。
// Attach to Main Camera. Sceneタブと同等のマウス操作でカメラを動かせます。
//
// 操作方法:
//   W/S/A/D/Q/E              : 移動（右クリック中も有効）
//   Shift                    : 移動速度 x5
//   右クリック + ドラッグ    : 視点回転（Pitch / Yaw）
//   中クリック + ドラッグ    : パン（カメラ平行移動）
//   Alt + 左クリック + ドラッグ : 注視点オービット
//   Alt + 右クリック + ドラッグ : ドリーズーム（注視点に接近/離反）
//   スクロール               : 前後移動（ズーム）
//   R                        : 初期位置にリセット
//   F1                       : デバッグ表示のオン/オフ

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

        [Header("回転感度（deg/pixel: sensitivity × 0.01）")]
        [SerializeField] private float _rotSensitivity = 10f;   // 0.1 deg/px (≈ Scene View)

        [Header("オービット感度（deg/pixel: sensitivity × 0.01）")]
        [SerializeField] private float _orbitSensitivity = 10f;

        [Header("ドリー感度")]
        [SerializeField] private float _dollySpeed = 0.08f;

        [Header("デフォルト位置（R でリセット）")]
        [SerializeField] private Vector3 _defaultPosition = new Vector3(0f, 1.3f, 1.3f);
        [SerializeField] private Vector3 _defaultEuler    = new Vector3(0f, 180f, 0f);
        [SerializeField] private float   _defaultFov      = 40f;

        [Header("GUI")]
        [SerializeField] private bool _showGui = true;

        // ── private state ──────────────────────────────────────────────
        private Camera  _cam;
        private float   _pitch;
        private float   _yaw;

        // 右クリック回転
        private bool    _rotating;
        private Vector3 _rotLastMousePos;

        // 中クリックパン
        private bool    _panning;
        private Vector3 _panLastMousePos;

        // Alt+左クリック オービット / Alt+右クリック ドリー 共通の注視点
        private Vector3 _orbitPivot;
        private float   _orbitDistance = 2f;

        private bool    _orbiting;
        private Vector3 _orbitLastMousePos;

        private bool    _dollying;
        private Vector3 _dollyLastMousePos;

        // GUIスタイル
        private GUIStyle _boxStyle;
        private GUIStyle _labelStyle;

        // ──────────────────────────────────────────────────────────────

        private void Start()
        {
            _cam = GetComponent<Camera>();
            var e = transform.eulerAngles;
            // eulerAngles.x は [0, 360] を返すため負の俯角（例: -10° → 350°）を正規化してスナップ防止
            _pitch = e.x > 180f ? e.x - 360f : e.x;
            _yaw   = e.y;
            _orbitDistance = 2f;
            _orbitPivot    = transform.position + transform.forward * _orbitDistance;
        }

        private void Update()
        {
            HandleKeyboardMove();
            HandleMouseRotate();
            HandleMiddleMousePan();
            HandleAltOrbit();
            HandleAltDolly();
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
            bool altHeld = Input.GetKey(KeyCode.LeftAlt) || Input.GetKey(KeyCode.RightAlt);
            // Alt 押下中は右クリックをドリーに譲る
            if (altHeld) { _rotating = false; return; }

            if (Input.GetMouseButtonDown(1))
            {
                _rotating = true;
                _rotLastMousePos = Input.mousePosition;
            }
            else if (Input.GetMouseButtonUp(1))
            {
                _rotating = false;
            }

            if (!_rotating) return;

            Vector3 delta = Input.mousePosition - _rotLastMousePos;
            _rotLastMousePos = Input.mousePosition;
            if (delta.sqrMagnitude < 0.0001f) return;   // 移動なしの場合はスナップ防止

            // マウス delta はすでに 1 フレーム分なので Time.deltaTime は不要
            float sensitivity = _rotSensitivity * 0.01f;
            _yaw   += delta.x * sensitivity;
            _pitch -= delta.y * sensitivity;
            _pitch  = Mathf.Clamp(_pitch, -89f, 89f);

            transform.rotation = Quaternion.Euler(_pitch, _yaw, 0f);
        }

        // ── パン（中クリック + ドラッグ）────────────────────────────

        private void HandleMiddleMousePan()
        {
            if (Input.GetMouseButtonDown(2))
            {
                _panning = true;
                _panLastMousePos = Input.mousePosition;
            }
            else if (Input.GetMouseButtonUp(2))
            {
                _panning = false;
            }

            if (!_panning) return;

            Vector3 delta = Input.mousePosition - _panLastMousePos;
            _panLastMousePos = Input.mousePosition;
            if (delta.sqrMagnitude < 0.0001f) return;

            // 1ピクセル = ワールド空間の何ユニットかを FOV と注視距離から算出（Scene ビューと同等）
            float fov = _cam != null ? _cam.fieldOfView : 60f;
            float dist = Mathf.Max(_orbitDistance, 0.5f);
            float worldPerPixel = 2f * Mathf.Tan(fov * 0.5f * Mathf.Deg2Rad) * dist / Screen.height;

            bool shiftHeld = Input.GetKey(KeyCode.LeftShift) || Input.GetKey(KeyCode.RightShift);
            if (shiftHeld)
            {
                // Shift + 中ドラッグ = 前後移動（Scene タブの Shift+中ドラッグと同等）
                float fwd = delta.y * worldPerPixel;
                transform.position += transform.forward * fwd;
                _orbitDistance = Mathf.Max(0.01f, _orbitDistance - fwd);
            }
            else
            {
                Vector3 panOffset = -transform.right * delta.x * worldPerPixel
                                    - transform.up    * delta.y * worldPerPixel;
                transform.position += panOffset;
                _orbitPivot        += panOffset;   // 次回オービットの中心も追従
            }
        }

        // ── オービット（Alt + 左クリック + ドラッグ）─────────────────

        private void HandleAltOrbit()
        {
            bool altHeld = Input.GetKey(KeyCode.LeftAlt) || Input.GetKey(KeyCode.RightAlt);

            if (altHeld && Input.GetMouseButtonDown(0))
            {
                _orbiting = true;
                _orbitLastMousePos = Input.mousePosition;
                // 注視点をカメラ前方 _orbitDistance の点に固定
                _orbitPivot = transform.position + transform.forward * _orbitDistance;
            }
            else if (Input.GetMouseButtonUp(0))
            {
                _orbiting = false;
            }

            if (!_orbiting) return;

            Vector3 delta = Input.mousePosition - _orbitLastMousePos;
            _orbitLastMousePos = Input.mousePosition;

            float sensitivity = _orbitSensitivity * Time.deltaTime * 0.01f;
            _yaw   += delta.x * sensitivity;
            _pitch -= delta.y * sensitivity;
            _pitch  = Mathf.Clamp(_pitch, -89f, 89f);

            Quaternion rot = Quaternion.Euler(_pitch, _yaw, 0f);
            transform.rotation = rot;
            transform.position = _orbitPivot - rot * Vector3.forward * _orbitDistance;
        }

        // ── ドリー（Alt + 右クリック + ドラッグ）────────────────────

        private void HandleAltDolly()
        {
            bool altHeld = Input.GetKey(KeyCode.LeftAlt) || Input.GetKey(KeyCode.RightAlt);

            if (altHeld && Input.GetMouseButtonDown(1))
            {
                _dollying = true;
                _dollyLastMousePos = Input.mousePosition;
            }
            else if (Input.GetMouseButtonUp(1))
            {
                _dollying = false;
            }

            if (!_dollying) return;

            Vector3 delta = Input.mousePosition - _dollyLastMousePos;
            _dollyLastMousePos = Input.mousePosition;

            // 右方向のドラッグ量をドリー量に変換
            float dolly = delta.x * _dollySpeed * Time.deltaTime * 60f;
            _orbitDistance = Mathf.Max(0.01f, _orbitDistance - dolly);
            transform.position = _orbitPivot - transform.forward * _orbitDistance;
        }

        // ── スクロールズーム ──────────────────────────────────────────

        private void HandleScrollZoom()
        {
            float scroll = Input.GetAxis("Mouse ScrollWheel");
            if (Mathf.Abs(scroll) < 0.001f) return;

            float move = scroll * _scrollSpeed;
            transform.position += transform.forward * move;
            // 注視距離も同期
            _orbitDistance = Mathf.Max(0.01f, _orbitDistance - move);
        }

        // ── リセット ─────────────────────────────────────────────────

        private void HandleReset()
        {
            if (Input.GetKeyDown(KeyCode.R))
            {
                transform.position   = _defaultPosition;
                transform.eulerAngles = _defaultEuler;
                _pitch         = _defaultEuler.x;
                _yaw           = _defaultEuler.y;
                _orbitDistance = 2f;
                _orbitPivot    = _defaultPosition + Quaternion.Euler(_defaultEuler) * Vector3.forward * _orbitDistance;
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
                $"右ドラッグ: 回転  中ドラッグ: パン\n" +
                $"Alt+左ドラッグ: オービット\n" +
                $"Alt+右ドラッグ: ドリー\n" +
                $"スクロール: ズーム  R: リセット";

            float w = 310f, h = 180f;
            float x = 10f, y = 10f;

            GUI.color = new Color(0, 0, 0, 0.6f);
            GUI.Box(new Rect(x, y, w, h), GUIContent.none, _boxStyle);
            GUI.color = Color.white;

            GUI.Label(new Rect(x + 8f, y + 6f, w - 12f, h - 10f), text, _labelStyle);
        }
    }
}
