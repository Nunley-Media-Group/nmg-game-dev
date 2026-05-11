# ADR: Blender-as-Meshy Gap Analysis

**Issues**: #5
**Date**: 2026-05-02
**Status**: Accepted
**Decision Type**: Spike gap analysis

---

## Context

nmg-game-dev is Blender-first by product direction, and this spike concludes that Blender MCP recipe generation is the v1 asset-creation path. Meshy and model-backed tools are retained only as historical benchmarks, not implementation dependencies. Issue #5 asks whether Blender can become the primary Meshy-parity authoring surface for text-to-3D asset creation, PBR texture generation, retexturing, remesh/topology, LOD generation, rigging, and animation.

The final operating constraint is stricter than "local-first": v1 asset generation must use Blender MCP and deterministic procedural reasoning as the happy path. Paid APIs, hosted generation providers, and local specialized model servers are not implementation dependencies for asset creation. They remain historical benchmark evidence only.

For this spike's recommendation, "local" means local Blender plus the pinned Blender MCP listener. PyTorch/MPS, CUDA/NVIDIA, and other model-runtime paths are not part of the v1 asset-generation recommendation even if they are technically runnable on some machines.

Existing repo state already gives this spike a narrow implementation landing zone:

- `.mcp.json` pins `blender-mcp@1.5.6`, VibeUE through `mcp-remote@0.1.38`, and `meshy-mcp-server@1.2.3`.
- `src/nmg_game_dev/pipeline/` already composes `generate -> texture -> cleanup -> variants -> quality -> import_ue`.
- `src/nmg_game_dev/pipeline/stages/texture.py` is intentionally a `texture.not_implemented` placeholder that points at #5.
- The pipeline uses stage-as-Protocol callables, `StageArtifact` sidecars, and a content-addressed cache, which are the right primitives for local generation jobs and later visual review.
- The Blender add-on currently contains operator stubs and an `mcp_server/` integration seam, not a second MCP host.

## Decision Drivers

- Blender MCP-only happy path: no primary dependency on paid credits, SaaS uptime, daily quotas, local specialized model servers, or hardware outside local Blender.
- Blender is the generation and authoring surface. Assets are created by typed procedural recipes, Blender geometry builders, material/motif libraries, cleanup, variants, inspection, and export.
- Meshy parity means capability parity where honest, not cloning Meshy's implementation model.
- Asset-producing work must remain idempotent, resumable, cacheable, and quality-gated.
- Desktop and Mobile variants must be produced as separate physical assets from the first real implementation.
- v1 should prefer independently deliverable child issues over one broad parity PR.

## Candidate Set

- Status quo: keep Meshy as the practical generation supplement and do not claim Blender parity yet.
- Direct Blender MCP recipe-driven procedural asset authoring for all supported asset families.
- Blender-native procedural materials, geometry nodes/Python mesh construction, remesh, decimate, baking, LOD, glTF export, and Rigify.
- Hunyuan3D, TRELLIS, TripoSR, InstantMesh, FLUX, ComfyUI, Diffusers, Meshy, Hyper3D, Substance, Material Maker, and Mixamo as evaluated-but-rejected implementation dependencies. Their outputs may inform benchmarks, but they are not active v1 backends.

## Findings

### Status Quo / No Change

Keeping Meshy as the practical generation supplement would be the lowest implementation risk, but it violates the final product constraint. Meshy's own API docs show credit-based pricing and failure modes for payment required and rate limiting. It is still useful as a benchmark because it exposes text-to-3D, refine/PBR, remesh, rigging, and animation endpoints. It should not be a v1 dependency or fallback backend.

Assessment: benchmark/reference only, not an implementation dependency.

Sources:

- https://docs.meshy.ai/en/api/text-to-3d
- https://docs.meshy.ai/en/api/remesh
- https://docs.meshy.ai/en/api/rigging
- https://docs.meshy.ai/en/api/pricing

