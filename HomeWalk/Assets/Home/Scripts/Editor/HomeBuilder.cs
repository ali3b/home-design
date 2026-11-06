using System.Collections.Generic;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

namespace HomeWalk.EditorTools
{
    /// Builds a walkable scene for one concept from the JSON data + Blender FBX + Synty props.
    /// Site coordinates (x east, y north, z up) map to Unity (x, z, y).
    public static class HomeBuilder
    {
        public static string Root => Path.GetFullPath(Path.Combine(Application.dataPath, "..", ".."));
        public const string ScenePath = "Assets/Home/Scenes/C1_Walkthrough.unity";

        [MenuItem("Home/Build Concept 1 %#b")]
        public static void BuildC1() => Build("c1_courtyard_house", "c1_furnishing", "Assets/Home/Models/c1_architecture.fbx", ScenePath);

        public static void BatchBuild() { HomeSetup.Configure(); BuildC1(); }

        static Vector3 U(double x, double y, double z) => new Vector3((float)x, (float)z, (float)y);

        // ------------------------------------------------------------------ build --
        public static void Build(string concept, string furnishing, string fbxPath, string scenePath)
        {
            var C = JObject.Parse(File.ReadAllText(Path.Combine(Root, "concepts", concept + ".json")));
            var S = JObject.Parse(File.ReadAllText(Path.Combine(Root, "concepts", "site.json")));
            var F = JObject.Parse(File.ReadAllText(Path.Combine(Root, "concepts", furnishing + ".json")));

            ConfigureFbx(fbxPath);
            var mats = MakeMaterials();
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);

            // architecture
            var fbx = AssetDatabase.LoadAssetAtPath<GameObject>(fbxPath);
            var arch = (GameObject)PrefabUtility.InstantiatePrefab(fbx);
            arch.name = "Architecture";
            var fp = C["footprint"].Select(t => (float)t).ToArray();
            FixAxes(arch, new Bounds(new Vector3((fp[0] + fp[2]) / 2, 0.215f, (fp[1] + fp[3]) / 2),
                                     new Vector3(fp[2] - fp[0], 0.43f, fp[3] - fp[1])));
            var roof = new List<GameObject>(); var upper = new List<GameObject>();
            foreach (var r in arch.GetComponentsInChildren<MeshRenderer>(true))
            {
                var nm = r.gameObject.name;
                var parts = nm.Split(new[] { "__" }, System.StringSplitOptions.None);
                var coll = parts[0];
                var mname = parts.Length > 1 ? parts[1].Split('.')[0] : "plaster";
                if (mats.TryGetValue(mname, out var m)) r.sharedMaterial = m;
                else Debug.LogWarning("[Home] no material for " + nm);
                r.shadowCastingMode = mname == "glass" ? ShadowCastingMode.Off : ShadowCastingMode.On;
                if (!r.GetComponent<MeshCollider>()) r.gameObject.AddComponent<MeshCollider>();
                GameObjectUtility.SetStaticEditorFlags(r.gameObject, StaticEditorFlags.BatchingStatic | StaticEditorFlags.NavigationStatic | StaticEditorFlags.OccluderStatic | StaticEditorFlags.OccludeeStatic);
                if (coll == "ROOF") roof.Add(r.gameObject);
                if (coll == "L1") upper.Add(r.gameObject);
            }

            var levels = (JArray)C["levels"];
            float zUpper = levels.Count > 1 ? (float)levels[1]["z"] : 99f;

