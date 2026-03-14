// PixelizeFeature.cs
// URP ScriptableRendererFeature — avatar-only pixelization.
//
// URP 17 (Unity 6) RecordRenderGraph 対応:
//   Execute          → GetTemporaryRT + Blit (Compatibility Mode)
//   RecordRenderGraph → AddRasterRenderPass x3 + Blitter.BlitTexture
//
// SRS refs: FR-SHADER-02 (PixelArt mode)

using UnityEngine;
using UnityEngine.Experimental.Rendering;
using UnityEngine.Rendering;
using UnityEngine.Rendering.RenderGraphModule;
using UnityEngine.Rendering.Universal;

namespace AITuber.Rendering
{
    public class PixelizeFeature : ScriptableRendererFeature
    {
        public static PixelizeFeature Instance { get; private set; }

        [Tooltip("PixelizeScreen.mat")]
        [SerializeField] public Material passMaterial;
        [Tooltip("AvatarMaskWrite.mat")]
        [SerializeField] public Material maskMaterial;
        [SerializeField, Range(60, 640)] public int resolutionX = 320;
        [SerializeField, Range(34, 360)] public int resolutionY = 180;

        private bool       _enabled   = false;
        private Renderer[] _renderers = null;
        private PixelizeAvatarPass _pass;

        public override void Create()
        {
            Instance = this;
            _pass    = new PixelizeAvatarPass();
        }

        public override void AddRenderPasses(ScriptableRenderer renderer, ref RenderingData renderingData)
        {
            if (!_enabled || passMaterial == null) return;
            _pass.Setup(maskMaterial, passMaterial, _renderers, resolutionX, resolutionY);
            renderer.EnqueuePass(_pass);
        }

        protected override void Dispose(bool disposing)
        {
            if (Instance == this) Instance = null;
        }

        public void SetEnabled(bool enabled) => _enabled = enabled;
        public void SetAvatarRenderers(Renderer[] renderers) => _renderers = renderers;

        // ─────────────────────────────────────────────────────────────────
        private class PixelizeAvatarPass : ScriptableRenderPass
        {
            static readonly int MaskRTId   = Shader.PropertyToID("_AvatarMaskRT");
            static readonly int BlitTexId  = Shader.PropertyToID("_BlitTexture");
            static readonly int ResXId     = Shader.PropertyToID("_ResolutionX");
            static readonly int ResYId     = Shader.PropertyToID("_ResolutionY");
            static readonly int MaskTempId = Shader.PropertyToID("_TempAvatarMask");
            static readonly int BlitTempId = Shader.PropertyToID("_TempPixelizeBlit");

            Material   _maskMat, _blitMat;
            Renderer[] _renderers;
            int        _resX, _resY;

            public PixelizeAvatarPass()
            {
                renderPassEvent = RenderPassEvent.AfterRenderingPostProcessing;
            }

            public void Setup(Material maskMat, Material blitMat, Renderer[] renderers, int resX, int resY)
            {
                _maskMat   = maskMat;
                _blitMat   = blitMat;
                _renderers = renderers;
                _resX      = resX;
                _resY      = resY;
            }

            // ── Compatibility Mode (RenderGraph disabled) ─────────────────
            [System.Obsolete("Compatibility Mode path for URP renderer fallback.", false)]
            public override void Execute(ScriptableRenderContext ctx, ref RenderingData rd)
            {
#pragma warning disable CS0618
                if (_blitMat == null) return;
                var cmd    = CommandBufferPool.Get("PixelizeAvatar");
                var camRT  = rd.cameraData.renderer.cameraColorTargetHandle;
                var desc   = rd.cameraData.cameraTargetDescriptor;

                cmd.GetTemporaryRT(MaskTempId, new RenderTextureDescriptor(desc.width, desc.height, RenderTextureFormat.R8, 0), FilterMode.Bilinear);
                cmd.GetTemporaryRT(BlitTempId, new RenderTextureDescriptor(desc.width, desc.height, desc.colorFormat, 0), FilterMode.Bilinear);

                cmd.SetRenderTarget(MaskTempId);
                cmd.ClearRenderTarget(false, true, Color.clear);
                DrawAvatar(cmd);
                cmd.SetGlobalTexture(MaskRTId, MaskTempId);

                cmd.Blit(camRT, BlitTempId);
                cmd.SetGlobalTexture(BlitTexId, BlitTempId);

                _blitMat.SetFloat(ResXId, _resX);
                _blitMat.SetFloat(ResYId, _resY);
                cmd.Blit(BlitTempId, camRT, _blitMat);

                cmd.ReleaseTemporaryRT(MaskTempId);
                cmd.ReleaseTemporaryRT(BlitTempId);

                ctx.ExecuteCommandBuffer(cmd);
                CommandBufferPool.Release(cmd);
#pragma warning restore CS0618
            }

