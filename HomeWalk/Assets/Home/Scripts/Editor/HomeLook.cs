using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

namespace HomeWalk.EditorTools
{
    /// The "look" of every walkthrough, set from code so all three concepts match and rebuilds are repeatable:
    /// render pipeline quality, ambient occlusion, post-processing (HDR + ACES grading), procedural sky,
    /// and per-room reflection probes baked from the finished scene.
    public static class HomeLook
    {
        const string Dir = "Assets/Home/Settings/";

        public static void ConfigurePipeline()
        {
            var pipe = AssetDatabase.LoadAssetAtPath<UniversalRenderPipelineAsset>(Dir + "CW_URP.asset");
            if (!pipe) { Debug.LogError("[Home] LOOK: no URP asset"); return; }
            pipe.supportsHDR = true;
            pipe.msaaSampleCount = 4;
            pipe.shadowDistance = 70f;
            pipe.shadowCascadeCount = 4;
            pipe.mainLightShadowmapResolution = 4096;
            pipe.colorGradingMode = ColorGradingMode.HighDynamicRange;
            var so = new SerializedObject(pipe);
            Set(so, "m_SoftShadowsSupported", p => p.boolValue = true);
            Set(so, "m_SoftShadowQuality", p => p.enumValueIndex = (int)SoftShadowQuality.High);
            Set(so, "m_AdditionalLightsPerObjectLimit", p => p.intValue = 8);
            Set(so, "m_ReflectionProbeBlending", p => p.boolValue = true);
            Set(so, "m_ReflectionProbeBoxProjection", p => p.boolValue = true);
            so.ApplyModifiedPropertiesWithoutUndo();
            EditorUtility.SetDirty(pipe);

            // screen-space ambient occlusion on the desktop renderer (the WebGL copy strips renderer features)
            var rd = AssetDatabase.LoadAssetAtPath<UniversalRendererData>(Dir + "CW_Renderer.asset");
            if (rd)
            {
                var ao = rd.rendererFeatures.OfType<ScreenSpaceAmbientOcclusion>().FirstOrDefault();
                if (!ao)
                {
                    ao = ScriptableObject.CreateInstance<ScreenSpaceAmbientOcclusion>();
                    ao.name = "SSAO";
                    AssetDatabase.AddObjectToAsset(ao, rd);
                    rd.rendererFeatures.Add(ao);
                    var rso = new SerializedObject(rd);
                    var map = rso.FindProperty("m_RendererFeatureMap");
                    AssetDatabase.TryGetGUIDAndLocalFileIdentifier(ao, out _, out long lid);
                    map.arraySize++; map.GetArrayElementAtIndex(map.arraySize - 1).longValue = lid;
                    rso.ApplyModifiedPropertiesWithoutUndo();
                }
                ao.SetActive(true);
                var aso = new SerializedObject(ao);
                Set(aso, "m_Settings.Intensity", p => p.floatValue = 1.6f);
                Set(aso, "m_Settings.Radius", p => p.floatValue = 0.35f);
                Set(aso, "m_Settings.DirectLightingStrength", p => p.floatValue = 0.2f);
                Set(aso, "m_Settings.Falloff", p => p.floatValue = 60f);
                Set(aso, "m_Settings.Downsample", p => p.boolValue = false);
                Set(aso, "m_Settings.AfterOpaque", p => p.boolValue = false);
                Set(aso, "m_Settings.Samples", p => p.enumValueIndex = 1);   // medium
                aso.ApplyModifiedPropertiesWithoutUndo();
                EditorUtility.SetDirty(ao); EditorUtility.SetDirty(rd);
                Debug.Log("[Home] LOOK: renderer features " + string.Join(", ", rd.rendererFeatures.Where(f => f).Select(f => f.GetType().Name + (f.isActive ? "" : "(off)"))));
            }
            AssetDatabase.SaveAssets();
        }

        static void Set(SerializedObject so, string path, System.Action<SerializedProperty> f)
        {
            var p = so.FindProperty(path);
            if (p != null) f(p); else Debug.LogWarning("[Home] LOOK: no property " + path);
        }

        /// Post-processing: ACES tonemapping, gentle bloom on lamps and sunlit glass, a little contrast and vignette.
        public static VolumeProfile PostFX()
        {
            var path = Dir + "CW_PostFX.asset";
            var prof = AssetDatabase.LoadAssetAtPath<VolumeProfile>(path);
            if (!prof) { prof = ScriptableObject.CreateInstance<VolumeProfile>(); AssetDatabase.CreateAsset(prof, path); }
            foreach (var c in prof.components.ToArray()) { prof.Remove(c.GetType()); Object.DestroyImmediate(c, true); }
            T Add<T>() where T : VolumeComponent
            {
                var c = prof.Add<T>(true);
                c.name = typeof(T).Name;
                AssetDatabase.AddObjectToAsset(c, prof);
                return c;
            }
            var tm = Add<Tonemapping>(); tm.mode.Override(TonemappingMode.ACES);
            var bl = Add<Bloom>(); bl.threshold.Override(1.1f); bl.intensity.Override(0.35f); bl.scatter.Override(0.65f);
            var ca = Add<ColorAdjustments>(); ca.postExposure.Override(0.35f); ca.contrast.Override(20f); ca.saturation.Override(12f);
            var wb = Add<WhiteBalance>(); wb.temperature.Override(4f);
            var sm = Add<ShadowsMidtonesHighlights>(); sm.shadows.Override(new Vector4(0.98f, 1.0f, 1.04f, 0f));
            var vg = Add<Vignette>(); vg.intensity.Override(0.2f); vg.smoothness.Override(0.45f);
            EditorUtility.SetDirty(prof);
            AssetDatabase.SaveAssets();
            return prof;
        }