            // furniture
            var furnRoot = new GameObject("Furniture");
            var furnUpper = new GameObject("Furniture_Upper");
            var placed = new List<(string name, GameObject go)>();
            int missing = 0;
            foreach (JArray it in F["items"])
            {
                string pf = (string)it[0];
                float x = (float)it[1], y = (float)it[2];
                string face = (string)it[3];
                int lvl = (int)it[4];
                string mode = it.Count > 5 ? (string)it[5] : "";
                var prefab = FindPrefab(pf);
                if (prefab == null) { missing++; Debug.LogWarning("[Home] missing prefab " + pf); continue; }
                var lv = levels[lvl];
                float floorY = (float)lv["z"];
                float ceilY = lvl == levels.Count - 1 ? (float)lv["ztop"] - 0.12f : (float)levels[lvl + 1]["z"] - 0.22f;
                var go = (GameObject)PrefabUtility.InstantiatePrefab(prefab, (lvl == 0 ? furnRoot : furnUpper).transform);
                go.transform.rotation = Quaternion.Euler(0, Yaw(face), 0);
                var b = WorldBounds(go);
                var target = new Vector3(x, floorY, y);
                float baseY = floorY;
                if (mode == "ceiling") baseY = ceilY - b.size.y;
                else if (mode.StartsWith("on:"))
                {
                    var host = placed.LastOrDefault(p => p.name == mode.Substring(3) && Vector2.Distance(new Vector2(p.go.transform.position.x, p.go.transform.position.z), new Vector2(x, y)) < 1f);
                    if (host.go) baseY = WorldBounds(host.go).max.y;
                }
                go.transform.position += new Vector3(target.x - b.center.x, baseY - b.min.y, target.z - b.center.z);
                placed.Add((pf, go));
                var fb = WorldBounds(go);
                bool inside = false;
                foreach (JArray rr in lv["rooms"])
                {
                    var rect = Rect.MinMaxRect((float)rr[1] - 0.15f, (float)rr[2] - 0.15f, (float)rr[3] + 0.15f, (float)rr[4] + 0.15f);
                    if (rect.Contains(new Vector2(fb.min.x, fb.min.z)) && rect.Contains(new Vector2(fb.max.x, fb.max.z))) { inside = true; break; }
                }
                if (!inside) Debug.LogWarning($"[Home] ITEM-OUTSIDE-ROOM {pf} at ({x},{y}) L{lvl} bounds {fb.min:F2}-{fb.max:F2} size {fb.size:F2}");
                if (mode != "ceiling" && b.size.y > 0.35f && !pf.Contains("Rug") && !pf.Contains("Lamp") && !go.GetComponentInChildren<Collider>())
                {
                    var bc = go.AddComponent<BoxCollider>();
                    var wb = WorldBounds(go);
                    bc.center = go.transform.InverseTransformPoint(wb.center);
                    var ls = Quaternion.Inverse(go.transform.rotation) * wb.size;
                    bc.size = new Vector3(Mathf.Abs(ls.x), Mathf.Abs(ls.y), Mathf.Abs(ls.z)) * 0.95f;
                }
            }
            upper.Add(furnUpper);

            // planting
            var plantRoot = new GameObject("Planting");
            var rnd = new System.Random(5);
            var plantTypes = (JObject)F["planting"];
            void Plant(JArray list)
            {
                if (list == null) return;
                foreach (JArray p in list)
                {
                    float x = (float)p[0], y = (float)p[1]; string kind = (string)p[2];
                    var opts = plantTypes[kind] as JArray;
                    if (opts == null) continue;
                    var prefab = FindPrefab((string)opts[rnd.Next(opts.Count)]);
                    if (prefab == null) continue;
                    var go = (GameObject)PrefabUtility.InstantiatePrefab(prefab, plantRoot.transform);
                    go.transform.position = new Vector3(x, kind == "court" ? 0.25f : 0f, y);
                    go.transform.rotation = Quaternion.Euler(0, rnd.Next(360), 0);
                    float want = kind == "tree" ? 6.5f + (float)rnd.NextDouble() * 3f : kind == "palm" ? 2.2f : kind == "court" ? 1.1f : 1.2f;
                    var pb = WorldBounds(go);
                    if (pb.size.y > 0.05f) go.transform.localScale = Vector3.one * Mathf.Clamp(want / pb.size.y, 0.15f, 4f);
                    if (kind == "tree")
                    {
                        var cap = go.AddComponent<CapsuleCollider>(); cap.radius = 0.25f; cap.height = 3f; cap.center = new Vector3(0, 1.5f, 0);
                    }
                }
            }
            Plant(C["planting_dnn"] as JArray);
            Plant(C["planting_ont"] as JArray);
            // context trees beyond the site so the horizon isn't bare
            var ctx = new JArray();
            for (int i = 0; i < 26; i++)
            {
                float side = i % 2 == 0 ? -1 : 1;
                ctx.Add(new JArray(side < 0 ? -4 - rnd.Next(30) : 17.5f + rnd.Next(30), rnd.Next(-2, 64), "tree"));
            }
            Plant(ctx);