### Hunyuan3D-2.1

Hunyuan3D-2.1 is the strongest local-first candidate for mesh plus PBR material generation. Tencent's repo describes it as an open-source 3D asset creation system with released model weights, training code, and PBR texture synthesis. Its model zoo calls out separate shape and paint models and gives concrete local resource expectations: roughly 10 GB VRAM for shape generation, 21 GB for texture generation, and 29 GB for combined shape plus texture generation.

Local follow-up testing on the target M-series development machine proved the shape path works locally through PyTorch MPS without Ollama, Meshy, or a hosted generation API. The full-quality image-to-shape run used `tencent/Hunyuan3D-2.1` with 50 inference steps, octree resolution 384, and 8000 chunks. It completed in roughly 22m08s wall time, peaked at about 34.6 GB memory footprint, and produced spike evidence artifacts `hunyuan3d_shape_full_50s_384o_8000c.glb` and `hunyuan3d_shape_full_review.png`. Trimesh validation reported one watertight component with 346,836 vertices and 693,672 faces.

The remaining gap is productization and texture/PBR, not basic local feasibility. nmg-game-dev still needs a local job wrapper, hardware probing, output normalization, cache integration, Blender-side import/review, and efficient-setting benchmarks. The Hunyuan texture/PBR path is not a Mac-local default as-is. The upstream paint README recommends at least 21 GB VRAM for `max_num_view=6` and `resolution=512`, the repository installation path is tested against PyTorch `cu124`, the paint config hardcodes `self.device = "cuda"`, the multiview pipeline sends tensors to `"cuda"`, the attention processor contains hardcoded `"cuda:0"`/`"cuda:1"` device routing, and the custom rasterizer is built as a `CUDAExtension`. A local build probe for `hy3dpaint/custom_rasterizer` failed immediately on this Mac with `CUDA_HOME environment variable is not set`.

Assessment: technically useful evidence, but rejected as a v1 implementation dependency. The path requires a local specialized model stack, heavy memory, model management, and a separate texture solution. No Hunyuan child implementation should remain active for the Blender MCP-only solution.

Sources:

- https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1

### TRELLIS

TRELLIS is a strong research-grade candidate for high-quality 3D assets from text or image prompts, including mesh output and local editing concepts. It is useful as a comparison path and possible future backend. For v1, it appears less directly aligned than Hunyuan3D-2.1 because the immediate repo gap is PBR-ready asset production through Blender and a concrete texture stage, not a broad model bake-off.

Local follow-up testing used the Apple Silicon TRELLIS.2 port rather than the CUDA-first official repository. The unmodified port loads `briaai/RMBG-2.0` for background removal, which is non-commercial and therefore not acceptable as a default production dependency. A local-only patch added `TRELLIS_SKIP_REMBG=1` so TRELLIS.2 skips BRIA when the input is already an RGBA cutout. The Hunyuan demo fixture is such a cutout, so the no-BRIA path proved that BRIA is optional for pre-masked inputs.

The no-BRIA TRELLIS.2 run completed end-to-end locally with `pipeline-type=512`, 1024 texture size, and the same Hunyuan demo input. It emitted spike evidence artifacts `trellis2_hunyuan_demo_512_no_bria_pbr.glb`, `trellis2_hunyuan_demo_512_no_bria_pbr.obj`, and `trellis2_hunyuan_demo_512_no_bria_review.png`. Total wall time was 471.37s, pipeline load was 152s, generation was 248.3s, bake time was 49s, and peak memory footprint was about 20.6 GB. The Metal PBR bake failed on this Mac target with an unsupported float atomic operation, then the KDTree texture baker fallback completed. The exported GLB had one geometry with 192,878 vertices and 199,999 faces, but it was not watertight. Visual quality was materially worse than Hunyuan, with noisy geometry, visible holes, and speckled/fragmented texture.