        /// The WebGL player renders without HDR: ACES on clamped colours goes grey, so the browser build swaps to
        /// neutral tonemapping and a smaller exposure lift. Returns an undo action.
        public static System.Action UseLdrGrading()
        {
            var prof = AssetDatabase.LoadAssetAtPath<VolumeProfile>(Dir + "CW_PostFX.asset");
            if (!prof || !prof.TryGet<Tonemapping>(out var tm) || !prof.TryGet<ColorAdjustments>(out var ca)) return () => { };
            var (m, e) = (tm.mode.value, ca.postExposure.value);
            tm.mode.Override(TonemappingMode.None); ca.postExposure.Override(0.1f);
            EditorUtility.SetDirty(prof); AssetDatabase.SaveAssets();
            return () => { tm.mode.Override(m); ca.postExposure.Override(e); EditorUtility.SetDirty(prof); AssetDatabase.SaveAssets(); };
        }

        /// Physically-based procedural sky (tinted and exposed per time of day by Walkthrough.ApplySun).
        public static Material Sky()
        {
            var path = Dir + "CW_Sky.mat";
            var m = AssetDatabase.LoadAssetAtPath<Material>(path);
            var sh = Shader.Find("Skybox/Procedural");
            if (!m) { m = new Material(sh); AssetDatabase.CreateAsset(m, path); }
            m.shader = sh;
            m.SetFloat("_SunDisk", 2f);
            m.SetFloat("_SunSize", 0.03f);
            m.SetFloat("_SunSizeConvergence", 6f);
            m.SetFloat("_AtmosphereThickness", 0.9f);
            m.SetColor("_SkyTint", new Color(.5f, .5f, .5f));
            m.SetColor("_GroundColor", new Color(.30f, .34f, .27f));
            m.SetFloat("_Exposure", 1.2f);
            EditorUtility.SetDirty(m);
            return m;
        }

        /// Reflection probes: one box-projected probe per room (so glass, tiles and glossy floors reflect that
        /// room, not the open sky) plus one for the whole site. Baked after the scene is complete.
        public static int BakeProbes(string key, Walkthrough wt, float siteW, float siteD)
        {
            var root = new GameObject("ReflectionProbes");
            var dir = $"Assets/Home/Probes/{key}";
            if (AssetDatabase.IsValidFolder(dir)) AssetDatabase.DeleteAsset(dir);
            Directory.CreateDirectory(dir);
            AssetDatabase.Refresh();
            int n = 0;
            ReflectionProbe Make(string name, Vector3 c, Vector3 size, int res, bool hdr, int importance)
            {
                var go = new GameObject(name); go.transform.SetParent(root.transform); go.transform.position = c;
                var p = go.AddComponent<ReflectionProbe>();
                p.mode = ReflectionProbeMode.Custom;
                p.size = size; p.boxProjection = true; p.blendDistance = 0.4f;
                p.resolution = res; p.hdr = hdr; p.importance = importance;
                p.nearClipPlane = 0.05f; p.farClipPlane = 250f; p.shadowDistance = 60f;
                p.clearFlags = ReflectionProbeClearFlags.Skybox;
                var file = $"{dir}/rp_{n++:00}_{System.Text.RegularExpressions.Regex.Replace(name, "[^A-Za-z0-9]+", "_")}.{(hdr ? "exr" : "png")}";
                if (Lightmapping.BakeReflectionProbe(p, file))
                {
                    AssetDatabase.ImportAsset(file);
                    p.customBakedTexture = AssetDatabase.LoadAssetAtPath<Texture>(file);
                }
                else Debug.LogWarning("[Home] LOOK: probe bake failed " + name);
                return p;
            }
            Make("site", new Vector3(siteW / 2, 2.5f, 16f), new Vector3(siteW + 40f, 30f, 70f), 128, true, 0);
            foreach (var r in wt.rooms)
            {
                if (r.kind == "plant" || r.kind == "out") continue;
                if (r.rect.width * r.rect.height < 1.2f) continue;
                float h = 2.7f;
                var c = new Vector3(r.rect.center.x, r.floorY + 1.45f, r.rect.center.y);
                Make(r.label, c, new Vector3(r.rect.width + 0.3f, h + 0.3f, r.rect.height + 0.3f), 64, false, 1);
            }
            Debug.Log($"[Home] LOOK: baked {n} reflection probes");
            return n;
        }
    }
}
