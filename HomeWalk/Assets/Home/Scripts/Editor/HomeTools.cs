using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.AI;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;
using Unity.AI.Navigation;

namespace HomeWalk.EditorTools
{
    /// Review screenshots, walk test and player builds. All runnable in batch mode:
    ///   -executeMethod HomeWalk.EditorTools.HomeTools.BuildAndShoot
    ///   -executeMethod HomeWalk.EditorTools.HomeTools.WalkTest
    ///   -executeMethod HomeWalk.EditorTools.HomeTools.BuildLinux | BuildWindows | BuildWebGL
    public static class HomeTools
    {
        static string OutDir => Path.Combine(HomeBuilder.Root, "out", "c1", "unity");

        [MenuItem("Home/Review/Render Viewpoint Shots")]
        public static void Shoot()
        {
            if (EditorSceneManager.GetActiveScene().path != HomeBuilder.ScenePath) EditorSceneManager.OpenScene(HomeBuilder.ScenePath);
            var wt = Object.FindAnyObjectByType<Walkthrough>();
            Directory.CreateDirectory(OutDir);
            var go = new GameObject("ShotCam");
            var cam = go.AddComponent<Camera>();
            cam.fieldOfView = 70; cam.nearClipPlane = 0.05f; cam.farClipPlane = 1500;
            cam.GetUniversalAdditionalCameraData().renderPostProcessing = true;
            const int W = 1600, H = 1000;
            var rt = new RenderTexture(W, H, 24, RenderTextureFormat.ARGB32) { antiAliasing = 4 };
            cam.targetTexture = rt;
            var tex = new Texture2D(W, H, TextureFormat.RGB24, false);
            var extra = new List<Viewpoint>(wt.viewpoints);
            // dollhouse views (roof + upper hidden) for plan reading
            extra.Add(new Viewpoint { name = "Dollhouse_ground", pos = new Vector3(-6f, 16f, -6f), yaw = 40f, pitch = 48f });
            int i = 0;
            Debug.Log($"[Home] DIAG sun.forward={wt.sun.transform.forward:F2} euler={wt.sun.transform.eulerAngles:F1}");
            foreach (var r in Object.FindObjectsByType<MeshRenderer>(FindObjectsSortMode.None))
                if (r.name.StartsWith("SITE__asphalt") || r.name.StartsWith("SITE__river") || r.name.StartsWith("SITE__existing"))
                    Debug.Log($"[Home] DIAG {r.name} bounds {r.bounds.min:F1}..{r.bounds.max:F1} lossyScale={r.transform.lossyScale}");
            // warm-up: the first render after loading has no valid shadow map (renders the scene in shadow)
            go.transform.position = extra[0].pos + Vector3.up * 1.6f;
            for (int w = 0; w < 3; w++) cam.Render();
            foreach (var v in extra)
            {
                bool doll = v.name.StartsWith("Dollhouse");
                foreach (var g in wt.roofObjects) g.SetActive(!doll);
                foreach (var g in wt.upperObjects) g.SetActive(!doll);
                go.transform.position = v.pos + new Vector3(0, 1.6f, 0);
                go.transform.rotation = Quaternion.Euler(v.pitch, v.yaw, 0);
                cam.fieldOfView = v.name == "Aerial" ? 50 : 70;
                if (v.name == "Aerial") Debug.Log($"[Home] DIAG aerial cam pos={go.transform.position:F1} fwd={go.transform.forward:F2}");
                cam.Render();
                RenderTexture.active = rt;
                tex.ReadPixels(new Rect(0, 0, W, H), 0, 0); tex.Apply();
                File.WriteAllBytes(Path.Combine(OutDir, $"{++i:00}_{v.name.ToLower()}.png"), tex.EncodeToPNG());
            }
            foreach (var g in wt.roofObjects) g.SetActive(true);
            foreach (var g in wt.upperObjects) g.SetActive(true);
            RenderTexture.active = null; cam.targetTexture = null;
            Object.DestroyImmediate(go); Object.DestroyImmediate(rt);
            Debug.Log("[Home] shots written to " + OutDir);
        }