TRELLIS.2 still depends on `facebook/dinov3-vitl16-pretrain-lvd1689m`, which is gated and custom-licensed, even when BRIA is skipped. That requires legal/license review before any generated-output default could ship.

Assessment: technically runs locally with BRIA removed for RGBA inputs, but not quality-viable as the v1 default on this Mac. Keep as a research reference; do not make it the primary backend unless a later model/configuration materially improves output quality and license posture.

Sources:

- https://microsoft.github.io/TRELLIS/
- https://github.com/microsoft/TRELLIS
- https://github.com/microsoft/TRELLIS.2
- https://github.com/shivampkumar/trellis-mac

### TripoSR and InstantMesh

TripoSR and InstantMesh are useful local reconstruction backends when nmg-game-dev can first produce or receive a reference image. TripoSR is attractive for speed and low inference budget. InstantMesh is useful for feed-forward single-image mesh generation and has an Apache-2.0 implementation. Neither solves text-to-3D plus PBR texture output alone.

These remain historical comparison points only. They still require model-backed reconstruction and a reference image stage, so they do not fit the final Blender MCP-only path.

Assessment: rejected as v1 implementation dependencies; benchmark/reference only.

Sources:

- https://stability.ai/news/triposr-3d-generation
- https://huggingface.co/stabilityai/TripoSR
- https://github.com/TencentARC/InstantMesh

### ComfyUI / Diffusers / Material Maker

The texture stage should be Blender MCP-only. ComfyUI and Diffusers were evaluated as possible local model-backed texture paths, and Material Maker was evaluated as an external procedural material reference, but none of them should be required in v1. Blender's own material nodes, UV tools, procedural textures, baking, and glTF export are the implementation surface.

The gap is PBR channel discipline. Generic image diffusion produces images, not guaranteed game-ready base color, normal, roughness, metallic, and AO maps. The Blender recipe engine must cover material generation, retexture-like variation, and procedural material fallback under a strict output contract.

The v1 texture strategy should separate "PBR-compliant asset packaging" from "AI-generated high-quality texture synthesis." Blender and glTF can give nmg-game-dev the first part locally: UVs, material slots, base color, metallic, roughness, normal, AO/emissive channels where available, texture bake-down, and GLB export. Blender's render baking supports baking base color/normal/AO/procedural results to image textures, and Blender's glTF exporter supports core metal/rough PBR materials and recognized image texture nodes. That is enough to make local assets engine-importable and materially disciplined even when texture art is procedural or simple.

Texture generation should be staged behind quality gates. For v1, use deterministic Blender procedural PBR presets and recipe-specific material builders for stylized props and modular characters. Do not introduce ComfyUI, Diffusers, or another local model backend for texture synthesis.

The Mac-local PBR packaging path was exercised through the already-running Blender MCP listener on `127.0.0.1:9876`, using local Blender 5.1.1. The test imported the mid-quality Hunyuan chest GLB, created a UV layer with Blender smart projection, assigned three procedural/stylized PBR materials for wood, brass, and dark trim, packed generated texture images, exported a GLB, and rendered a review PNG. It completed in 8.578s inside Blender and produced spike evidence artifacts `flux_chest_pbr_packaged.glb` and `flux_chest_pbr_packaged_review.png`. The exported GLB is 46 MB, contains 3 materials, 9 textures, 9 images, and 1 mesh; glTF inspection confirmed base-color, metallic-roughness, and normal texture bindings for each material.

Hunyuan3D-Paint is out of scope for v1 unless a Mac-compatible port is separately proven on this exact machine. A CUDA-capable machine should not be part of the recommendation because nmg-game-dev will only use this Mac for this path.

Assessment: ready for a Blender MCP procedural material issue. Scope it as `Blender PBR packaging + procedural material library`; no AI texture backend belongs in v1.

Sources:

- https://github.com/Comfy-Org/ComfyUI
- https://huggingface.co/docs/diffusers/main/using-diffusers/img2img
- https://github.com/huggingface/diffusers/blob/main/docs/source/en/using-diffusers/controlnet.md
- https://www.materialmaker.org/
- https://docs.blender.org/manual/en/4.2/render/cycles/baking.html
- https://docs.blender.org/manual/en/4.2/addons/import_export/scene_gltf2.html

### Local Text-to-Image for Prompt-Only Generation

Prompt-only model-backed generation was evaluated before the Blender MCP recipe path was proven. FLUX.1-schnell was the strongest local text-to-image candidate because its model card lists Apache-2.0 licensing and explicitly allows personal, scientific, and commercial use. It also supports Diffusers and local ComfyUI workflows.

Local FLUX.1-schnell testing on the target Mac completed through Diffusers and MPS. The cold run used a game-prop prompt for a stylized treasure chest, 512x512 output, 4 inference steps, and `torch.bfloat16`. It downloaded the model, loaded in 252.5s, moved to MPS in 87.0s, generated in 367.3s, and took 712.26s wall time overall with about 37.3 GB peak memory footprint. The output evidence artifact `flux_schnell_treasure_chest_512.png` was visually useful as an image-to-3D reference: centered, single object, clean white background, and game-prop styling. It still produced a small signature/text artifact, so the stage needs stricter prompting, postprocessing, or rejection gates.

The same output was converted locally to an RGBA cutout with `rembg`/`u2netp` in 3.89s and about 434 MB peak memory footprint. The cutout was then fed into Hunyuan3D-2.1 at smoke settings: 5 inference steps, octree resolution 96, and 3000 chunks. That text-to-image-to-3D chain completed in 99.53s wall time for the Hunyuan step, generated in 67.2s after load, peaked at about 25.9 GB memory footprint, and produced spike evidence artifact `hunyuan3d_shape_from_flux_chest_smoke.glb`. The smoke mesh was watertight with 26,978 vertices and 53,952 faces. This proves local wiring, not final quality.

The same cutout was then tested with a more useful mid-quality Hunyuan setting: 20 inference steps, octree resolution 256, and 8000 chunks. This completed locally in 462.49s wall time, with 21.9s model load, 433.1s generation time, and about 29.2 GB peak memory footprint. It produced spike evidence artifacts `hunyuan3d_shape_from_flux_chest_20s_256o_8000c.glb` and `hunyuan3d_shape_from_flux_chest_20s_256o_8000c_review.png`; the GLB was a 7.3 MB watertight mesh with 212,006 vertices and 424,008 faces.

The visual result is strong enough to validate the architecture direction: the generated mesh has a recognizable treasure-chest silhouette, readable straps, rivets, and lid curvature, and it is materially better than the TRELLIS.2 Mac output. It is not game-ready without cleanup. The front emblem is softened and partially collapsed, the FLUX signature/text artifact appears as a small underside geometry artifact, and the 2D shadow/base plane was reconstructed into unwanted mesh. The text-to-image stage therefore needs artifact rejection, signature/text removal, shadow/base-plane suppression, and likely crop/mask cleanup before Hunyuan. Blender cleanup must still remove stray geometry, decimate/retopologize, and produce texture/material outputs.

Stable Diffusion XL was also tried as an executable baseline. It downloaded and ran locally through Diffusers/MPS, but the local run emitted a 1.8 KB output with VAE/numeric warnings, so it is not currently a useful Mac baseline without further tuning. Its model card uses OpenRAIL++ rather than the cleaner Apache-2.0 posture of FLUX.1-schnell.

Assessment: useful historical evidence, but rejected as a v1 implementation dependency. The Blender MCP recipe engine removes the need for local text-to-image and image-to-3D model chains for supported assets. Do not keep an active local text-to-image child issue for v1.

Sources:

- https://huggingface.co/black-forest-labs/FLUX.1-schnell
- https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0
- https://pypi.org/project/rembg/

