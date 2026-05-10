# ADR: Blender-as-Meshy Gap Analysis

**Issues**: #5
**Date**: 2026-05-02
**Status**: Draft
**Decision Type**: Spike gap analysis

---

## Context

nmg-game-dev is Blender-first by product direction, with Meshy retained only as a supplement when it is the right production tool. Issue #5 asks whether Blender can become the primary Meshy-parity authoring surface for text-to-3D asset creation, PBR texture generation, retexturing, remesh/topology, LOD generation, rigging, and animation.

The additional operating constraint is that v1 must not rely on paid or heavily rate-limited third-party APIs as the primary path. Paid or rate-limited services may be used as reference outputs or manual escape hatches, but the framework's core happy path must run locally or against free/open tooling that can be cached and controlled.

The target deployment machine is the current Apple Silicon Mac. For this spike's recommendation, "local" means runnable on this Mac through local Blender, PyTorch MPS/CPU fallback where needed, and the pinned Blender MCP listener. CUDA/NVIDIA-only paths are disqualified from the v1 recommendation even if they are locally self-hostable on different hardware.

Existing repo state already gives this spike a narrow implementation landing zone:

- `.mcp.json` pins `blender-mcp@1.5.6`, VibeUE through `mcp-remote@0.1.38`, and `meshy-mcp-server@1.2.3`.
- `src/nmg_game_dev/pipeline/` already composes `generate -> texture -> cleanup -> variants -> quality -> import_ue`.
- `src/nmg_game_dev/pipeline/stages/texture.py` is intentionally a `texture.not_implemented` placeholder that points at #5.
- The pipeline uses stage-as-Protocol callables, `StageArtifact` sidecars, and a content-addressed cache, which are the right primitives for local generation jobs and later visual review.
- The Blender add-on currently contains operator stubs and an `mcp_server/` integration seam, not a second MCP host.

## Decision Drivers

- Local-first and API-optional: no primary dependency on paid credits, SaaS uptime, daily quotas, or hardware that is not this Mac.
- Blender remains the authoring surface. External models may generate source artifacts, but Blender owns cleanup, variants, inspection, and export.
- Meshy parity means capability parity where honest, not cloning Meshy's implementation model.
- Asset-producing work must remain idempotent, resumable, cacheable, and quality-gated.
- Desktop and Mobile variants must be produced as separate physical assets from the first real implementation.
- v1 should prefer independently deliverable child issues over one broad parity PR.

## Candidate Set

- Status quo: keep Meshy as the practical generation supplement and do not claim Blender parity yet.
- Hunyuan3D-2.1 self-hosted generation, with Hunyuan3D-Paint evaluated separately because its upstream PBR texture synthesis path is CUDA-first.
- TRELLIS self-hosted 3D generation.
- TripoSR and InstantMesh image-to-3D reconstruction behind a local text-to-image stage.
- ComfyUI or Hugging Face Diffusers as a local texture and image-generation backend.
- Material Maker or similar procedural/open PBR tooling for non-AI materials.
- Blender-native remesh, decimate, baking, LOD, glTF export, and Rigify.
- Meshy, Hyper3D, Substance, and Mixamo as non-core references or fallbacks.

## Findings

### Status Quo / No Change

Keeping Meshy as the only practical supplement would be the lowest implementation risk, but it violates the added product constraint. Meshy's own API docs show credit-based pricing and failure modes for payment required and rate limiting. It is still useful as a benchmark and optional fallback, especially because it exposes text-to-3D, refine/PBR, remesh, rigging, and animation endpoints. It should not be the primary v1 dependency.

Assessment: fallback required, not primary.

Sources:

- https://docs.meshy.ai/en/api/text-to-3d
- https://docs.meshy.ai/en/api/remesh
- https://docs.meshy.ai/en/api/rigging
- https://docs.meshy.ai/en/api/pricing

### Hunyuan3D-2.1