            // lighting
            var sunGo = new GameObject("Sun");
            var sun = sunGo.AddComponent<Light>();
            sun.type = LightType.Directional; sun.shadows = LightShadows.Soft; sun.shadowStrength = 0.85f;
            var sky = AssetDatabase.LoadAssetAtPath<Material>("Assets/Home/Settings/CW_Sky.mat");
            if (sky) RenderSettings.skybox = sky;
            RenderSettings.sun = sun;
            RenderSettings.ambientMode = AmbientMode.Skybox;
            RenderSettings.fog = true; RenderSettings.fogMode = FogMode.Exponential; RenderSettings.fogDensity = 0.0035f;
            RenderSettings.fogColor = new Color(0.78f, 0.80f, 0.82f);
            var lightsRoot = new GameObject("InteriorLights");
            var lights = new List<Light>();
            var rooms = new List<RoomZone>();
            var labels = (JObject)C["labels"];
            for (int li = 0; li < levels.Count; li++)
            {
                var lv = levels[li];
                float z0 = (float)lv["z"], zt = (float)lv["ztop"];
                foreach (JArray r in lv["rooms"])
                {
                    string nm = (string)r[0]; string kind = (string)r[5];
                    float x0 = (float)r[1], y0 = (float)r[2], x1 = (float)r[3], y1 = (float)r[4];
                    rooms.Add(new RoomZone { label = labels?[nm] != null ? (string)labels[nm] : nm, level = li, rect = Rect.MinMaxRect(x0, y0, x1, y1), floorY = z0, kind = kind });
                    if (kind == "plant") continue;
                    var lgo = new GameObject("Light_" + li + "_" + nm);
                    lgo.transform.SetParent(lightsRoot.transform);
                    float ceil = li == levels.Count - 1 ? zt - 0.15f : (float)levels[li + 1]["z"] - 0.3f;
                    lgo.transform.position = new Vector3((x0 + x1) / 2, ceil - 0.25f, (y0 + y1) / 2);
                    var l = lgo.AddComponent<Light>();
                    l.type = LightType.Point; l.shadows = LightShadows.None;
                    l.color = new Color(1f, 0.82f, 0.62f);
                    l.range = Mathf.Max(x1 - x0, y1 - y0) * 0.9f + 1.5f;
                    l.intensity = 1.6f;
                    lights.Add(l);
                    if (li > 0) upper.Add(lgo);
                }
            }
            // gate lamps
            foreach (var gx in new[] { 4.9f, 8.3f })
            {
                var lgo = new GameObject("GateLamp"); lgo.transform.SetParent(lightsRoot.transform);
                lgo.transform.position = new Vector3(gx, 2.0f, -0.4f);
                var l = lgo.AddComponent<Light>(); l.type = LightType.Point; l.range = 5; l.intensity = 2.5f; l.color = new Color(1f, .72f, .45f);
                lights.Add(l);
            }

            // post-processing volume
            var prof = AssetDatabase.LoadAssetAtPath<VolumeProfile>("Assets/Home/Settings/CW_PostFX.asset");
            if (prof)
            {
                var vgo = new GameObject("PostFX");
                var vol = vgo.AddComponent<Volume>(); vol.isGlobal = true; vol.sharedProfile = prof;
            }