### Blender Remesh, LOD, Baking, and Export

Blender already supplies core local operations needed for cleanup and game delivery. The Decimate modifier reduces face counts, Remesh generates new topology, Rigify is bundled for automatic rigging from building-block components, and the glTF exporter supports meshes, textures, skinning, and animation export. These are not Meshy-equivalent magic, but they are scriptable, local, cacheable, and fit the repo's Blender-first architecture.

The implementation gap is a deterministic operator layer around these tools: target budgets, desktop/mobile split, LOD chain construction, texture bake-down, output sidecars, and visual review artifacts.

Assessment: ready for implementation issues.

Sources:

- https://docs.blender.org/manual/en/4.2/modeling/modifiers/generate/decimate.html
- https://docs.blender.org/manual/en/4.2/modeling/modifiers/generate/remesh.html
- https://docs.blender.org/manual/en/4.2/addons/rigging/rigify/index.html
- https://docs.blender.org/manual/en/4.2/addons/import_export/scene_gltf2.html

### Direct Blender MCP Procedural Asset Authoring

Direct Blender MCP procedural authoring is viable for structured/stylized game props where the target can be decomposed into known primitives, material presets, and reusable motifs. This is not text-to-3D model inference; Codex drives Blender Python through `execute_code` and constructs the asset deterministically inside Blender.

The spike exercised this path through the already-running Blender MCP listener on `127.0.0.1:9876`. The test created a stylized fantasy treasure chest using Blender primitives, bevels, simple material nodes, rivets, trim, lock geometry, feet, orthographic review lighting, GLB export, and a review render. It produced spike evidence artifacts `blender_mcp_procedural_treasure_chest.glb` and `blender_mcp_procedural_treasure_chest_review.png`. The exported asset contained 46 mesh objects, 632 vertices, 408 faces, five materials, and dimensions of roughly 3.1 x 1.8425 x 2.08 Blender units.

The first pass still showed why one-shot prompt-to-code is not enough: the chest was recognizable but crude. The next experiment moved to a more general structured-spec approach: prompt intent was translated into typed asset specs, reusable part functions, material presets, per-asset collections, GLB export, and five-angle render proof (`front`, `right`, `back`, `three_quarter`, `top`). This produced two additional assets:

- `generalized_plasma_pistol.glb` with render proofs `generalized_plasma_pistol_review_*.png`. The asset has 27 mesh objects, 436 vertices, 272 faces, four materials, and a readable sci-fi sidearm silhouette with barrel, grip, trigger guard, energy tube, side windows, and screw/rib detail.
- `generalized_forest_ranger_character.glb` with render proofs `generalized_forest_ranger_character_review_*.png`. The asset has 46 mesh objects, 1,965 vertices, 1,971 faces, seven materials, and a readable humanoid archer/ranger silhouette with hood, cloak, limbs, quiver, arrows, and bow.

Visual assessment: structured procedural parts improved hard-surface object accuracy materially. The plasma pistol is a plausible low-poly game prop and validates the approach for hard-surface props, pickups, weapons, interactables, platforms, doors, signs, and similar typed object families. The character result is not production-accurate: it reads as a humanoid archer mannequin, but anatomy, face quality, clothing shape, pose control, deformation, and character appeal are not sufficient. Blender MCP alone can assemble a character from parts, but accurate generalized character generation needs a separate character grammar with anatomy templates, rig-aware proportions, clothing/hair modules, facial feature templates, and multi-angle critique gates. It is not solved by generic primitives.

The quality pass then moved beyond primitive stacking. Two higher-fidelity Blender-only assets were authored through the same MCP listener:

- `arcane_frost_sword.glb` with render proofs `arcane_frost_sword_review_*.png`. This pass used a custom faceted blade mesh, bevels, layered guard geometry, emissive runes, metal/leather/ice material presets, floating shards, GLB export, and five-angle review. The exported asset had 55 mesh objects, 2,797 vertices, 2,691 faces, six materials, and dimensions of roughly 3.0 x 0.4672 x 6.3772 Blender units.
- `enchanted_mana_potion_v2.glb` with render proofs `enchanted_mana_potion_v2_review_*.png`. This pass replaced stacked primitives with surface-of-revolution bottle and liquid meshes, curved label geometry, explicit cork/twine/hardware parts, transparent/emissive material presets, internal bubbles/crystals, GLB export, and five-angle review. The exported asset had 35 mesh objects, 7,984 vertices, 7,525 faces, nine materials, and dimensions of roughly 1.44 x 1.491 x 2.8962 Blender units.

The potion v2 pass is the first Blender MCP-only result that is credible as a stylized game-prop baseline, and it establishes the path for all generated assets. The important finding is how quality improved: typed asset-family recipes, real mesh constructors, reusable motif libraries, PBR material presets, and multi-angle render critique worked. Generic one-shot "make any object from text" did not.

Assessment: make direct Blender MCP recipe generation the only v1 asset-generation solution. The implementation should not be a prompt-to-code free-for-all; it should be a recipe compiler with typed asset specs, per-family geometry builders, material/motif libraries, GLB export, quality budgets, and mandatory multi-angle review. Every asset request must either map to a supported Blender MCP recipe family, trigger recipe-authoring work for that family, or fail honestly as unsupported. Local specialized models are removed from the implementation plan. Characters are handled through Blender MCP modular archetype recipes until a stronger character grammar proves anatomy, clothing, face, rig, and pose quality.

### Rigging and Animation

Humanoid rigging can start with Blender Rigify and optional Mixamo reference workflows. Mixamo is free for many Adobe ID users, but it is still an external web service, is not available in every account/country setup, stores only the last used character, and is limited to bipedal humanoids. Meshy's rigging API has similar humanoid-only caveats and is credit-based. Neither should be a primary automated dependency.

The honest v1 path is:

- Rigify-driven biped setup in Blender for humanoids.
- Strict unsupported/backlog status for quadrupeds, non-biped characters, props with deformable parts, and text-driven custom motion.
- Import/retarget prepared animation libraries locally rather than promising text-to-animation generation.

Assessment: ready for a constrained humanoid rigging issue; follow-up spike required for quadruped/non-biped auto-rigging and text-driven custom motion.

Sources:

- https://docs.blender.org/manual/en/4.2/addons/rigging/rigify/index.html
- https://helpx.adobe.com/creative-cloud/faq/mixamo-faq.html
- https://helpx.adobe.com/creative-cloud/help/mixamo-rigging-animation.html
- https://docs.meshy.ai/en/api/rigging

### Blender MCP and Orchestration

The pinned Blender MCP can execute Python in Blender, inspect scenes, manipulate objects, apply materials, download Poly Haven assets, and integrate AI generation providers such as Hunyuan3D/Hyper3D depending on version. Its README warns that Hyper3D's free trial has daily limits. That is another reason not to make provider-backed MCP generation the core dependency.

The repo should use Blender MCP primarily as a control plane for local Blender operations and nmg-game-dev operators, not as a hidden dependency on paid provider APIs. Generation jobs should be represented in nmg-game-dev code with explicit backend names, cache keys, progress, cancellation, artifact paths, and source provenance.

Direct provider-backed generation through Blender MCP was tested separately. The running add-on exposed Hyper3D/Rodin and Hunyuan3D generation tools. Both were initially disabled in the Blender MCP panel. Hyper3D could be enabled programmatically with the add-on's built-in free-trial key, but the corrected text-to-asset submission failed with provider response `INSUFFICIENT_BALANCE`. Hunyuan3D through Blender MCP was not tested as a non-local provider because it requires Tencent SecretId/SecretKey for `OFFICIAL_API`; the configured `LOCAL_API` mode points at `http://localhost:8081`, which is the local-model direction already evaluated elsewhere in this spike.