            void DrawAvatar(CommandBuffer cmd)
            {
                if (_maskMat == null || _renderers == null) return;
                foreach (var r in _renderers)
                {
                    if (r == null) continue;
                    for (int sm = 0; sm < r.sharedMaterials.Length; sm++)
                        cmd.DrawRenderer(r, _maskMat, sm, 0);
                }
            }

            // ── RenderGraph Mode ──────────────────────────────────────────
            private class MaskData  { public Material mat; public Renderer[] renderers; }
            private class CopyData  { public TextureHandle source; }
            private class BlitData  { public TextureHandle blitTex, maskTex; public Material mat; public int resX, resY; }

            public override void RecordRenderGraph(RenderGraph rg, ContextContainer frameData)
            {
                if (_blitMat == null) return;

                var resourceData = frameData.Get<UniversalResourceData>();
                var cameraData   = frameData.Get<UniversalCameraData>();
                var cameraColor  = resourceData.activeColorTexture;
                var desc         = cameraData.cameraTargetDescriptor;

                var maskDesc = desc; maskDesc.graphicsFormat = GraphicsFormat.R8_UNorm; maskDesc.depthBufferBits = 0; maskDesc.msaaSamples = 1;
                TextureHandle maskHandle = UniversalRenderer.CreateRenderGraphTexture(rg, maskDesc, "_AvatarMaskRG", false, FilterMode.Bilinear);

                var blitDesc = desc; blitDesc.depthBufferBits = 0; blitDesc.msaaSamples = 1;
                TextureHandle blitHandle = UniversalRenderer.CreateRenderGraphTexture(rg, blitDesc, "_PixelizeBlitRG", false, FilterMode.Bilinear);

                // ── Pass 1: draw avatar → maskHandle ──────────────────────
                using (var b = rg.AddRasterRenderPass<MaskData>("AvatarMask_RG", out var pd))
                {
                    pd.mat = _maskMat; pd.renderers = _renderers;
                    b.SetRenderAttachment(maskHandle, 0, AccessFlags.Write);
                    b.AllowPassCulling(false);
                    b.SetRenderFunc(static (MaskData d, RasterGraphContext ctx) =>
                    {
                        ctx.cmd.ClearRenderTarget(false, true, Color.clear);
                        if (d.mat == null || d.renderers == null) return;
                        foreach (var r in d.renderers)
                        {
                            if (r == null) continue;
                            for (int sm = 0; sm < r.sharedMaterials.Length; sm++)
                                ctx.cmd.DrawRenderer(r, d.mat, sm, 0);
                        }
                    });
                }

                // ── Pass 2: copy cameraColor → blitHandle ─────────────────
                using (var b = rg.AddRasterRenderPass<CopyData>("PixelizeCopy_RG", out var pd))
                {
                    pd.source = cameraColor;
                    b.SetRenderAttachment(blitHandle, 0, AccessFlags.Write);
                    b.UseTexture(cameraColor, AccessFlags.Read);
                    b.AllowPassCulling(false);
                    b.SetRenderFunc(static (CopyData d, RasterGraphContext ctx) =>
                    {
                        Blitter.BlitTexture(ctx.cmd, d.source, new Vector4(1, 1, 0, 0), 0, false);
                    });
                }

                // ── Pass 3: lerp(orig, pixelized, mask) → cameraColor ─────
                using (var b = rg.AddRasterRenderPass<BlitData>("PixelizeBlit_RG", out var pd))
                {
                    pd.blitTex = blitHandle; pd.maskTex = maskHandle;
                    pd.mat = _blitMat; pd.resX = _resX; pd.resY = _resY;
                    b.SetRenderAttachment(cameraColor, 0, AccessFlags.Write);
                    b.UseTexture(blitHandle, AccessFlags.Read);
                    b.UseTexture(maskHandle, AccessFlags.Read);
                    b.AllowPassCulling(false);
                    b.AllowGlobalStateModification(true);
                    b.SetRenderFunc(static (BlitData d, RasterGraphContext ctx) =>
                    {
                        ctx.cmd.SetGlobalTexture(Shader.PropertyToID("_AvatarMaskRT"), d.maskTex);
                        d.mat.SetFloat(Shader.PropertyToID("_ResolutionX"), d.resX);
                        d.mat.SetFloat(Shader.PropertyToID("_ResolutionY"), d.resY);
                        Blitter.BlitTexture(ctx.cmd, d.blitTex, new Vector4(1, 1, 0, 0), d.mat, 0);
                    });
                }
            }
        }
    }
}