            // player
            var player = new GameObject("Player");
            var cc = player.AddComponent<CharacterController>();
            cc.height = 1.7f; cc.radius = 0.25f; cc.center = new Vector3(0, 0.86f, 0); cc.stepOffset = 0.32f; cc.slopeLimit = 50; cc.skinWidth = 0.03f;
            var pivot = new GameObject("CamPivot"); pivot.transform.SetParent(player.transform, false); pivot.transform.localPosition = new Vector3(0, 1.6f, 0);
            var cam = pivot.AddComponent<Camera>(); cam.fieldOfView = 70; cam.nearClipPlane = 0.05f; cam.farClipPlane = 1500;
            cam.tag = "MainCamera";
            var cad = cam.GetUniversalAdditionalCameraData(); cad.renderPostProcessing = true; cad.antialiasing = AntialiasingMode.SubpixelMorphologicalAntiAliasing;
            pivot.AddComponent<AudioListener>();
            var fpc = player.AddComponent<FirstPersonController>(); fpc.cameraPivot = pivot.transform;

            // walkthrough
            var wt = new GameObject("Walkthrough").AddComponent<Walkthrough>();
            wt.conceptTitle = ((string)C["title"]).Replace("CONCEPT 1 — ", "Concept 1 · ");
            wt.player = fpc; wt.sun = sun;
            wt.roofObjects = roof.ToArray();
            wt.upperObjects = upper.ToArray();
            wt.interiorLights = lights.ToArray();
            wt.rooms = rooms.ToArray();
            wt.upperFloorY = zUpper;
            var ont = S["bands"]["ONT"];
            wt.ontRect = Rect.MinMaxRect(0, (float)ont["y0"], (float)S["site"]["width"], (float)ont["y1"]);
            wt.siteRect = Rect.MinMaxRect(0, 0, (float)S["site"]["width"], (float)S["site"]["depth_west"]);
            var vps = new List<Viewpoint>();
            var order = new[] { "street", "entry", "living", "kitchen", "master", "lounge", "balcony", "garden", "aerial" };
            var V = (JObject)C["viewpoints"];
            foreach (var key in order)
            {
                if (V[key] == null) continue;
                var p = V[key]["pos"]; var l = V[key]["look"];
                var eye = U((float)p[0], (float)p[1], (float)p[2]);
                var look = U((float)l[0], (float)l[1], (float)l[2]);
                var d = look - eye;
                float yaw = Mathf.Atan2(d.x, d.z) * Mathf.Rad2Deg;
                float pitch = -Mathf.Atan2(d.y, new Vector2(d.x, d.z).magnitude) * Mathf.Rad2Deg;
                vps.Add(new Viewpoint { name = char.ToUpper(key[0]) + key.Substring(1), pos = eye - new Vector3(0, 1.6f, 0), yaw = yaw, pitch = pitch });
            }
            wt.viewpoints = vps.ToArray();
            var v0 = vps[0];
            player.transform.position = v0.pos; player.transform.rotation = Quaternion.Euler(0, v0.yaw, 0);
            wt.ApplyTod();

            Directory.CreateDirectory(Path.GetDirectoryName(scenePath));
            EditorSceneManager.SaveScene(scene, scenePath);
            EditorBuildSettings.scenes = new[] { new EditorBuildSettingsScene(scenePath, true) };
            foreach (var n in new[] { "SM_Prop_Couch_01", "SM_Prop_Couch_02", "SM_Prop_Couch_04", "SM_Prop_Couch_05", "SM_Prop_Couch_06", "SM_Prop_Couch_07", "SM_Prop_CeilingFan_01", "SM_Prop_DiningTable_01", "SM_Prop_Bed_Double_01" })
            {
                var pfb = FindPrefab(n); if (!pfb) continue;
                var t = (GameObject)Object.Instantiate(pfb); var bb = WorldBounds(t);
                Debug.Log($"[Home] SURVEY {n} size {bb.size:F2} centerOffset {(bb.center - t.transform.position):F2}");
                Object.DestroyImmediate(t);
            }
            Debug.Log($"[Home] built {scenePath}: {placed.Count} furniture items ({missing} missing), {rooms.Count} rooms, {lights.Count} lights, {vps.Count} viewpoints");
        }