        public static void SunTest()
        {
            EditorSceneManager.OpenScene(HomeBuilder.ScenePath);
            var wt = Object.FindAnyObjectByType<Walkthrough>();
            var go = new GameObject("ShotCam"); var cam = go.AddComponent<Camera>(); cam.fieldOfView = 70;
            var rt = new RenderTexture(800, 500, 24); cam.targetTexture = rt; var tex = new Texture2D(800, 500, TextureFormat.RGB24, false);
            var v = wt.viewpoints[0];
            go.transform.position = v.pos + Vector3.up * 1.6f; go.transform.rotation = Quaternion.Euler(v.pitch, v.yaw, 0);
            foreach (var az in new[] { 222f, 200f, 240f, 180f })
            {
                float e = (az == 240f ? 19f : 30f) * Mathf.Deg2Rad, a = az * Mathf.Deg2Rad;
                var toSun = new Vector3(Mathf.Sin(a) * Mathf.Cos(e), Mathf.Sin(e), Mathf.Cos(a) * Mathf.Cos(e));
                wt.sun.transform.rotation = Quaternion.LookRotation(-toSun);
                foreach (var shad in new[] { true, false })
                {
                    wt.sun.shadows = shad ? LightShadows.Soft : LightShadows.None;
                    cam.Render(); RenderTexture.active = rt; tex.ReadPixels(new Rect(0, 0, 800, 500), 0, 0); tex.Apply();
                    File.WriteAllBytes(Path.Combine(OutDir, $"suntest_{az}_{(shad ? "sh" : "nosh")}.png"), tex.EncodeToPNG());
                }
            }
            foreach (var rr in Object.FindObjectsByType<Renderer>(FindObjectsSortMode.None))
                if (rr.shadowCastingMode != UnityEngine.Rendering.ShadowCastingMode.Off && (rr.bounds.size.x > 25 || rr.bounds.size.y > 15 || rr.bounds.size.z > 25))
                    Debug.Log($"[Home] SUNTEST big caster {rr.name} parent={(rr.transform.parent ? rr.transform.parent.name : "-")} bounds {rr.bounds.min:F0}..{rr.bounds.max:F0}");
            wt.ApplyTod();
            foreach (var pp in new[] { false, true })
            {
                cam.GetUniversalAdditionalCameraData().renderPostProcessing = pp;
                cam.Render(); RenderTexture.active = rt; tex.ReadPixels(new Rect(0, 0, 800, 500), 0, 0); tex.Apply();
                File.WriteAllBytes(Path.Combine(OutDir, $"suntest_tod_pp{pp}.png"), tex.EncodeToPNG());
            }
            Debug.Log($"[Home] SUNTEST tod sun fwd {wt.sun.transform.forward:F2} shadows {wt.sun.shadows} intensity {wt.sun.intensity}");
            var mr = Object.FindObjectsByType<MeshRenderer>(FindObjectsSortMode.None).First(r => r.name.StartsWith("L0__brick"));
            var mesh = mr.GetComponent<MeshFilter>().sharedMesh;
            int south = 0, north = 0;
            var nrm = mesh.normals; var vtx = mesh.vertices;
            for (int i = 0; i < nrm.Length; i++) { if (vtx[i].z < 2.3f) { if (nrm[i].z < -0.5f) south++; if (nrm[i].z > 0.5f) north++; } }
            Debug.Log($"[Home] SUNTEST brick verts at south face z<2.3: normals -z={south} +z={north}; mr.transform {mr.transform.lossyScale} {mr.transform.eulerAngles}");
        }

        /// Everything: rebuild scene, shots, walk test, Linux + Windows players, WebGL into docs/play.
        public static void ReleaseAll()
        {
            BuildAndShoot();
            BuildLinux();
            BuildWindows();
            BuildWebGL();
        }

        public static void BuildAndShoot()
        {
            HomeBuilder.BatchBuild();
            Shoot();
            WalkTest();
        }