Hunyuan3D-2.1 is the strongest local-first candidate for mesh plus PBR material generation. Tencent's repo describes it as an open-source 3D asset creation system with released model weights, training code, and PBR texture synthesis. Its model zoo calls out separate shape and paint models and gives concrete local resource expectations: roughly 10 GB VRAM for shape generation, 21 GB for texture generation, and 29 GB for combined shape plus texture generation.

Local follow-up testing on the target M-series development machine proved the shape path works locally through PyTorch MPS without Ollama, Meshy, or a hosted generation API. The full-quality image-to-shape run used `tencent/Hunyuan3D-2.1` with 50 inference steps, octree resolution 384, and 8000 chunks. It completed in roughly 22m08s wall time, peaked at about 34.6 GB memory footprint, and produced `/private/tmp/hunyuan3d-smoke/output/hunyuan3d_shape_full_50s_384o_8000c.glb`. Trimesh validation reported one watertight component with 346,836 vertices and 693,672 faces. Blender import/render proof succeeded through the local Blender path and produced `/private/tmp/hunyuan3d-smoke/output/hunyuan3d_shape_full_review.png`.

The remaining gap is productization and texture/PBR, not basic local feasibility. nmg-game-dev still needs a local job wrapper, hardware probing, output normalization, cache integration, Blender-side import/review, and efficient-setting benchmarks. The Hunyuan texture/PBR path is not a Mac-local default as-is. The upstream paint README recommends at least 21 GB VRAM for `max_num_view=6` and `resolution=512`, the repository installation path is tested against PyTorch `cu124`, the paint config hardcodes `self.device = "cuda"`, the multiview pipeline sends tensors to `"cuda"`, the attention processor contains hardcoded `"cuda:0"`/`"cuda:1"` device routing, and the custom rasterizer is built as a `CUDAExtension`. A local build probe for `hy3dpaint/custom_rasterizer` failed immediately on this Mac with `CUDA_HOME environment variable is not set`.

Assessment: preferred local image-to-shape baseline for v1. Implement after adding local job orchestration, with hardware capability detection, efficient-quality presets, and explicit texture-stage fallback behavior. Treat Hunyuan3D-Paint as disqualified for v1 unless a Mac-compatible port is proven on this machine.

Sources:

- https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1

### TRELLIS

TRELLIS is a strong research-grade candidate for high-quality 3D assets from text or image prompts, including mesh output and local editing concepts. It is useful as a comparison path and possible future backend. For v1, it appears less directly aligned than Hunyuan3D-2.1 because the immediate repo gap is PBR-ready asset production through Blender and a concrete texture stage, not a broad model bake-off.

Local follow-up testing used the Apple Silicon TRELLIS.2 port rather than the CUDA-first official repository. The unmodified port loads `briaai/RMBG-2.0` for background removal, which is non-commercial and therefore not acceptable as a default production dependency. A local-only patch added `TRELLIS_SKIP_REMBG=1` so TRELLIS.2 skips BRIA when the input is already an RGBA cutout. The Hunyuan demo fixture is such a cutout, so the no-BRIA path proved that BRIA is optional for pre-masked inputs.

The no-BRIA TRELLIS.2 run completed end-to-end locally with `pipeline-type=512`, 1024 texture size, and the same Hunyuan demo input. It emitted `/private/tmp/trellis2-mac-smoke/output/trellis2_hunyuan_demo_512_no_bria_pbr.glb` and `.obj`. Total wall time was 471.37s, pipeline load was 152s, generation was 248.3s, bake time was 49s, and peak memory footprint was about 20.6 GB. The Metal PBR bake failed on this Mac target with an unsupported float atomic operation, then the KDTree texture baker fallback completed. The exported GLB had one geometry with 192,878 vertices and 199,999 faces, but it was not watertight. Blender render proof produced `/private/tmp/trellis2-mac-smoke/output/trellis2_hunyuan_demo_512_no_bria_review.png`; visual quality was materially worse than Hunyuan, with noisy geometry, visible holes, and speckled/fragmented texture.

