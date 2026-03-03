// AlchemistRoom.cs
// [DEPRECATED] プロシージャル生成による錬金術師の部屋。
//
// !! Prefab ベースの方式（Assets/Rooms/）に移行済みのため、
//    このコンポーネントは Start() で自動的に無効化されます。
//    SRS ref: FR-ROOM-01（廃止: 旧プロシージャル方式）
//
// 削除手順:
//   1. SampleScene の AlchemistRoom GameObject からこのコンポーネントを外す
//   2. このファイルを削除する
//   3. SampleScene の AlchemistRoom GameObject 自体を削除する

using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

namespace AITuber
{
    /// <summary>
    /// [DEPRECATED] Use Prefab-based room system (RoomManager + RoomDefinition) instead.
    /// </summary>
    [System.Obsolete("Use RoomManager + RoomDefinition Prefab approach. See Assets/Rooms/README.md")]
    public class AlchemistRoom : MonoBehaviour
    {
        // ── パラメータ ────────────────────────────────────────────
        [Header("Room Size")]
        [SerializeField] private float _width  = 6f;   // X
        [SerializeField] private float _height = 3.5f; // Y
        [SerializeField] private float _depth  = 5f;   // Z

        [Header("Colors")]
        [SerializeField] private Color _stoneColor    = new Color(0.25f, 0.22f, 0.20f);
        [SerializeField] private Color _floorColor    = new Color(0.20f, 0.18f, 0.15f);
        [SerializeField] private Color _woodColor     = new Color(0.38f, 0.25f, 0.13f);
        [SerializeField] private Color _tableclothColor = new Color(0.18f, 0.22f, 0.28f);

        [Header("Lighting")]
        [SerializeField] private Color _candleColor   = new Color(1.0f, 0.65f, 0.25f);
        [SerializeField] private float _candleIntensity = 3.0f;
        [SerializeField] private Color _ambientColor  = new Color(0.08f, 0.06f, 0.05f);

        // ── 内部 ─────────────────────────────────────────────────
        private readonly List<GameObject> _created = new();
        private static readonly int _colorProp = Shader.PropertyToID("_BaseColor");

        // ─────────────────────────────────────────────────────────

        private void Start()
        {
            Debug.LogWarning("[AlchemistRoom] DEPRECATED: Use RoomManager + Prefab approach. See Assets/Rooms/README.md. Disabling self.");
            enabled = false;
            return;

            // --- Legacy procedural generation below (disabled) ---
#pragma warning disable CS0162
            RenderSettings.ambientMode  = AmbientMode.Flat;
            RenderSettings.ambientLight = _ambientColor;

            BuildRoom();
            BuildFurniture();
            BuildProps();
            BuildLights();
            BuildBookshelf();
#pragma warning restore CS0162
        }

        // ── 部屋の壁・床・天井 ───────────────────────────────────

        private void BuildRoom()
        {
            float hw = _width  / 2f;
            float hd = _depth  / 2f;

            // 床
            MakePlane("Floor",    new Vector3(0, 0, 0),
                      Vector3.zero, new Vector3(_width, 1, _depth), _floorColor);

            // 天井
            MakePlane("Ceiling",  new Vector3(0, _height, 0),
                      new Vector3(180, 0, 0), new Vector3(_width, 1, _depth), _stoneColor * 0.6f);

            // 奥壁（カメラ向こう側 / +Z 方向）
            MakePlane("WallBack", new Vector3(0, _height / 2f, hd),
                      new Vector3(90, 0, 0), new Vector3(_width, 1, _height), _stoneColor);

            // 前壁（省略 or 見えないので軽量に）

            // 左壁
            MakePlane("WallLeft", new Vector3(-hw, _height / 2f, 0),
                      new Vector3(90, 90, 0), new Vector3(_depth, 1, _height), _stoneColor * 0.85f);

            // 右壁
            MakePlane("WallRight", new Vector3(hw, _height / 2f, 0),
                      new Vector3(90, -90, 0), new Vector3(_depth, 1, _height), _stoneColor * 0.85f);
        }

