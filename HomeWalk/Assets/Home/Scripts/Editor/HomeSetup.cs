using System.IO;
using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

namespace HomeWalk.EditorTools
{
    /// One-off project configuration (URP asset, colour space, input, product name). Safe to re-run.
    public static class HomeSetup
    {
        const string Pipe = "Assets/Home/Settings/CW_URP.asset";

        [MenuItem("Home/Setup/Configure Project")]
        public static void Configure()
        {
            var pipeline = AssetDatabase.LoadAssetAtPath<UniversalRenderPipelineAsset>(Pipe);
            if (pipeline != null)
            {
                pipeline.shadowDistance = 70f;
                GraphicsSettings.defaultRenderPipeline = pipeline;
                for (int i = 0; i < QualitySettings.names.Length; i++)
                {
                    QualitySettings.SetQualityLevel(i, false);
                    QualitySettings.renderPipeline = pipeline;
                }
                QualitySettings.SetQualityLevel(QualitySettings.names.Length - 1, false);
            }
            else Debug.LogError("[Home] URP asset missing at " + Pipe);
            PlayerSettings.colorSpace = ColorSpace.Linear;
            PlayerSettings.productName = "HomeWalk";
            PlayerSettings.companyName = "HomeDesign";
            var ps = AssetDatabase.LoadAllAssetsAtPath("ProjectSettings/ProjectSettings.asset")[0];
            var so = new SerializedObject(ps);
            var prop = so.FindProperty("activeInputHandler");
            if (prop != null) { prop.intValue = 2; so.ApplyModifiedProperties(); }
            AssetDatabase.SaveAssets();
            Debug.Log("[Home] project configured");
        }

        /// Batch probe: log how the Blender FBX lands in Unity space.
        public static void ProbeFbx()
        {
            Configure();
            var go = AssetDatabase.LoadAssetAtPath<GameObject>("Assets/Home/Models/c1_architecture.fbx");
            if (go == null) { Debug.LogError("[Home] fbx not imported"); return; }
            var inst = (GameObject)Object.Instantiate(go);
            foreach (var r in inst.GetComponentsInChildren<Renderer>())
                if (r.name.StartsWith("L0__") || r.name.StartsWith("SITE__existing") || r.name.StartsWith("PORCH"))
                    Debug.Log($"[Home] PROBE {r.name} bounds min={r.bounds.min} max={r.bounds.max}");
            Debug.Log($"[Home] PROBE root rot={go.transform.localEulerAngles} scale={go.transform.localScale}");
        }
    }
}
