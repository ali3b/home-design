using System;
using UnityEngine;
using UnityEngine.InputSystem;

namespace HomeWalk
{
    [Serializable] public class RoomZone { public string label; public int level; public Rect rect; public float floorY; public string kind; }
    [Serializable] public class Viewpoint { public string name; public Vector3 pos; public float yaw; public float pitch; }

    /// Walkthrough controls + HUD for a generated concept scene.
    ///  1-9 viewpoints · R roof · U dollhouse (hide upper floor + roof) · T time of day · L sun timelapse · F fly · M plan · H help
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
            if (kb.tKey.wasPressedThisFrame) { _lapse = 0; _tod = (_tod + 1) % TodNames.Length; ApplyTod(); Toast(TodNames[_tod]); }
            if (kb.lKey.wasPressedThisFrame) StartLapse((_lapse + 1) % 3);
            if (_lapse != 0 && kb.leftBracketKey.wasPressedThisFrame) { _lapseHold = Mathf.Min(6f, _lapseHold + 0.5f); Toast($"{_lapseHold:0.#} s per 30 min"); }
            if (_lapse != 0 && kb.rightBracketKey.wasPressedThisFrame) { _lapseHold = Mathf.Max(0.3f, _lapseHold - 0.5f); Toast($"{_lapseHold:0.#} s per 30 min"); }
            UpdateLapse();
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

        // ------------------------------------------------------------ sun & sky --
        // Latitude rounded to a whole degree (no site coordinates are published). Times are local solar time.
        public float latitude = 21f;
        public Material sky;

        /// Fixed presets for the T key: (elevation, azimuth from north, clockwise). The road is south.
        static readonly float[] PresetElev = { 22f, 70f, 19f, 4f };
        static readonly float[] PresetAz = { 100f, 180f, 240f, 262f };

        public void ApplyTod() => ApplySun(PresetElev[_tod], PresetAz[_tod]);

        /// Sun position for a solar declination (deg) and solar time (minutes after midnight).
        public void SolarPosition(float declDeg, float minutes, out float elevDeg, out float azDeg)
        {
            float phi = latitude * Mathf.Deg2Rad, d = declDeg * Mathf.Deg2Rad;
            float H = (minutes / 60f - 12f) * 15f * Mathf.Deg2Rad;
            float sinE = Mathf.Sin(phi) * Mathf.Sin(d) + Mathf.Cos(phi) * Mathf.Cos(d) * Mathf.Cos(H);
            elevDeg = Mathf.Asin(Mathf.Clamp(sinE, -1f, 1f)) * Mathf.Rad2Deg;
            // azimuth from south (westward +), then turned to "from north, clockwise"
            float A = Mathf.Atan2(Mathf.Sin(H), Mathf.Cos(H) * Mathf.Sin(phi) - Mathf.Tan(d) * Mathf.Cos(phi)) * Mathf.Rad2Deg;
            azDeg = (A + 180f + 360f) % 360f;
        }

        /// Sunrise/sunset in solar minutes for a declination.
        public void DayLength(float declDeg, out float riseMin, out float setMin)
        {
            float c = -Mathf.Tan(latitude * Mathf.Deg2Rad) * Mathf.Tan(declDeg * Mathf.Deg2Rad);
            float H0 = Mathf.Acos(Mathf.Clamp(c, -1f, 1f)) * Mathf.Rad2Deg / 15f;   // hours
            riseMin = (12f - H0) * 60f; setMin = (12f + H0) * 60f;
        }

        public void SetSolar(float declDeg, float minutes)
        {
            SolarPosition(declDeg, minutes, out var e, out var a);
            ApplySun(e, a);
        }

        static float Smooth(float a, float b, float x) { float t = Mathf.Clamp01((x - a) / (b - a)); return t * t * (3 - 2 * t); }