TRELLIS.2 still depends on `facebook/dinov3-vitl16-pretrain-lvd1689m`, which is gated and custom-licensed, even when BRIA is skipped. That requires legal/license review before any generated-output default could ship.

Assessment: technically runs locally with BRIA removed for RGBA inputs, but not quality-viable as the v1 default on this Mac. Keep as a research reference; do not make it the primary backend unless a later model/configuration materially improves output quality and license posture.

Sources:

- https://microsoft.github.io/TRELLIS/
- https://github.com/microsoft/TRELLIS
- https://github.com/microsoft/TRELLIS.2
- https://github.com/shivampkumar/trellis-mac

### TripoSR and InstantMesh

TripoSR and InstantMesh are useful local reconstruction backends when nmg-game-dev can first produce or receive a reference image. TripoSR is attractive for speed and low inference budget. InstantMesh is useful for feed-forward single-image mesh generation and has an Apache-2.0 implementation. Neither solves text-to-3D plus PBR texture output alone.

These should become optional local backends behind the same generation job interface, especially for props where a local text-to-image preview can drive reconstruction. They should not block the first Hunyuan3D path.

Assessment: ready as optional backend issue after the shared generation job contract exists.

Sources:

- https://stability.ai/news/triposr-3d-generation
- https://huggingface.co/stabilityai/TripoSR
- https://github.com/TencentARC/InstantMesh

### ComfyUI / Diffusers / Material Maker

The texture stage should be local-first. ComfyUI provides a local graph/node workflow and backend on Windows, Linux, and macOS. Diffusers provides local image-to-image and ControlNet-style controlled generation APIs, useful for generating or retexturing 2D texture maps from renders, UV previews, depth maps, and normal/canny controls. Material Maker is an open-source procedural PBR authoring tool that can export materials for game engines and is useful for deterministic, non-AI material generation.

The gap is PBR channel discipline. Generic image diffusion produces images, not guaranteed game-ready base color, normal, roughness, metallic, and AO maps. ComfyUI/Diffusers/Material Maker should cover Mac-local texture generation, retexture experiments, and procedural material fallback under a strict output contract.

The v1 texture strategy should separate "PBR-compliant asset packaging" from "AI-generated high-quality texture synthesis." Blender and glTF can give nmg-game-dev the first part locally: UVs, material slots, base color, metallic, roughness, normal, AO/emissive channels where available, texture bake-down, and GLB export. Blender's render baking supports baking base color/normal/AO/procedural results to image textures, and Blender's glTF exporter supports core metal/rough PBR materials and recognized image texture nodes. That is enough to make local assets engine-importable and materially disciplined even when texture art is procedural or simple.

AI texture generation should be staged behind quality gates. For Mac-local v1, use deterministic Blender/Material Maker procedural PBR presets and reference-image projection/baking experiments for stylized props. Use ComfyUI/Diffusers only for explicit texture/retexture experiments that emit the required channel manifest and review renders. Do not claim Meshy-quality PBR from this path until a benchmark shows coherent base color, normal, metallic, roughness, and AO maps on the target asset categories.

The Mac-local PBR packaging path was exercised through the already-running Blender MCP listener on `127.0.0.1:9876`, using `/Volumes/Fast Brick/Applications/Blender.app/Contents/MacOS/Blender` 5.1.1. The test imported the mid-quality Hunyuan chest GLB, created a UV layer with Blender smart projection, assigned three procedural/stylized PBR materials for wood, brass, and dark trim, packed generated texture images, exported a GLB, and rendered a review PNG. It completed in 8.578s inside Blender and produced `/private/tmp/hunyuan3d-smoke/output/pbr_package_flux_chest/flux_chest_pbr_packaged.glb` and `/private/tmp/hunyuan3d-smoke/output/pbr_package_flux_chest/flux_chest_pbr_packaged_review.png`. The exported GLB is 46 MB, contains 3 materials, 9 textures, 9 images, and 1 mesh; glTF inspection confirmed base-color, metallic-roughness, and normal texture bindings for each material.