        /// NavMesh routes from the road gate to every room; reports any room that can't be reached.
        [MenuItem("Home/Review/Walk Test")]
        public static void WalkTest()
        {
            if (EditorSceneManager.GetActiveScene().path != HomeBuilder.ScenePath) EditorSceneManager.OpenScene(HomeBuilder.ScenePath);
            var wt = Object.FindAnyObjectByType<Walkthrough>();
            var navGo = new GameObject("NavSurface");
            var surf = navGo.AddComponent<NavMeshSurface>();
            surf.collectObjects = CollectObjects.All;
            surf.useGeometry = NavMeshCollectGeometry.PhysicsColliders;
            // Configure the built-in Humanoid agent (id 0) to human size; NavMesh.CreateSettings() types are ignored by NavMeshSurface builds.
            var navSo = new SerializedObject(AssetDatabase.LoadAllAssetsAtPath("ProjectSettings/NavMeshAreas.asset")[0]);
            var agents = navSo.FindProperty("m_Settings");
            var a0 = agents.GetArrayElementAtIndex(0);
            a0.FindPropertyRelative("agentRadius").floatValue = 0.22f;
            a0.FindPropertyRelative("agentHeight").floatValue = 1.7f;
            a0.FindPropertyRelative("agentClimb").floatValue = 0.3f;
            a0.FindPropertyRelative("agentSlope").floatValue = 45f;
            navSo.ApplyModifiedPropertiesWithoutUndo();
            AssetDatabase.SaveAssets();
            surf.agentTypeID = 0;
            var settings = NavMesh.GetSettingsByID(0);
            surf.overrideVoxelSize = true; surf.voxelSize = 0.04f; surf.minRegionArea = 0.3f;
            surf.BuildNavMesh();
            foreach (var (nm, c, ext) in new[] { ("laundry door", new Vector3(4.5f, 1.45f, 3.6f), new Vector3(0.3f, 0.9f, 0.3f)), ("stair bottom gap", new Vector3(3.0f, 1.45f, 8.4f), new Vector3(0.1f, 0.9f, 0.3f)), ("pantry door", new Vector3(8.7f, 1.45f, 3.6f), new Vector3(0.3f, 0.9f, 0.3f)) })
            {
                var cs = Physics.OverlapBox(c, ext);
                Debug.Log($"[Home] DOORPROBE {nm}: " + string.Join(", ", cs.Select(x => x.name + (x is MeshCollider mc ? "(mesh)" : "(" + x.GetType().Name + ")"))));
                foreach (var dir in new[] { Vector3.left, Vector3.right, Vector3.forward, Vector3.back })
                    if (Physics.Raycast(c, dir, out var hh, 1.5f)) Debug.Log($"[Home] DOORPROBE   {nm} ray {dir} hits {hh.collider.name} at {hh.distance:F2}");
            }
            var tri = NavMesh.CalculateTriangulation();
            Debug.Log($"[Home] NAV triangulation verts={tri.vertices.Length} tris={tri.indices.Length / 3}");
            int inLaundry = tri.vertices.Count(vv => vv.x > 1.5f && vv.x < 4.5f && vv.z > 2.4f && vv.z < 4.8f);
            int inBed1 = tri.vertices.Count(vv => vv.x > 4.5f && vv.x < 8.7f && vv.z > 2.4f && vv.z < 6.2f && vv.y > 3f && vv.y < 4.5f);
            Debug.Log($"[Home] NAV verts in laundry={inLaundry} bedroom1={inBed1}; bounds {(tri.vertices.Length > 0 ? new Bounds(tri.vertices[0], Vector3.zero) : new Bounds())}");
            var start = new Vector3(6.6f, 0.05f, -3f);   // on the footpath outside the gate
            NavMesh.SamplePosition(start, out var sh, 2f, new NavMeshQueryFilter { agentTypeID = settings.agentTypeID, areaMask = NavMesh.AllAreas });
            var sb = new StringBuilder();
            sb.AppendLine($"Walk test (agent radius {settings.agentRadius}, climb {settings.agentClimb}) from road gate");
            int ok = 0, total = 0;
            foreach (var r in wt.rooms)
            {
                if (r.kind == "plant") continue;
                if (r.label == "Stair") continue;
                total++;
                var qf = new NavMeshQueryFilter { agentTypeID = settings.agentTypeID, areaMask = NavMesh.AllAreas };
                int walk = 0, samples = 0; Vector3 first = Vector3.zero; bool found = false;
                for (float gx = r.rect.xMin + 0.3f; gx < r.rect.xMax - 0.29f; gx += 0.3f)
                    for (float gz = r.rect.yMin + 0.3f; gz < r.rect.yMax - 0.29f; gz += 0.3f)
                    {
                        samples++;
                        if (NavMesh.SamplePosition(new Vector3(gx, r.floorY + 0.05f, gz), out var h, 0.2f, qf) && Mathf.Abs(h.position.y - r.floorY) < 0.25f)
                        {
                            walk++;
                            var ctr = new Vector3(r.rect.center.x, h.position.y, r.rect.center.y);
                            if (!found || (h.position - ctr).sqrMagnitude < (first - ctr).sqrMagnitude) { found = true; first = h.position; }
                        }
                    }
                var path = new NavMeshPath();
                bool reach = found && NavMesh.CalculatePath(sh.position, first, qf, path) && path.status == NavMeshPathStatus.PathComplete;
                if (walk == 0)
                {
                    var cpt = new Vector3(r.rect.center.x, r.floorY + 2.2f, r.rect.center.y);
                    var hits = Physics.RaycastAll(cpt, Vector3.down, 3f);
                    System.Array.Sort(hits, (a, b) => a.distance.CompareTo(b.distance));
                    sb.AppendLine($"     probe down from {cpt}: " + string.Join(", ", hits.Select(hh => $"{hh.collider.name}@{hh.point.y:F2} n={hh.normal.y:F2}")));
                    var cols = Physics.OverlapBox(new Vector3(r.rect.center.x, r.floorY + 0.9f, r.rect.center.y), new Vector3(r.rect.width / 2 - 0.2f, 0.75f, r.rect.height / 2 - 0.2f));
                    sb.AppendLine("     overlapping: " + string.Join(", ", cols.Select(cc => cc.name).Distinct().Take(12)));
                }
                float len = 0; for (int k = 1; k < path.corners.Length; k++) len += Vector3.Distance(path.corners[k - 1], path.corners[k]);
                if (reach) ok++;
                else if (found && path.corners.Length > 0) sb.AppendLine($"     partial path ends at {path.corners[path.corners.Length - 1]:F2} (target {first:F2})");
                sb.AppendLine($"  {(reach ? "OK  " : "FAIL")} L{r.level} {r.label,-22} path {len,5:F1} m  walkable {100f * walk / Mathf.Max(1, samples),3:F0}% of floor{(found ? "" : "  (no navmesh in room)")}");
            }
            sb.AppendLine($"{ok}/{total} rooms reachable");
            // stair diagnostics: navmesh heights along both flights
            var stairPts = new[] { new Vector3(3.8f, 0.5f, 8.6f), new Vector3(2.2f, 0.5f, 8.4f), new Vector3(2.2f, 1.0f, 9.4f), new Vector3(3.0f, 2.1f, 11.5f), new Vector3(3.8f, 2.9f, 9.8f), new Vector3(3.8f, 3.8f, 8.4f), new Vector3(3.8f, 3.8f, 7.5f) };
            foreach (var spt in stairPts)
            {
                var qf2 = new NavMeshQueryFilter { agentTypeID = settings.agentTypeID, areaMask = NavMesh.AllAreas };
                bool f2 = NavMesh.SamplePosition(spt, out var h2, 0.35f, qf2);
                var p2 = new NavMeshPath(); bool r2 = f2 && NavMesh.CalculatePath(sh.position, h2.position, qf2, p2) && p2.status == NavMeshPathStatus.PathComplete;
                sb.AppendLine($"  stair probe {spt}: {(f2 ? "navmesh y=" + h2.position.y.ToString("F2") : "none")} {(r2 ? "reachable" : "")}");
            }
            Object.DestroyImmediate(navGo);
            NavMesh.RemoveAllNavMeshData();
            Directory.CreateDirectory(OutDir);
            File.WriteAllText(Path.Combine(OutDir, "walktest.txt"), sb.ToString());
            Debug.Log("[Home] " + sb);
        }