        // ---------------------------------------------------------------- helpers --
        static float Yaw(string face) => face switch { "N" => 0f, "E" => 90f, "S" => 180f, "W" => 270f, _ => float.TryParse(face, out var f) ? f : 0f };

        public static Bounds WorldBounds(GameObject go)
        {
            var rs = go.GetComponentsInChildren<Renderer>();
            if (rs.Length == 0) return new Bounds(go.transform.position, Vector3.zero);
            var b = rs[0].bounds;
            foreach (var r in rs) b.Encapsulate(r.bounds);
            return b;
        }

        static readonly Dictionary<string, GameObject> _prefabCache = new();
        public static GameObject FindPrefab(string name)
        {
            if (_prefabCache.TryGetValue(name, out var g) && g) return g;
            foreach (var guid in AssetDatabase.FindAssets(name + " t:Prefab", new[] { "Assets/Synty" }))
            {
                var path = AssetDatabase.GUIDToAssetPath(guid);
                if (Path.GetFileNameWithoutExtension(path) != name) continue;
                // prefer PolygonTown (domestic) when a name exists in several packs
                g = AssetDatabase.LoadAssetAtPath<GameObject>(path);
                if (path.Contains("PolygonTown")) break;
            }
            _prefabCache[name] = g;
            return g;
        }

        static void ConfigureFbx(string path)
        {
            var mi = AssetImporter.GetAtPath(path) as ModelImporter;
            if (mi == null) { Debug.LogError("[Home] no FBX at " + path); return; }
            bool dirty = mi.materialImportMode != ModelImporterMaterialImportMode.None || mi.importAnimation || !mi.bakeAxisConversion;
            mi.materialImportMode = ModelImporterMaterialImportMode.None;
            mi.importAnimation = false;
            mi.importCameras = false; mi.importLights = false;
            mi.bakeAxisConversion = true;
            mi.importNormals = ModelImporterNormals.Import;
            if (dirty) mi.SaveAndReimport();
        }

        /// Try the 8 yaw/mirror combinations and keep the one that puts the plinth where the data says it is.
        static void FixAxes(GameObject arch, Bounds expected)
        {
            var plinth = arch.GetComponentsInChildren<MeshRenderer>().FirstOrDefault(r => r.name.StartsWith("L0__stone_dk"));
            if (plinth == null) { Debug.LogWarning("[Home] plinth not found; axes unchecked"); return; }
            float best = float.MaxValue; Quaternion bq = Quaternion.identity; Vector3 bs = Vector3.one;
            foreach (var yaw in new[] { 0f, 90f, 180f, 270f })
                foreach (var mx in new[] { 1f, -1f })
                {
                    arch.transform.rotation = Quaternion.Euler(0, yaw, 0);
                    arch.transform.localScale = new Vector3(mx, 1, 1);
                    Physics.SyncTransforms();
                    var b = plinth.bounds;
                    float err = (b.min - expected.min).magnitude + (b.max - expected.max).magnitude;
                    if (err < best) { best = err; bq = arch.transform.rotation; bs = arch.transform.localScale; }
                }
            arch.transform.rotation = bq; arch.transform.localScale = bs;
            Debug.Log($"[Home] FBX axes: rot={bq.eulerAngles} scale={bs} err={best:F3}");
            if (best > 0.2f) Debug.LogError("[Home] FBX placement does not match the data (err " + best + ")");
        }