Hunyuan3D-Paint is out of scope for v1 unless a Mac-compatible port is separately proven on this exact machine. A CUDA-capable machine should not be part of the recommendation because nmg-game-dev will only use this Mac for this path.

Assessment: ready for a local texture backend issue, but scope it as `Blender PBR packaging + procedural material fallback` first. The Mac-local happy path can be PBR-compliant in v1; full AI PBR texture quality remains unproven.

Sources:

- https://github.com/Comfy-Org/ComfyUI
- https://huggingface.co/docs/diffusers/main/using-diffusers/img2img
- https://github.com/huggingface/diffusers/blob/main/docs/source/en/using-diffusers/controlnet.md
- https://www.materialmaker.org/
- https://docs.blender.org/manual/en/dev/render/cycles/baking.html
- https://docs.blender.org/manual/en/4.0/addons/import_export/scene_gltf2.html

### Local Text-to-Image for Prompt-Only Generation

Prompt-only generation still needs a local text-to-image stage before Hunyuan-style image-to-3D. FLUX.1-schnell is the strongest candidate tested so far because its model card lists Apache-2.0 licensing and explicitly allows personal, scientific, and commercial use. It also supports Diffusers and local ComfyUI workflows.

Local FLUX.1-schnell testing on the target Mac completed through Diffusers and MPS. The cold run used a game-prop prompt for a stylized treasure chest, 512x512 output, 4 inference steps, and `torch.bfloat16`. It downloaded the model, loaded in 252.5s, moved to MPS in 87.0s, generated in 367.3s, and took 712.26s wall time overall with about 37.3 GB peak memory footprint. The output `/private/tmp/text2image-smoke/output/flux_schnell_treasure_chest_512.png` was visually useful as an image-to-3D reference: centered, single object, clean white background, and game-prop styling. It still produced a small signature/text artifact, so the stage needs stricter prompting, postprocessing, or rejection gates.

The same output was converted locally to an RGBA cutout with `rembg`/`u2netp` in 3.89s and about 434 MB peak memory footprint. The cutout was then fed into Hunyuan3D-2.1 at smoke settings: 5 inference steps, octree resolution 96, and 3000 chunks. That text-to-image-to-3D chain completed in 99.53s wall time for the Hunyuan step, generated in 67.2s after load, peaked at about 25.9 GB memory footprint, and produced `/private/tmp/hunyuan3d-smoke/output/hunyuan3d_shape_from_flux_chest_smoke.glb`. The smoke mesh was watertight with 26,978 vertices and 53,952 faces. This proves local wiring, not final quality.

The same cutout was then tested with a more useful mid-quality Hunyuan setting: 20 inference steps, octree resolution 256, and 8000 chunks. This completed locally in 462.49s wall time, with 21.9s model load, 433.1s generation time, and about 29.2 GB peak memory footprint. It produced `/private/tmp/hunyuan3d-smoke/output/hunyuan3d_shape_from_flux_chest_20s_256o_8000c.glb`, a 7.3 MB watertight mesh with 212,006 vertices and 424,008 faces. Blender render proof produced `/private/tmp/hunyuan3d-smoke/output/hunyuan3d_shape_from_flux_chest_20s_256o_8000c_review.png`.

The visual result is strong enough to validate the architecture direction: the generated mesh has a recognizable treasure-chest silhouette, readable straps, rivets, and lid curvature, and it is materially better than the TRELLIS.2 Mac output. It is not game-ready without cleanup. The front emblem is softened and partially collapsed, the FLUX signature/text artifact appears as a small underside geometry artifact, and the 2D shadow/base plane was reconstructed into unwanted mesh. The text-to-image stage therefore needs artifact rejection, signature/text removal, shadow/base-plane suppression, and likely crop/mask cleanup before Hunyuan. Blender cleanup must still remove stray geometry, decimate/retopologize, and produce texture/material outputs.

