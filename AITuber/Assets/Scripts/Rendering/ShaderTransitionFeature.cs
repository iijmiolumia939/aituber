// ShaderTransitionFeature.cs
// URP ScriptableRendererFeature that overlays the ShaderTransitionGrid full-screen shader
// during shader-mode transitions. Delegates to FullScreenPassRendererFeature so that
// Unity 6 / URP 17 RenderGraph is handled by the built-in implementation.
//
// The shader itself is a no-op at _ShaderTransitionProgress ≈ 0 or 1, so
// per-frame cost at idle is minimal (one cheap pass-through blit).
//
// Setup: AITuber > Shader Transition > Setup (add to Renderer)
// SRS refs: FR-SHADER-TRANSITION-01

using UnityEngine;
using UnityEngine.Rendering.Universal;

namespace AITuber.Rendering
{
    /// <summary>
    /// Thin wrapper around <see cref="FullScreenPassRendererFeature"/> that registers the
    /// ShaderTransitionGrid shader blit in the render pipeline.
    /// The feature is always active; the shader discards when
    /// <c>_ShaderTransitionProgress</c> is outside (0.005, 0.995).
    /// </summary>
    public class ShaderTransitionFeature : ScriptableRendererFeature
    {
        [SerializeField] public Material passMaterial;

        FullScreenPassRendererFeature _inner;

        static readonly int ProgressId = Shader.PropertyToID("_ShaderTransitionProgress");

        public override void Create()
        {
            _inner = CreateInstance<FullScreenPassRendererFeature>();
            _inner.name             = "ShaderTransitionInner";
            _inner.passMaterial     = passMaterial;
            _inner.injectionPoint   = FullScreenPassRendererFeature.InjectionPoint.AfterRenderingPostProcessing;
            _inner.fetchColorBuffer = true;
            _inner.Create();
        }

        public override void AddRenderPasses(ScriptableRenderer renderer, ref RenderingData renderingData)
        {
            if (passMaterial == null || _inner == null) return;
            _inner.AddRenderPasses(renderer, ref renderingData);
        }

        protected override void Dispose(bool disposing)
        {
            if (_inner != null)
            {
                _inner.Dispose();
                DestroyImmediate(_inner);
                _inner = null;
            }
        }
    }
}