        /// One lighting model for presets, the timelapse and the review shots: sun colour/intensity, sky,
        /// sky/horizon/ground ambient, fog and interior lights all follow the sun's elevation.
        public void ApplySun(float elevDeg, float azDeg)
        {
            if (!sun) return;
            float day = Smooth(-5f, 8f, elevDeg);            // 0 night .. 1 day
            float low = 1f - Smooth(4f, 35f, elevDeg);        // warm, low sun
            bool moon = elevDeg < -1.5f;
            float e = (moon ? 38f : Mathf.Max(elevDeg, 0.5f)) * Mathf.Deg2Rad;
            float a = (moon ? 120f : azDeg) * Mathf.Deg2Rad;
            var toSun = new Vector3(Mathf.Sin(a) * Mathf.Cos(e), Mathf.Sin(e), Mathf.Cos(a) * Mathf.Cos(e));
            sun.transform.rotation = Quaternion.LookRotation(-toSun, Vector3.up);
            if (moon) { sun.intensity = 0.12f; sun.color = new Color(.62f, .7f, .95f); }
            else
            {
                sun.intensity = Mathf.Lerp(0.15f, 2.7f, Smooth(-1f, 45f, elevDeg));
                sun.color = Color.Lerp(new Color(1f, .97f, .93f), new Color(1f, .58f, .32f), low * low);
            }
            var nightSky = new Color(.035f, .045f, .08f);
            var daySky = Color.Lerp(new Color(.36f, .45f, .60f), new Color(.5f, .43f, .40f), low * .6f);
            var dayEq = Color.Lerp(new Color(.36f, .36f, .34f), new Color(.52f, .40f, .31f), low * .6f);
            RenderSettings.ambientMode = UnityEngine.Rendering.AmbientMode.Trilight;
            RenderSettings.ambientSkyColor = Color.Lerp(nightSky, daySky, day);
            RenderSettings.ambientEquatorColor = Color.Lerp(nightSky * .8f, dayEq, day);
            RenderSettings.ambientGroundColor = Color.Lerp(nightSky * .4f, new Color(.2f, .19f, .17f), day);
            RenderSettings.fogColor = Color.Lerp(new Color(.05f, .06f, .09f), Color.Lerp(new Color(.74f, .79f, .85f), new Color(.92f, .74f, .58f), low), day);
            var sk = sky ? sky : RenderSettings.skybox;
            if (sk && sk.HasProperty("_Exposure"))
            {
                sk.SetFloat("_Exposure", Mathf.Lerp(0.06f, 1.25f, day));
                sk.SetColor("_SkyTint", Color.Lerp(new Color(.5f, .5f, .5f), new Color(.62f, .5f, .45f), low));
                sk.SetFloat("_AtmosphereThickness", Mathf.Lerp(0.85f, 1.35f, low));
            }
            if (interiorLights != null)
            {
                float li = Mathf.Lerp(2.4f, 0.45f, Smooth(-2f, 25f, elevDeg));
                foreach (var l in interiorLights) if (l) l.intensity = li * (l.name == "GateLamp" ? 1.4f : 1f);
            }
        }

        // ------------------------------------------------------------- timelapse --
        // L cycles: winter solstice -> summer solstice -> off. Sunrise to sunset in 30-minute steps; [ ] change speed.
        int _lapse;                     // 0 off, 1 winter, 2 summer
        float _lapseFrom, _lapseTo, _lapseClock, _lapseHold = 2.0f;
        const float LapseStep = 30f, LapseEase = 0.7f;
        float LapseDecl => _lapse == 1 ? -23.44f : 23.44f;
        static string Clock(float m) { int t = Mathf.RoundToInt(m); return $"{t / 60:00}:{t % 60:00}"; }

        float LapseFirst() { DayLength(LapseDecl, out var r, out _); return Mathf.Floor(r / LapseStep) * LapseStep; }

        void StartLapse(int mode)
        {
            _lapse = mode;
            if (_lapse == 0) { ApplyTod(); Toast("Timelapse off"); return; }
            _lapseFrom = _lapseTo = LapseFirst(); _lapseClock = 0;
            SetSolar(LapseDecl, _lapseTo);
            Toast(_lapse == 1 ? "Timelapse: winter solstice (21 Dec)" : "Timelapse: summer solstice (21 Jun)");
        }

        void UpdateLapse()
        {
            if (_lapse == 0) return;
            _lapseClock += Time.deltaTime;
            float cur = _lapseFrom + (_lapseTo - _lapseFrom) * Smooth(0f, 1f, _lapseClock / LapseEase);
            SetSolar(LapseDecl, cur);
            if (_lapseClock >= _lapseHold + LapseEase)
            {
                DayLength(LapseDecl, out _, out var set);
                _lapseFrom = _lapseTo; _lapseClock = 0;
                _lapseTo += LapseStep;
                if (_lapseTo > set + LapseStep) { _lapseFrom = _lapseTo = LapseFirst(); }   // loop back to dawn
            }
        }

        string LapseLabel()
        {
            SolarPosition(LapseDecl, _lapseTo, out var e, out var a);
            string side = a > 270 || a < 90 ? "northern sky" : "southern sky";
            return $"{(_lapse == 1 ? "Winter solstice · 21 Dec" : "Summer solstice · 21 Jun")}   {Clock(_lapseTo)} solar time   " +
                   $"sun bearing {a:0}° ({side}), {Mathf.Max(e, 0):0}° high   ·   {_lapseHold:0.#} s per 30 min   L next · [ ] speed";
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
                    "R roof · U dollhouse · T time of day · L sun timelapse · F fly · M plan\n" +
                    "Esc free mouse · CLICK the view to look around · H hide help\n" + vp, _box);
            }
            if (_map) DrawMap(W, H, lvl);
            if (_lapse != 0) GUI.Box(new Rect(W / 2 - 430, H - 70, 860, 34), LapseLabel(), _box);
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
