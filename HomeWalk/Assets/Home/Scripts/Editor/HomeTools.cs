using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.AI;
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
            foreach (var v in extra)
            {
                bool doll = v.name.StartsWith("Dollhouse");
                foreach (var g in wt.roofObjects) g.SetActive(!doll);
                foreach (var g in wt.upperObjects) g.SetActive(!doll);
                go.transform.position = v.pos + new Vector3(0, 1.6f, 0);
                go.transform.rotation = Quaternion.Euler(v.pitch, v.yaw, 0);
                cam.fieldOfView = v.name == "Aerial" ? 50 : 70;
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
            var settings = NavMesh.CreateSettings();
            settings.agentRadius = 0.22f; settings.agentHeight = 1.7f; settings.agentClimb = 0.3f; settings.agentSlope = 45f;
            surf.agentTypeID = settings.agentTypeID;
            surf.overrideVoxelSize = true; surf.voxelSize = 0.04f;
            surf.BuildNavMesh();
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
                var c = new Vector3(r.rect.center.x, r.floorY + 0.05f, r.rect.center.y);
                var qf = new NavMeshQueryFilter { agentTypeID = settings.agentTypeID, areaMask = NavMesh.AllAreas };
                bool found = NavMesh.SamplePosition(c, out var hit, Mathf.Max(r.rect.width, r.rect.height) * 0.5f, qf) && Mathf.Abs(hit.position.y - r.floorY) < 0.4f && r.rect.Contains(new Vector2(hit.position.x, hit.position.z));
                var path = new NavMeshPath();
                bool reach = found && NavMesh.CalculatePath(sh.position, hit.position, qf, path) && path.status == NavMeshPathStatus.PathComplete;
                float len = 0; for (int k = 1; k < path.corners.Length; k++) len += Vector3.Distance(path.corners[k - 1], path.corners[k]);
                if (reach) ok++;
                sb.AppendLine($"  {(reach ? "OK  " : "FAIL")} L{r.level} {r.label,-22} path {len,5:F1} m{(found ? "" : "  (no navmesh in room)")}");
            }
            sb.AppendLine($"{ok}/{total} rooms reachable");
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
            var report = BuildPipeline.BuildPlayer(opts);
            var s = report.summary;
            Debug.Log($"[Home] player build {target}: {s.result}, {s.totalSize / (1024 * 1024)} MB, {s.totalErrors} errors, {s.totalTime.TotalMinutes:F1} min -> {path}");
            if (s.result != BuildResult.Succeeded && Application.isBatchMode) EditorApplication.Exit(1);
        }
    }
}
