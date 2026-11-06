using System;
using UnityEngine;
using UnityEngine.InputSystem;

namespace HomeWalk
{
    [Serializable] public class RoomZone { public string label; public int level; public Rect rect; public float floorY; public string kind; }
    [Serializable] public class Viewpoint { public string name; public Vector3 pos; public float yaw; public float pitch; }

    /// Walkthrough controls + HUD for a generated concept scene.
    ///  1-9 viewpoints · R roof · U dollhouse (hide upper floor + roof) · T time of day · F fly · M plan · H help
    public class Walkthrough : MonoBehaviour
    {
        public string conceptTitle = "Concept";
        public string note = "CONCEPT ONLY — NOT FOR CONSTRUCTION · subject to survey, legal merger, setbacks and permits · neighbours assumed (3 storeys)";
        public FirstPersonController player;
        public Light sun;
        public GameObject[] roofObjects;
        public GameObject[] upperObjects;
        public Light[] interiorLights;
        public RoomZone[] rooms;
        public Viewpoint[] viewpoints;
        public Rect siteRect = new Rect(0, 0, 13.5f, 65f);
        public Rect ontRect = new Rect(0, 0, 13.5f, 19.73f);
        public float upperFloorY = 3.75f;

        bool _roof = true, _upper = true, _help = true, _map = true;
        int _tod = 2;
        string _toast; float _toastT;
        static readonly string[] TodNames = { "Morning", "Midday", "Golden hour", "Evening" };

        void Start()
        {
            Debug.Log("[HomeWalk] scene started: " + conceptTitle);
            ApplyTod();
            if (viewpoints != null && viewpoints.Length > 0) Go(0);
        }

        void Update()
        {
            var kb = Keyboard.current;
            if (kb == null) return;
            for (int i = 0; i < 9 && viewpoints != null && i < viewpoints.Length; i++)
                if (kb[Key.Digit1 + i].wasPressedThisFrame || kb[Key.Numpad1 + i].wasPressedThisFrame) Go(i);
            if (viewpoints != null && viewpoints.Length > 9 && (kb.digit0Key.wasPressedThisFrame || kb.numpad0Key.wasPressedThisFrame)) Go(9);
            if (kb.rKey.wasPressedThisFrame) { _roof = !_roof; ApplyVis(); Toast(_roof ? "Roof on" : "Roof off"); }
            if (kb.uKey.wasPressedThisFrame) { _upper = !_upper; ApplyVis(); Toast(_upper ? "Upper floor on" : "Dollhouse: upper floor hidden"); }
            if (kb.tKey.wasPressedThisFrame) { _tod = (_tod + 1) % TodNames.Length; ApplyTod(); Toast(TodNames[_tod]); }
            if (kb.fKey.wasPressedThisFrame && player) { player.fly = !player.fly; Toast(player.fly ? "Fly mode (Space up, C down)" : "Walk mode"); }
            if (kb.mKey.wasPressedThisFrame || kb.tabKey.wasPressedThisFrame) _map = !_map;
            if (kb.hKey.wasPressedThisFrame) _help = !_help;
        }

        public void Go(int i)
        {
            var v = viewpoints[i];
            if (player) player.Teleport(v.pos, v.yaw, v.pitch);
            if (v.name == "Aerial" && player) player.fly = true;
            else if (player && player.fly && v.pos.y < upperFloorY + 3f) player.fly = false;
            Toast(v.name);
        }

        void ApplyVis()
        {
            foreach (var g in roofObjects) if (g) g.SetActive(_roof && _upper);
            foreach (var g in upperObjects) if (g) g.SetActive(_upper);
        }

        public void ApplyTod()
        {
            if (!sun) return;
            // sun azimuth measured from north (+Z), clockwise; the road is south
            float[] elev = { 22f, 70f, 19f, 4f };
            float[] az = { 100f, 180f, 240f, 262f };
            float[] inten = { 1.6f, 2.6f, 2.2f, 0.25f };
            Color[] col = { new Color(1f, .9f, .78f), Color.white, new Color(1f, .74f, .48f), new Color(.7f, .6f, .75f) };
            // direction TO the sun (x east, z north); the light travels the opposite way
            float e = elev[_tod] * Mathf.Deg2Rad, a = az[_tod] * Mathf.Deg2Rad;
            var toSun = new Vector3(Mathf.Sin(a) * Mathf.Cos(e), Mathf.Sin(e), Mathf.Cos(a) * Mathf.Cos(e));
            sun.transform.rotation = Quaternion.LookRotation(-toSun, Vector3.up);
            sun.intensity = inten[_tod];
            sun.color = col[_tod];
            RenderSettings.ambientIntensity = _tod == 3 ? 0.35f : 1f;
            if (interiorLights != null)
                foreach (var l in interiorLights) if (l) l.intensity = _tod == 1 ? 0.6f : (_tod == 3 ? 3.0f : 1.6f);
        }

        void Toast(string s) { _toast = s; _toastT = Time.unscaledTime + 2.2f; }