        // ------------------------------------------------------------------ builds --
        [MenuItem("Home/Build/Linux")] public static void BuildLinux() => Build(BuildTarget.StandaloneLinux64, "Builds/Linux/HomeWalk.x86_64");
        [MenuItem("Home/Build/Windows")] public static void BuildWindows() => Build(BuildTarget.StandaloneWindows64, "Builds/Windows/HomeWalk.exe");
        [MenuItem("Home/Build/WebGL")] public static void BuildWebGL() => Build(BuildTarget.WebGL, Path.Combine(HomeBuilder.Root, "docs", "play"));

        static void UsePipeline(RenderPipelineAsset p)
        {
            GraphicsSettings.defaultRenderPipeline = p;
            int cur = QualitySettings.GetQualityLevel();
            for (int i = 0; i < QualitySettings.names.Length; i++) { QualitySettings.SetQualityLevel(i, false); QualitySettings.renderPipeline = p; }
            QualitySettings.SetQualityLevel(cur, false);
            AssetDatabase.SaveAssets();
        }

        /// WebGL2 can't run Forward+ (needs storage buffers), APV or heavy SSAO: a copy of the desktop URP asset
        /// set to plain Forward, legacy light probes, no renderer features, no MSAA, shorter shadows.
        static RenderPipelineAsset WebGLPipeline()
        {
            const string dir = "Assets/Home/Settings/";
            AssetDatabase.DeleteAsset(dir + "WebGL_URP.asset");
            AssetDatabase.DeleteAsset(dir + "WebGL_Renderer.asset");
            AssetDatabase.CopyAsset(dir + "CW_Renderer.asset", dir + "WebGL_Renderer.asset");
            AssetDatabase.CopyAsset(dir + "CW_URP.asset", dir + "WebGL_URP.asset");
            var rd = AssetDatabase.LoadAssetAtPath<UniversalRendererData>(dir + "WebGL_Renderer.asset");
            rd.renderingMode = RenderingMode.Forward;
            foreach (var f in rd.rendererFeatures.ToArray()) if (f) Object.DestroyImmediate(f, true);
            rd.rendererFeatures.Clear();
            var rso = new SerializedObject(rd);
            var map = rso.FindProperty("m_RendererFeatureMap"); if (map != null) map.arraySize = 0;
            rso.ApplyModifiedPropertiesWithoutUndo();
            EditorUtility.SetDirty(rd);
            var pipe = AssetDatabase.LoadAssetAtPath<UniversalRenderPipelineAsset>(dir + "WebGL_URP.asset");
            var pso = new SerializedObject(pipe);
            var list = pso.FindProperty("m_RendererDataList");
            list.arraySize = 1; list.GetArrayElementAtIndex(0).objectReferenceValue = rd;
            pso.FindProperty("m_DefaultRendererIndex").intValue = 0;
            var lp = pso.FindProperty("m_LightProbeSystem"); if (lp != null) lp.enumValueIndex = 0;
            pso.ApplyModifiedPropertiesWithoutUndo();
            pipe.msaaSampleCount = 1;
            pipe.shadowDistance = 40f;
            pipe.supportsHDR = false;
            pipe.supportsCameraOpaqueTexture = false;
            EditorUtility.SetDirty(pipe);
            AssetDatabase.SaveAssets();
            Debug.Log("[Home] WebGL pipeline: Forward, no features, legacy probes");
            return pipe;
        }

