# ADR: Blender-as-Meshy Gap Analysis

**Issues**: #5
**Date**: 2026-05-02
**Status**: Draft
**Decision Type**: Spike gap analysis

---

## Context

nmg-game-dev is Blender-first by product direction, with Meshy retained only as a supplement when it is the right production tool. Issue #5 asks whether Blender can become the primary Meshy-parity authoring surface for text-to-3D asset creation, PBR texture generation, retexturing, remesh/topology, LOD generation, rigging, and animation.

The additional operating constraint is that v1 must not rely on paid or heavily rate-limited third-party APIs as the primary path. Paid or rate-limited services may be used as reference outputs, manual escape hatches, or optional fallbacks, but the framework's core happy path must run locally or against free/open tooling that can be cached and controlled.

Existing repo state already gives this spike a narrow implementation landing zone:

- `.mcp.json` pins `blender-mcp@1.5.6`, VibeUE through `mcp-remote@0.1.38`, and `meshy-mcp-server@1.2.3`.
- `src/nmg_game_dev/pipeline/` already composes `generate -> texture -> cleanup -> variants -> quality -> import_ue`.
- `src/nmg_game_dev/pipeline/stages/texture.py` is intentionally a `texture.not_implemented` placeholder that points at #5.
- The pipeline uses stage-as-Protocol callables, `StageArtifact` sidecars, and a content-addressed cache, which are the right primitives for local generation jobs and later visual review.
- The Blender add-on currently contains operator stubs and an `mcp_server/` integration seam, not a second MCP host.

## Decision Drivers

- Local-first and API-optional: no primary dependency on paid credits, SaaS uptime, or daily quotas.
- Blender remains the authoring surface. External models may generate source artifacts, but Blender owns cleanup, variants, inspection, and export.
- Meshy parity means capability parity where honest, not cloning Meshy's implementation model.
- Asset-producing work must remain idempotent, resumable, cacheable, and quality-gated.
- Desktop and Mobile variants must be produced as separate physical assets from the first real implementation.
- v1 should prefer independently deliverable child issues over one broad parity PR.

## Candidate Set

- Status quo: keep Meshy as the practical generation supplement and do not claim Blender parity yet.
- Hunyuan3D-2.1 self-hosted generation and PBR texture synthesis.
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

The gap is not capability in the abstract; the gap is productization for this repo. nmg-game-dev still needs a local job wrapper, hardware probing, output normalization, cache integration, and Blender-side import/review. M-series Mac feasibility and latency were not proven in this spike.

Assessment: ready for an implementation issue as the preferred local generation backend, with hardware capability detection and honest fallback behavior.

Sources:

- https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1

### TRELLIS

TRELLIS is a strong research-grade candidate for high-quality 3D assets from text or image prompts, including mesh output and local editing concepts. It is useful as a comparison path and possible future backend. For v1, it appears less directly aligned than Hunyuan3D-2.1 because the immediate repo gap is PBR-ready asset production through Blender and a concrete texture stage, not a broad model bake-off.

Assessment: follow-up candidate, not v1 primary unless Hunyuan3D proves unusable on target hardware.

Sources:

- https://microsoft.github.io/TRELLIS/
- https://github.com/microsoft/TRELLIS

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

The gap is PBR channel discipline. Generic image diffusion produces images, not guaranteed game-ready base color, normal, roughness, metallic, and AO maps. Hunyuan3D-Paint may cover PBR for generated meshes; ComfyUI/Diffusers/Material Maker should cover texture generation, retexture experiments, and procedural material fallback under a strict output contract.

Assessment: ready for a local texture backend issue.

Sources:

- https://github.com/Comfy-Org/ComfyUI
- https://huggingface.co/docs/diffusers/main/using-diffusers/img2img
- https://github.com/huggingface/diffusers/blob/main/docs/source/en/using-diffusers/controlnet.md
- https://www.materialmaker.org/

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