        string CurrentRoom(out int level)
        {
            level = -1;
            if (!player || rooms == null) return "";
            var p = player.transform.position;
            RoomZone best = null;
            foreach (var r in rooms)
            {
                if (!r.rect.Contains(new Vector2(p.x, p.z))) continue;
                if (p.y < r.floorY - 0.6f || p.y > r.floorY + 3.0f) continue;
                if (best == null || r.floorY > best.floorY) best = r;
            }
            if (best == null)
            {
                if (ontRect.Contains(new Vector2(p.x, p.z))) return "ONT — house plot (outside)";
                if (siteRect.Contains(new Vector2(p.x, p.z))) return "DNN — existing garden land (no building)";
                return p.z < 0 ? "Village road" : "Outside the site";
            }
            level = best.level;
            return best.label + (best.level == 0 ? " · Ground" : " · Upper");
        }

        GUIStyle _box, _small, _big;
        void OnGUI()
        {
            if (_box == null)
            {
                _box = new GUIStyle(GUI.skin.box) { alignment = TextAnchor.UpperLeft, fontSize = 15, wordWrap = true, richText = true };
                _box.normal.textColor = Color.white;
                _small = new GUIStyle(GUI.skin.label) { fontSize = 12, wordWrap = true };
                _small.normal.textColor = new Color(1, 1, 1, .85f);
                _big = new GUIStyle(GUI.skin.label) { fontSize = 26, alignment = TextAnchor.MiddleCenter, fontStyle = FontStyle.Bold };
                _big.normal.textColor = Color.white;
            }
            float s = Mathf.Clamp(Screen.height / 1000f, 0.55f, 2f);
            var m = GUI.matrix; GUI.matrix = Matrix4x4.Scale(new Vector3(s, s, 1));
            float W = Screen.width / s, H = Screen.height / s;
            var room = CurrentRoom(out int lvl);
            GUI.Box(new Rect(12, 12, 420, 54), $"<b>{conceptTitle}</b>\n{room}", _box);
            GUI.Label(new Rect(12, H - 26, W - 24, 22), note, _small);
            if (_help)
            {
                string vp = "";
                for (int i = 0; i < viewpoints.Length && i < 10; i++) vp += $"{(i + 1) % 10} {viewpoints[i].name}   ";
                GUI.Box(new Rect(12, 72, 420, 150),
                    "WASD walk · mouse look · Shift run · Space jump\n" +
                    "R roof · U dollhouse · T time of day · F fly · M plan\n" +
                    "Esc free mouse · CLICK the view to look around · H hide help\n" + vp, _box);
            }
            if (_map) DrawMap(W, H, lvl);
            if (_toast != null && Time.unscaledTime < _toastT)
                GUI.Label(new Rect(0, H * 0.12f, W, 40), _toast, _big);
            GUI.matrix = m;
        }

        static Texture2D _px;
        static void Fill(Rect r, Color c)
        {
            if (_px == null) { _px = new Texture2D(1, 1); _px.SetPixel(0, 0, Color.white); _px.Apply(); }
            var o = GUI.color; GUI.color = c; GUI.DrawTexture(r, _px); GUI.color = o;
        }

        void DrawMap(float W, float H, int lvl)
        {
            if (!player) return;
            float sc = 13f;                       // px per metre
            float mw = ontRect.width * sc + 20, mh = 24f * sc + 30;
            float ox = W - mw - 12, oy = 12;
            Fill(new Rect(ox, oy, mw, mh), new Color(0, 0, 0, .55f));
            int show = lvl >= 0 ? lvl : (player.transform.position.y > upperFloorY - 0.5f ? 1 : 0);
            Func<float, float, Vector2> P = (x, z) => new Vector2(ox + 10 + x * sc, oy + 20 + (24f - z) * sc);
            // ONT band
            var a = P(ontRect.xMin, ontRect.yMax); var b = P(ontRect.xMax, ontRect.yMin);
            Fill(new Rect(a.x, a.y, b.x - a.x, b.y - a.y), new Color(.95f, .92f, .85f, .25f));
            var d = P(0, ontRect.yMax);
            Fill(new Rect(d.x, d.y - 1, ontRect.width * sc, 2), new Color(.9f, .2f, .2f, .9f));
            GUI.Label(new Rect(ox + 8, oy + 2, mw, 18), show == 0 ? "PLAN · GROUND" : "PLAN · UPPER", _small);
            foreach (var r in rooms)
            {
                if (r.level != show) continue;
                var p0 = P(r.rect.xMin, r.rect.yMax); var p1 = P(r.rect.xMax, r.rect.yMin);
                var c = r.kind == "out" ? new Color(.55f, .7f, .5f, .7f) : r.kind == "plant" ? new Color(.4f, .6f, .35f, .7f)
                      : r.kind == "serv" ? new Color(.75f, .8f, .82f, .75f) : new Color(.96f, .93f, .86f, .8f);
                Fill(new Rect(p0.x + 1, p0.y + 1, p1.x - p0.x - 2, p1.y - p0.y - 2), c);
            }
            var pp = player.transform.position;
            var pv = P(pp.x, pp.z);
            Fill(new Rect(pv.x - 4, pv.y - 4, 8, 8), new Color(.9f, .15f, .1f, 1));
            var f = player.transform.forward;
            Fill(new Rect(pv.x + f.x * 9 - 2, pv.y - f.z * 9 - 2, 4, 4), new Color(1, 1, 1, 1));
        }
    }
}