Stable Diffusion XL was also tried as an executable baseline. It downloaded and ran locally through Diffusers/MPS, but the local run emitted a 1.8 KB output with VAE/numeric warnings, so it is not currently a useful Mac baseline without further tuning. Its model card uses OpenRAIL++ rather than the cleaner Apache-2.0 posture of FLUX.1-schnell.

Assessment: FLUX.1-schnell plus cutout/postprocess plus Hunyuan3D-2.1 is now the preferred local prompt-to-shape architecture. It is viable as an implementation direction, but not yet production quality or latency. The next issue should treat text-to-image cleanup and Blender post-generation cleanup as first-class stages, not optional polish. Keep SDXL as a fallback research path only if FLUX proves too slow or memory-heavy for production presets.

Sources:

- https://huggingface.co/black-forest-labs/FLUX.1-schnell
- https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0
- https://pypi.org/project/rembg/

### Blender Remesh, LOD, Baking, and Export

Blender already supplies core local operations needed for cleanup and game delivery. The Decimate modifier reduces face counts, Remesh generates new topology, Rigify is bundled for automatic rigging from building-block components, and the glTF exporter supports meshes, textures, skinning, and animation export. These are not Meshy-equivalent magic, but they are scriptable, local, cacheable, and fit the repo's Blender-first architecture.

The implementation gap is a deterministic operator layer around these tools: target budgets, desktop/mobile split, LOD chain construction, texture bake-down, output sidecars, and visual review artifacts.

Assessment: ready for implementation issues.

Sources:

- https://docs.blender.org/manual/en/4.0/modeling/modifiers/generate/decimate.html
- https://docs.blender.org/manual/en/3.6/modeling/modifiers/generate/remesh.html
- https://docs.blender.org/manual/en/latest/addons/rigging/rigify/index.html
- https://docs.blender.org/manual/en/4.2/addons/import_export/scene_gltf2.html

### Rigging and Animation

Humanoid rigging can start with Blender Rigify and optional Mixamo reference workflows. Mixamo is free for many Adobe ID users, but it is still an external web service, is not available in every account/country setup, stores only the last used character, and is limited to bipedal humanoids. Meshy's rigging API has similar humanoid-only caveats and is credit-based. Neither should be a primary automated dependency.

The honest v1 path is:

- Rigify-driven biped setup in Blender for humanoids.
- Strict "fallback required" status for quadrupeds, non-biped characters, props with deformable parts, and text-driven custom motion.
- Import/retarget prepared animation libraries locally rather than promising text-to-animation generation.

Assessment: ready for a constrained humanoid rigging issue; follow-up spike required for quadruped/non-biped auto-rigging and text-driven custom motion.

Sources:

- https://docs.blender.org/manual/en/latest/addons/rigging/rigify/index.html
- https://helpx.adobe.com/creative-cloud/faq/mixamo-faq.html
- https://helpx.adobe.com/creative-cloud/help/mixamo-rigging-animation.html
- https://docs.meshy.ai/en/api/rigging

### Blender MCP and Orchestration

The pinned Blender MCP can execute Python in Blender, inspect scenes, manipulate objects, apply materials, download Poly Haven assets, and integrate AI generation providers such as Hunyuan3D/Hyper3D depending on version. Its README warns that Hyper3D's free trial has daily limits. That is another reason not to make provider-backed MCP generation the core dependency.

The repo should use Blender MCP primarily as a control plane for local Blender operations and nmg-game-dev operators, not as a hidden dependency on paid provider APIs. Generation jobs should be represented in nmg-game-dev code with explicit backend names, cache keys, progress, cancellation, artifact paths, and source provenance.

Assessment: ready for shared orchestration primitive issue.

Sources:

- https://github.com/ahujasid/blender-mcp
- https://pypi.org/project/blender-mcp/

## Honest Gaps