        // -------------------------------------------------------------- materials --
        static readonly Dictionary<string, (Color c, float smooth, string tex)> MatDefs = new()
        {
            { "plaster", (new Color(.93f, .90f, .84f), .15f, "plaster") },
            { "plaster_w", (new Color(1f, 1f, 1f), .15f, "plaster_w") },
            { "plaster_s", (new Color(.75f, .72f, .68f), .1f, "plaster") },
            { "brick", (Color.white, .12f, "brick") },
            { "brick_red", (Color.white, .12f, "brick") },
            { "breeze", (Color.white, .1f, "breeze") },
            { "tile_roof", (Color.white, .25f, "tile_roof") },
            { "timber", (Color.white, .3f, "timber") },
            { "timber_dk", (Color.white, .35f, "timber_dk") },
            { "slat", (Color.white, .3f, "timber") },
            { "cement_tile", (Color.white, .45f, "cement_tile") },
            { "terracotta", (Color.white, .3f, "terracotta") },
            { "stone", (Color.white, .2f, "stone") },
            { "stone_dk", (Color.white, .2f, "stone_dk") },
            { "paver", (Color.white, .2f, "paver") },
            { "grass", (Color.white, .05f, "grass") },
            { "gravel", (Color.white, .1f, "gravel") },
            { "asphalt", (Color.white, .15f, "asphalt") },
            { "soil", (Color.white, .05f, "soil") },
            { "existing", (Color.white, .1f, "existing") },
            { "white", (new Color(.95f, .93f, .88f), .3f, null) },
            { "white2", (new Color(.85f, .84f, .82f), .3f, null) },
            { "river", (new Color(.22f, .34f, .36f), .92f, null) },
            { "water", (new Color(.15f, .38f, .42f), .95f, null) },
            { "leaf", (new Color(.25f, .42f, .18f), .1f, null) },
            { "leaf2", (new Color(.3f, .48f, .2f), .1f, null) },
            { "dark", (new Color(.08f, .08f, .07f), .2f, null) },
            { "charcoal", (new Color(.12f, .12f, .11f), .2f, null) },
            { "glass", (new Color(.55f, .65f, .7f, .22f), .95f, null) },
            { "glass_dk", (new Color(.45f, .55f, .6f, .35f), .95f, null) },
        };

        public static Dictionary<string, Material> MakeMaterials()
        {
            var lit = Shader.Find("Universal Render Pipeline/Lit");
            Directory.CreateDirectory("Assets/Home/Materials");
            var outd = new Dictionary<string, Material>();
            foreach (var kv in MatDefs)
            {
                var path = $"Assets/Home/Materials/M_{kv.Key}.mat";
                var m = AssetDatabase.LoadAssetAtPath<Material>(path);
                if (m == null) { m = new Material(lit); AssetDatabase.CreateAsset(m, path); }
                m.shader = lit;
                var (c, sm, tex) = kv.Value;
                m.SetColor("_BaseColor", c);
                m.SetFloat("_Smoothness", sm);
                m.SetFloat("_Metallic", 0f);
                if (tex != null)
                {
                    var tpath = $"Assets/Home/Textures/{tex}.png";
                    var ti = AssetImporter.GetAtPath(tpath) as TextureImporter;
                    if (ti != null && (ti.wrapMode != TextureWrapMode.Repeat || ti.anisoLevel < 4))
                    { ti.wrapMode = TextureWrapMode.Repeat; ti.anisoLevel = 8; ti.SaveAndReimport(); }
                    m.SetTexture("_BaseMap", AssetDatabase.LoadAssetAtPath<Texture2D>(tpath));
                }
                if (c.a < 0.99f)
                {
                    m.SetFloat("_Surface", 1); m.SetFloat("_Blend", 0);
                    m.SetOverrideTag("RenderType", "Transparent");
                    m.SetInt("_SrcBlend", (int)BlendMode.SrcAlpha); m.SetInt("_DstBlend", (int)BlendMode.OneMinusSrcAlpha);
                    m.SetInt("_ZWrite", 0); m.renderQueue = (int)RenderQueue.Transparent;
                    m.EnableKeyword("_SURFACE_TYPE_TRANSPARENT");
                }
                EditorUtility.SetDirty(m);
                outd[kv.Key] = m;
            }
            AssetDatabase.SaveAssets();
            return outd;
        }
    }
}