        // ── 家具 ─────────────────────────────────────────────────

        private void BuildFurniture()
        {
            // 作業台（中央やや奥）
            MakeBox("Table",
                    new Vector3(0, 0.4f, 1.2f),
                    new Vector3(1.8f, 0.08f, 0.7f), _woodColor);

            // 台の脚 x 4
            float[] xs = { -0.82f,  0.82f, -0.82f,  0.82f };
            float[] zs = {  0.88f,  0.88f,  1.52f,  1.52f };
            for (int i = 0; i < 4; i++)
                MakeBox($"TableLeg{i}", new Vector3(xs[i], 0.2f, zs[i]),
                        new Vector3(0.07f, 0.43f, 0.07f), _woodColor * 0.8f);

            // テーブルクロス（薄い板で代用）
            MakeBox("Tablecloth",
                    new Vector3(0, 0.445f, 1.2f),
                    new Vector3(1.75f, 0.005f, 0.65f), _tableclothColor);

            // 椅子（奥側、カメラには映らない用）
            MakeBox("ChairSeat",  new Vector3(0, 0.25f, 2.0f), new Vector3(0.45f, 0.05f, 0.4f), _woodColor * 0.9f);
            MakeBox("ChairBack",  new Vector3(0, 0.6f,  2.22f), new Vector3(0.45f, 0.45f, 0.05f), _woodColor * 0.9f);
        }

        // ── 小道具（薬瓶・本・ろうそく）────────────────────────

        private void BuildProps()
        {
            // 薬瓶 on 作業台
            var bottleColors = new[]
            {
                new Color(0.3f, 0.7f, 0.4f, 0.7f),   // 緑
                new Color(0.7f, 0.3f, 0.3f, 0.7f),   // 赤
                new Color(0.3f, 0.4f, 0.8f, 0.7f),   // 青
                new Color(0.7f, 0.6f, 0.2f, 0.7f),   // 黄
                new Color(0.5f, 0.2f, 0.6f, 0.7f),   // 紫
            };
            float[] bx = { -0.55f, -0.3f, 0.0f, 0.3f, 0.55f };
            for (int i = 0; i < bottleColors.Length; i++)
            {
                // 胴体
                var body = MakeCapsule($"Bottle{i}Body",
                    new Vector3(bx[i], 0.51f, 1.0f),
                    new Vector3(0.07f, 0.09f, 0.07f), bottleColors[i]);
                // 栓
                MakeBox($"Bottle{i}Cork",
                    new Vector3(bx[i], 0.60f, 1.0f),
                    new Vector3(0.04f, 0.03f, 0.04f), _woodColor);
            }

            // 本 on 作業台（右端）
            MakeBox("Book1", new Vector3(0.72f, 0.45f, 1.1f),
                    new Vector3(0.12f, 0.18f, 0.15f), new Color(0.5f, 0.15f, 0.1f));
            MakeBox("Book2", new Vector3(0.86f, 0.45f, 1.09f),
                    new Vector3(0.10f, 0.20f, 0.16f), new Color(0.2f, 0.35f, 0.2f));

            // ろうそく（3 本、台の上）
            float[] cx = { -0.72f, -0.62f, -0.78f };
            float[] ch = {  0.09f,  0.12f,  0.07f  };
            for (int i = 0; i < 3; i++)
            {
                MakeCylinder($"Candle{i}",
                    new Vector3(cx[i], 0.445f + ch[i] / 2f, 1.35f),
                    new Vector3(0.025f, ch[i], 0.025f),
                    new Color(0.96f, 0.94f, 0.82f));
                // 炎（小さな黄色球）
                MakeSphere($"Flame{i}",
                    new Vector3(cx[i], 0.445f + ch[i] + 0.015f, 1.35f),
                    Vector3.one * 0.02f,
                    new Color(1f, 0.8f, 0.1f) * 2f);
            }

            // 大鍋（左端）
            MakeSphere("Cauldron",
                new Vector3(-0.6f, 0.47f, 1.2f),
                new Vector3(0.22f, 0.18f, 0.22f),
                new Color(0.15f, 0.15f, 0.18f));

            // 床に落ちた本
            MakeBox("FloorBook", new Vector3(-1.5f, 0.015f, 0.5f),
                    new Vector3(0.18f, 0.03f, 0.24f), new Color(0.35f, 0.2f, 0.1f));
        }