- This spike proved Hunyuan3D-2.1 shape generation locally, but did not benchmark efficient Hunyuan presets, Hunyuan3D-2mini, or turbo variants against the full-quality baseline.
- This spike ruled out Hunyuan3D-Paint as the Mac-local v1 default without porting: the upstream paint path hardcodes CUDA in config/model code and requires a CUDAExtension rasterizer that does not build on this Mac.
- This spike proved TRELLIS.2 Mac can run without BRIA on RGBA inputs, but the measured output was not quality-viable and its DINOv3 dependency still needs license review.
- This spike did not benchmark TripoSR, InstantMesh, SPAR3D/Stable Fast 3D, or other local image-to-3D candidates against the Hunyuan baseline.
- This spike proved a local text-to-image-to-3D chain using FLUX.1-schnell, rembg/u2netp, and Hunyuan3D-2.1 at smoke and mid-quality settings, but did not prove production-quality prompt-only generation, AI-generated PBR texture output, or acceptable latency.
- This spike did not identify a credible local solution for quadruped or non-biped auto-rigging.
- This spike did not identify a credible local solution for text-driven custom motion.
- This spike did not define an artist-facing review UI beyond the need for turntable renders, material-ball renders, screenshots, and sidecar reports.
- This spike proved Blender-side import/render review for generated GLBs, but did not validate whether the pinned `blender-mcp@1.5.6` Hunyuan helper path is adequate; nmg-game-dev likely should invoke Hunyuan directly through its own local backend wrapper and use Blender MCP for review/cleanup.
- This spike did not resolve model license review for every candidate model weight and dependency; child issues must include license review before shipping generated-output defaults.

## Recommendation

Proceed with ADR plus an implementation umbrella. The v1 direction should be local-first Blender parity, not Meshy replacement through another paid API.

Recommended architecture:

1. Add shared local job orchestration primitives first: job submit/poll/cancel, progress events, cache keys, artifact manifests, backend provenance, and review artifacts.
2. Implement Hunyuan3D-2.1 as the preferred local image-to-shape backend behind the existing `Stage` Protocol shape, with efficient-quality presets and Blender review artifacts.
3. Select and implement a local text-to-image stage that can create clean, asset-style RGBA or maskable reference images for prompt-only generation.
4. Implement a local texture backend as Blender-owned PBR packaging first: UV unwrap, material-slot assignment, procedural/stylized PBR presets, texture bake-down, GLB channel validation, and review renders. Exclude Hunyuan3D-Paint from v1 unless a Mac-compatible port is proven on this machine; keep ComfyUI/Diffusers as gated texture/retexture experiments until they prove channel-correct output locally on this Mac.
5. Implement Blender-native cleanup, remesh, LOD, texture bake-down, and Desktop/Mobile variant operators.
6. Implement constrained humanoid rigging and animation import through Blender/Rigify and local animation-library retargeting.
7. Implement asset review outputs and quality gates so every asset-producing skill ends with inspectable proof, not trust.

Meshy, Hyper3D, Substance, and Mixamo remain allowed only as:

- reference outputs for comparison,
- explicit user-selected fallback paths,
- manual production escape hatches,
- or temporary gaps recorded in issue bodies and review reports.

They must not be required for the happy path of `$new-prop`, `$new-character`, `$generate-texture`, or consumer onboarding.

## Decomposition

- component-count: 7
- components:
  - Local generation job orchestration: add job lifecycle, progress, cancellation, cache provenance, artifact manifest, and backend capability probing.
  - Hunyuan3D local generation backend: wire self-hosted Hunyuan3D-2.1 into the pipeline generate boundary with hardware detection, efficient-quality presets, and Meshy-reference comparison only.
  - Local text-to-image backend: select and wire a commercial-safe local model path that turns asset prompts into clean RGBA or maskable reference images for Hunyuan-style image-to-3D.
  - Local texture and retexture backend: implement the `texture` stage with Blender-owned PBR material packaging, UV unwrap, bake-down, GLB channel validation, deterministic procedural/stylized PBR presets, and Mac-local ComfyUI/Diffusers experiments only after channel-correct output is proven.
  - Blender cleanup, remesh, LOD, and variant operators: produce deterministic Desktop/Mobile assets with sidecars for quality gates.
  - Humanoid rigging and animation import: support Rigify-based humanoid rigs and local animation-library retargeting while marking non-biped/custom motion as gaps.
  - Asset inspection and review gates: produce turntables, material-ball renders, diff screenshots, budget reports, and an `inspect-artifact`/asset-reviewer surface.