        static void Build(BuildTarget target, string path)
        {
            PlayerSettings.productName = "HomeWalk";
            PlayerSettings.companyName = "HomeDesign";
            PlayerSettings.runInBackground = false;
            if (target == BuildTarget.WebGL)
            {
                PlayerSettings.WebGL.compressionFormat = WebGLCompressionFormat.Gzip;
                PlayerSettings.WebGL.decompressionFallback = true;   // GitHub Pages can't set Content-Encoding
                PlayerSettings.WebGL.dataCaching = true;
                PlayerSettings.WebGL.exceptionSupport = WebGLExceptionSupport.None;
                PlayerSettings.SetGraphicsAPIs(target, new[] { UnityEngine.Rendering.GraphicsDeviceType.OpenGLES3 });
                EditorUserBuildSettings.SwitchActiveBuildTarget(BuildTargetGroup.WebGL, BuildTarget.WebGL);
                if (Directory.Exists(path)) Directory.Delete(path, true);
            }
            else
            {
                PlayerSettings.fullScreenMode = FullScreenMode.FullScreenWindow;
                PlayerSettings.defaultIsNativeResolution = true;
                PlayerSettings.SetGraphicsAPIs(target, target == BuildTarget.StandaloneWindows64
                    ? new[] { UnityEngine.Rendering.GraphicsDeviceType.Direct3D11 }
                    : new[] { UnityEngine.Rendering.GraphicsDeviceType.Vulkan, UnityEngine.Rendering.GraphicsDeviceType.OpenGLCore });
                Directory.CreateDirectory(Path.GetDirectoryName(path));
            }
            var opts = new BuildPlayerOptions { scenes = new[] { HomeBuilder.ScenePath }, locationPathName = path, target = target, options = BuildOptions.None };
            var desktopPipe = GraphicsSettings.defaultRenderPipeline;
            if (target == BuildTarget.WebGL) UsePipeline(WebGLPipeline());
            BuildReport report;
            try { report = BuildPipeline.BuildPlayer(opts); }
            finally { if (target == BuildTarget.WebGL) UsePipeline(desktopPipe); }
            var s = report.summary;
            Debug.Log($"[Home] player build {target}: {s.result}, {s.totalSize / (1024 * 1024)} MB, {s.totalErrors} errors, {s.totalTime.TotalMinutes:F1} min -> {path}");
            if (s.result != BuildResult.Succeeded && Application.isBatchMode) EditorApplication.Exit(1);
        }
    }
}