Assessment: ready for shared orchestration primitive issue. Provider-backed Blender MCP generation is not a reliable v1 happy path without project-owned credentials and quota policy; direct procedural Blender MCP authoring is reliable for the asset categories it can express.

Sources:

- https://github.com/ahujasid/blender-mcp
- https://pypi.org/project/blender-mcp/

## Honest Gaps

- This spike proved several local/model-backed paths can run or partially run, but they are explicitly rejected as v1 implementation dependencies after the Blender MCP recipe path produced the best controllable result.
- This spike proved direct Blender MCP procedural authoring can produce credible stylized prop baselines when it uses typed recipes, real mesh constructors, reusable part libraries, material presets, and multi-angle review. The potion v2 pass is the strongest evidence and becomes the implementation model for all supported asset families.
- This spike did not prove accurate generalized character generation through Blender MCP alone. The forest-ranger test read as a humanoid archer but exposed unresolved anatomy, face, clothing, pose, rigging, and appeal gaps.
- This spike did not prove broad arbitrary-prompt generation through Blender MCP alone. It identified the production path: nmg-game-dev must build typed asset DSLs, recipe selection, part libraries, material presets, reference/spec validation, and multi-angle critique loops for every supported asset family.
- This spike could not prove provider-backed Blender MCP generation quality because Hyper3D/Rodin's built-in free-trial key returned `INSUFFICIENT_BALANCE`, and Tencent Hunyuan official API credentials were not configured. Provider-backed MCP generation is not part of v1.
- This spike did not identify a credible local solution for quadruped or non-biped auto-rigging.
- This spike did not identify a credible local solution for text-driven custom motion.
- This spike did not define an artist-facing review UI beyond the need for turntable renders, material-ball renders, screenshots, and sidecar reports.
- This spike proved Blender-side import/render review for generated GLBs, but did not turn the proof scripts into reusable repo code.
- This spike did not define the complete asset-family taxonomy needed to cover every game asset category; that taxonomy becomes implementation work under the recipe engine and recipe library.

## Recommendation

Proceed with ADR plus an implementation umbrella. The v1 direction should be Blender MCP-only recipe generation as the default happy path for supported asset families, not a local specialized-model stack and not Meshy replacement through another paid API.

Recommended architecture:

1. Add Blender MCP job orchestration primitives first: submit/poll/cancel, progress events, cache keys, artifact manifests, recipe provenance, safe listener restart handling, and review artifacts.
2. Implement a direct Blender MCP recipe engine for all supported asset families. The engine accepts typed specs, selects an asset-family builder, emits Blender Python, exports GLB, and records recipe/material provenance.
3. Build the procedural recipe libraries needed by game assets: potion/bottle, melee weapon, firearm/tool, chest/container, key/collectible, sign/UI pickup, platform/door, environmental kit pieces, modular props, and modular biped characters.
4. Implement a Blender-owned material and motif library: metal, wood, leather, glass, liquid, cloth, stone, emissive magic, trim, rivets, labels, straps, ropes, seals, glyphs, decals, and damage/wear motifs.
5. Implement asset review outputs and quality gates so every asset-producing skill ends with five-angle renders, object/material/poly statistics, budget checks, and reject/fix prompts.
6. Implement Blender-native cleanup, remesh, LOD, texture bake-down, and Desktop/Mobile variant operators after recipe generation.
7. Treat unsupported asset requests as recipe-authoring backlog or explicit unsupported failures. Do not route to local specialized models.

Meshy, Hyper3D, Substance, Mixamo, Hunyuan3D, FLUX, TripoSR/InstantMesh, ComfyUI, and Diffusers remain historical benchmark references only. They are not active v1 generation, texture, character, or fallback backends.

Supported `$new-prop`, `$new-character`, `$generate-texture`, and consumer onboarding flows must use Blender MCP recipe generation. Unsupported requests should create recipe-authoring backlog or fail honestly.