## Consequences

### Positive

- The core path is controllable, cacheable, and not exposed to paid credit burn or third-party rate limits.
- Meshy parity becomes an honest quality target rather than a hidden dependency.
- The existing pipeline architecture can absorb the work without replacing the stage runner.
- Child issues can be implemented and validated independently.

### Negative

- Local inference raises hardware, install, and model-management complexity.
- Hunyuan3D-class generation may exceed some developer machines' practical limits.
- v1 will still need explicit fallback language for non-biped rigging and text-driven custom motion.
- Quality may initially trail Meshy on some categories until prompts, models, and review gates mature.

## Scope Decision

Choose **ADR + umbrella + child implementation issues** at the Phase 0 Human Review Gate.

The ADR should ship in the issue #5 PR. The implementation tracker is umbrella issue #27 with child issues created from the decomposition above. Each child carries `Depends on: #27` so the SDLC pipeline treats the umbrella as coordination rather than a shipping change.

Created tracker:

- #27: Umbrella: deliver local-first Blender-as-Meshy parity
- #31: Add local generation job orchestration
- #34: Add local text-to-image backend
- #28: Wire Hunyuan3D local generation backend
- #29: Implement local texture and retexture backend
- #33: Build Blender cleanup remesh LOD and variant operators
- #32: Support humanoid rigging and animation import
- #30: Add asset inspection and review gates

## References

- Issue #5: https://github.com/Nunley-Media-Group/nmg-game-dev/issues/5
- Umbrella issue #27: https://github.com/Nunley-Media-Group/nmg-game-dev/issues/27
- Product steering: `steering/product.md`
- Technical steering: `steering/tech.md`
- Structure steering: `steering/structure.md`
- Pipeline core spec: `specs/feature-pipeline-composition-core-variant-aware-stage-runner/`
- Blender add-on spec: `specs/feature-blender-add-on-skeleton-blender-mcp-wiring/`
- Hunyuan3D-2.1: https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1
- TRELLIS: https://github.com/microsoft/TRELLIS
- TripoSR: https://huggingface.co/stabilityai/TripoSR
- InstantMesh: https://github.com/TencentARC/InstantMesh
- ComfyUI: https://github.com/Comfy-Org/ComfyUI
- Diffusers image-to-image: https://huggingface.co/docs/diffusers/main/using-diffusers/img2img
- Diffusers ControlNet: https://github.com/huggingface/diffusers/blob/main/docs/source/en/using-diffusers/controlnet.md
- FLUX.1-schnell: https://huggingface.co/black-forest-labs/FLUX.1-schnell
- Stable Diffusion XL: https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0
- rembg: https://pypi.org/project/rembg/
- Material Maker: https://www.materialmaker.org/
- Blender render baking: https://docs.blender.org/manual/en/dev/render/cycles/baking.html
- Blender Decimate: https://docs.blender.org/manual/en/4.0/modeling/modifiers/generate/decimate.html
- Blender Remesh: https://docs.blender.org/manual/en/3.6/modeling/modifiers/generate/remesh.html
- Blender Rigify: https://docs.blender.org/manual/en/latest/addons/rigging/rigify/index.html
- Blender glTF exporter: https://docs.blender.org/manual/en/4.2/addons/import_export/scene_gltf2.html
- Blender MCP: https://github.com/ahujasid/blender-mcp
- Meshy API docs: https://docs.meshy.ai/en/api/text-to-3d
- Meshy pricing: https://docs.meshy.ai/en/api/pricing
- Adobe Mixamo FAQ: https://helpx.adobe.com/creative-cloud/faq/mixamo-faq.html