- This spike did not run Hunyuan3D-2.1 locally on the target M-series development machine, so actual latency, VRAM/RAM behavior, and quality are unproven.
- This spike did not prove that Hunyuan3D-Paint produces consistently acceptable PBR maps for every v1 asset class.
- This spike did not benchmark TRELLIS, TripoSR, or InstantMesh against Meshy on NMG prompts.
- This spike did not prove a reliable local text-to-image-to-3D chain for prompt-only generation when Hunyuan3D is unavailable.
- This spike did not identify a credible local solution for quadruped or non-biped auto-rigging.
- This spike did not identify a credible local solution for text-driven custom motion.
- This spike did not define an artist-facing review UI beyond the need for turntable renders, material-ball renders, screenshots, and sidecar reports.
- This spike did not validate whether the pinned `blender-mcp@1.5.6` Hunyuan path is adequate, or whether nmg-game-dev should invoke Hunyuan directly through its own local backend wrapper.
- This spike did not resolve model license review for every candidate model weight and dependency; child issues must include license review before shipping generated-output defaults.

## Recommendation

Proceed with ADR plus an implementation umbrella. The v1 direction should be local-first Blender parity, not Meshy replacement through another paid API.

Recommended architecture:

1. Add shared local job orchestration primitives first: job submit/poll/cancel, progress events, cache keys, artifact manifests, backend provenance, and review artifacts.
2. Implement Hunyuan3D-2.1 as the preferred local mesh plus PBR backend behind the existing `Stage` Protocol shape.
3. Implement a local texture backend that can use Hunyuan3D-Paint where applicable and ComfyUI/Diffusers/Material Maker for texture/retexture/procedural cases.
4. Implement Blender-native cleanup, remesh, LOD, texture bake-down, and Desktop/Mobile variant operators.
5. Implement constrained humanoid rigging and animation import through Blender/Rigify and local animation-library retargeting.
6. Implement asset review outputs and quality gates so every asset-producing skill ends with inspectable proof, not trust.

Meshy, Hyper3D, Substance, and Mixamo remain allowed only as:

- reference outputs for comparison,
- explicit user-selected fallback paths,
- manual production escape hatches,
- or temporary gaps recorded in issue bodies and review reports.

They must not be required for the happy path of `$new-prop`, `$new-character`, `$generate-texture`, or consumer onboarding.

## Decomposition

- component-count: 6
- components:
  - Local generation job orchestration: add job lifecycle, progress, cancellation, cache provenance, artifact manifest, and backend capability probing.
  - Hunyuan3D local generation backend: wire self-hosted Hunyuan3D-2.1 into the pipeline generate/texture boundary with hardware detection and Meshy-reference comparison only.
  - Local texture and retexture backend: implement the `texture` stage using local Hunyuan3D-Paint, ComfyUI/Diffusers, and procedural PBR fallback outputs.
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

The ADR should ship in the issue #5 PR. Child issues should be created from the decomposition above and should each carry `Depends on: #{umbrella}` so the SDLC pipeline treats the umbrella as coordination rather than a shipping change.

## References

- Issue #5: https://github.com/Nunley-Media-Group/nmg-game-dev/issues/5
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
- Material Maker: https://www.materialmaker.org/
- Blender Decimate: https://docs.blender.org/manual/en/4.0/modeling/modifiers/generate/decimate.html
- Blender Remesh: https://docs.blender.org/manual/en/3.6/modeling/modifiers/generate/remesh.html
- Blender Rigify: https://docs.blender.org/manual/en/latest/addons/rigging/rigify/index.html
- Blender glTF exporter: https://docs.blender.org/manual/en/4.2/addons/import_export/scene_gltf2.html
- Blender MCP: https://github.com/ahujasid/blender-mcp
- Meshy API docs: https://docs.meshy.ai/en/api/text-to-3d
- Meshy pricing: https://docs.meshy.ai/en/api/pricing
- Adobe Mixamo FAQ: https://helpx.adobe.com/creative-cloud/faq/mixamo-faq.html