        // ── 本棚（左壁沿い）────────────────────────────────────

        private void BuildBookshelf()
        {
            float x = -_width / 2f + 0.12f;
            // 棚板 x 3
            float[] sy = { 0.6f, 1.1f, 1.6f };
            foreach (var y in sy)
                MakeBox($"Shelf{y}", new Vector3(x, y, 0.8f),
                        new Vector3(0.22f, 0.04f, 0.9f), _woodColor * 0.75f);

            // 棚の本（ランダム色）
            var shelfBookColors = new[]
            {
                new Color(0.55f, 0.15f, 0.1f),
                new Color(0.2f, 0.3f, 0.55f),
                new Color(0.25f, 0.45f, 0.2f),
                new Color(0.5f, 0.4f, 0.1f),
                new Color(0.45f, 0.15f, 0.35f),
                new Color(0.3f, 0.3f, 0.3f),
            };
            float[] bz = { 0.38f, 0.52f, 0.66f, 0.80f, 0.94f, 1.08f };
            float[] bh = { 0.14f, 0.17f, 0.12f, 0.16f, 0.13f, 0.15f };
            for (int si = 0; si < sy.Length; si++)
            {
                for (int bi = 0; bi < shelfBookColors.Length; bi++)
                {
                    MakeBox($"ShelfBook_{si}_{bi}",
                        new Vector3(x, sy[si] + bh[bi] / 2f + 0.02f, bz[bi]),
                        new Vector3(0.06f, bh[bi], 0.1f),
                        shelfBookColors[bi]);
                }
            }
        }

        // ── ライト ───────────────────────────────────────────────

        private void BuildLights()
        {
            // ろうそく炎のポイントライト（3 本分をまとめて 1 つ）
            AddPointLight("CandleLight",
                new Vector3(-0.7f, 0.7f, 1.3f),
                _candleColor, _candleIntensity, 3.5f);

            // 棚側の補助光（薄橙）
            AddPointLight("ShelfLight",
                new Vector3(-_width / 2f + 0.5f, 1.5f, 0.8f),
                new Color(0.9f, 0.6f, 0.3f), 1.2f, 3f);

            // 全体の薄い fill light（青白）
            var fill = new GameObject("FillLight");
            _created.Add(fill);
            fill.transform.SetParent(transform);
            fill.transform.position = new Vector3(0f, 3f, -1f);
            var dl = fill.AddComponent<Light>();
            dl.type      = LightType.Directional;
            dl.color     = new Color(0.4f, 0.45f, 0.55f);
            dl.intensity = 0.4f;
            fill.transform.eulerAngles = new Vector3(45f, 170f, 0f);
        }

        // ── ヘルパー ─────────────────────────────────────────────

        private GameObject MakePlane(string name, Vector3 pos, Vector3 euler, Vector3 scale, Color color)
        {
            var go = GameObject.CreatePrimitive(PrimitiveType.Plane);
            go.name = name;
            go.transform.SetParent(transform);
            go.transform.position    = pos;
            go.transform.eulerAngles = euler;
            go.transform.localScale  = scale / 10f; // Plane is 10 units
            ApplyColor(go, color);
            _created.Add(go);
            return go;
        }