## Decomposition

- component-count: 7
- components:
  - Blender MCP job orchestration: add job lifecycle, progress, cancellation, cache provenance, artifact manifest, recipe capability probing, and safe listener restart handling.
  - Procedural recipe engine: compile typed asset specs into deterministic Blender MCP scripts with recipe/material provenance and replayable cache keys.
  - Asset-family recipe library: implement high-quality builders for potion/bottle, weapon, tool, chest/container, key/collectible, sign/UI pickup, platform/door, environmental kit pieces, modular props, and modular biped characters.
  - Material and motif library: implement reusable procedural PBR presets and details for metal, wood, leather, glass, liquid, cloth, stone, emissive magic, trim, rivets, labels, straps, ropes, seals, glyphs, decals, and wear.
  - Blender cleanup, remesh, LOD, and variant operators: produce deterministic Desktop/Mobile assets with sidecars for quality gates.
  - Modular character grammar: support constrained biped archetypes with anatomy templates, clothing/hair modules, face templates, Rigify-ready proportions, and pose validation.
  - Asset inspection and review gates: produce five-angle renders, turntables, material-ball renders, diff screenshots, budget reports, and an `inspect-artifact`/asset-reviewer surface.

## Consequences

### Positive

- The core path is controllable, cacheable, and not exposed to paid credit burn or third-party rate limits.
- Meshy parity becomes an honest quality target rather than a hidden dependency.
- The existing pipeline architecture can absorb the work without replacing the stage runner.
- Child issues can be implemented and validated independently.

### Negative

- Procedural recipe quality is category-by-category; broad coverage requires authoring and maintaining a real recipe, part, material, and motif library.
- Freeform arbitrary prompt coverage becomes recipe coverage work; unsupported assets must not silently degrade into low-quality primitives.
- v1 will still need explicit unsupported/backlog language for non-biped rigging and text-driven custom motion.
- Quality may initially trail Meshy on categories outside the recipe library, especially organic characters, complex clothing, faces, creatures, and highly irregular natural assets.

## Scope Decision

Choose **ADR + umbrella + child implementation issues** at the Phase 0 Human Review Gate.

The ADR should ship in the issue #5 PR. The implementation tracker is umbrella issue #27 with child issues created from the decomposition above. Each child carries `Depends on: #27` so the SDLC pipeline treats the umbrella as coordination rather than a shipping change. After human review of the potion v2 proof, #35 is the primary implementation track and model-backed child issues #28 and #34 are closed as not planned for v1.

Created tracker:

- #27: Umbrella: deliver Blender MCP-only recipe asset generation
- #31: Add Blender MCP recipe job orchestration
- #35: Add Blender MCP recipe asset generation
- #34: Add local text-to-image backend as fallback research — closed as not planned for v1
- #28: Wire Hunyuan3D local generation backend as fallback research — closed as not planned for v1
- #29: Implement Blender procedural material and texture packaging
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
- Blender render baking: https://docs.blender.org/manual/en/4.2/render/cycles/baking.html
- Blender Decimate: https://docs.blender.org/manual/en/4.2/modeling/modifiers/generate/decimate.html
- Blender Remesh: https://docs.blender.org/manual/en/4.2/modeling/modifiers/generate/remesh.html
- Blender Rigify: https://docs.blender.org/manual/en/4.2/addons/rigging/rigify/index.html
- Blender glTF exporter: https://docs.blender.org/manual/en/4.2/addons/import_export/scene_gltf2.html
- Blender MCP: https://github.com/ahujasid/blender-mcp
- Meshy API docs: https://docs.meshy.ai/en/api/text-to-3d
- Meshy pricing: https://docs.meshy.ai/en/api/pricing
- Adobe Mixamo FAQ: https://helpx.adobe.com/creative-cloud/faq/mixamo-faq.html