        private GameObject MakeBox(string name, Vector3 pos, Vector3 size, Color color)
        {
            var go = GameObject.CreatePrimitive(PrimitiveType.Cube);
            go.name = name;
            go.transform.SetParent(transform);
            go.transform.position   = pos;
            go.transform.localScale = size;
            ApplyColor(go, color);
            _created.Add(go);
            return go;
        }

        private GameObject MakeSphere(string name, Vector3 pos, Vector3 scale, Color color)
        {
            var go = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            go.name = name;
            go.transform.SetParent(transform);
            go.transform.position   = pos;
            go.transform.localScale = scale;
            ApplyColor(go, color);
            _created.Add(go);
            return go;
        }

        private GameObject MakeCapsule(string name, Vector3 pos, Vector3 scale, Color color)
        {
            var go = GameObject.CreatePrimitive(PrimitiveType.Capsule);
            go.name = name;
            go.transform.SetParent(transform);
            go.transform.position   = pos;
            go.transform.localScale = scale;
            ApplyColor(go, color);
            _created.Add(go);
            return go;
        }

        private GameObject MakeCylinder(string name, Vector3 pos, Vector3 scale, Color color)
        {
            var go = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            go.name = name;
            go.transform.SetParent(transform);
            go.transform.position   = pos;
            go.transform.localScale = scale;
            ApplyColor(go, color);
            _created.Add(go);
            return go;
        }

        private void AddPointLight(string name, Vector3 pos, Color color, float intensity, float range)
        {
            var go = new GameObject(name);
            _created.Add(go);
            go.transform.SetParent(transform);
            go.transform.position = pos;
            var lt = go.AddComponent<Light>();
            lt.type      = LightType.Point;
            lt.color     = color;
            lt.intensity = intensity;
            lt.range     = range;
        }

        private static void ApplyColor(GameObject go, Color color)
        {
            var mr = go.GetComponent<MeshRenderer>();
            if (mr == null) return;

            // デフォルトのシェアードマテリアル（URP Lit）をベースにクローン。
            // Shader.Find は Build 時に「未参照シェーダー」だとピンクになるため
            // プリミティブ自身が持つ sharedMaterial を複製することで回避する。
            var baseMat = mr.sharedMaterial;
            var mat = baseMat != null ? new Material(baseMat) : new Material(Shader.Find("Hidden/InternalErrorShader"));

            // _BaseColor (URP Lit) / _Color (Standard) 両方に設定を試みる
            var opaqueColor = new Color(color.r, color.g, color.b, 1f);
            if (mat.HasProperty(_colorProp))
                mat.SetColor(_colorProp, color.a < 1f ? color : opaqueColor);
            if (mat.HasProperty("_Color"))
                mat.SetColor("_Color", opaqueColor);

            // 発光（炎など HDR）
            if (color.r > 1f || color.g > 1f || color.b > 1f)
            {
                if (mat.HasProperty("_EmissionColor"))
                {
                    mat.EnableKeyword("_EMISSION");
                    mat.SetColor("_EmissionColor", new Color(color.r, color.g, color.b) * 0.8f);
                }
            }

            // 半透明（薬瓶）
            if (color.a < 1f)
            {
                // URP Surface / Blend
                if (mat.HasProperty("_Surface")) mat.SetFloat("_Surface", 1);
                if (mat.HasProperty("_Blend"))   mat.SetFloat("_Blend",   0);
                mat.renderQueue = 3000;
                mat.SetOverrideTag("RenderType", "Transparent");
                mat.EnableKeyword("_SURFACE_TYPE_TRANSPARENT");
                // Built-in
                mat.SetInt("_SrcBlend",  (int)UnityEngine.Rendering.BlendMode.SrcAlpha);
                mat.SetInt("_DstBlend",  (int)UnityEngine.Rendering.BlendMode.OneMinusSrcAlpha);
                mat.SetInt("_ZWrite", 0);
            }

            mr.material = mat;
        }
    }
}
