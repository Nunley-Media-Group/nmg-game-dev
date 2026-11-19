# Asset contract

What "done" means for any asset generated in Blender for an NMG game. This covers
the deliverable, not how you model it: build it however you like, but what you hand
over must satisfy every rule below. Anything that looks right only in Blender's
viewport or renderer is not done.

## 1. Scene layout

- Each asset lives in its own collection named `<Name>` (PascalCase, e.g. `Lamppost`).
- That collection contains only what ships. Ground planes, lights, cameras, and
  set dressing go in a separate `<Name>_Preview` collection that is never exported.
- A reduce run (`docs/skills/reduce-to-budget.md`, #139) may keep the original meshes of a generated
  asset in a top-level `<Name>_High` collection, hidden in the viewport and in renders, with each
  object named `<object>_High`. `<Name>_High` is never validated, hashed, or exported. Only `<Name>`
  and `<Name>_Mobile` are.
- One root mesh object per variant: `SM_<Name>` (Desktop) and `SM_<Name>_Mobile` (Mobile).
  Split into multiple objects only for parts that must move independently, named
  `SM_<Name>_<Part>`, parented to the root.
- Each part has its own mesh data: no two mesh objects of one variant may share a mesh
  datablock. Validate reports `naming.mesh_data` for a shared one; fix it with Object >
  Relations > Make Single User > Object & Data.
- Export names each mesh datablock after its object (the `_Mobile` suffix removed), so every
  glTF mesh carries the name its object has in Godot.
- When one request produces several assets, each one is a separate deliverable with
  its own collection at the world origin; overlapping in Blender is expected. Don't
  compose scenes in Blender. Placement and level composition happen in Godot.

## 2. Units, orientation, pivot

- Meters, scene unit scale 1.0, real-world size (a door is ~2.1 m tall).
- Z up. The asset's front faces -Y (Blender's Front view looks at it). For assets with
  no natural front (terrain, tracks), the side a player first sees faces -Y.
- Root object origin at the bottom center of the asset (where it meets the ground),
  placed at world origin.
- A rigged asset (its collection holds an armature named `SK_<Name>`) may sit up to 5 mm off
  the world origin on each axis at authoring time, measured at the bottom center. Finalize's
  variants step moves its Desktop mesh data onto the origin, so both exported variants sit
  there. The root origin, static assets, and export-time validation keep the 1 mm tolerance.
  A bottom center more than 5 mm off fails validation: move the mesh data closer (#244).
  Validation, the Desktop re-seat, the reduce copy, and export measure a rigged asset in its rest
  pose, so a pose left on the pose bones does not affect its pivot, bounds, or mesh checks (#236).
- Root object transforms applied: location (0,0,0), rotation (0,0,0), scale (1,1,1).
- Child parts: rotation (0,0,0) and scale (1,1,1), with the origin at the hinge or
  axle and the location wherever that pivot sits relative to the root.
- All modifiers applied before export.
- 1 Blender unit = 1 m = 1 Godot unit. Export converts to Godot's Y-up space: a Blender point
  `(x, y, z)` becomes `(x, z, -y)`, so the asset's origin stays at its base centre and its front
  faces Godot's +Z.

## 3. Geometry

- Closed parts have every face pointing outward. Shading uses custom/auto smoothing,
  not unwanted flat facets.
- Open sheets (floors, roof planes, decals, terrain, ground sheets) are allowed where nothing
  will see underneath. Wind every face of a sheet consistently and make it face the viewer:
  `geometry.normals` checks consistent winding between neighbouring faces, and it never compares
  a sheet with an outside direction, so a sheet passes wherever it sits.
- A closed part must not join itself back with reversed winding through a narrow seam, as a
  Klein-bottle-like surface does. Such a part has no consistent outward direction, so
  `geometry.twist_seam` reports the seam itself, with the number of seam edges and their
  midpoints, instead of `geometry.normals` faces. Finalize cleanup deletes only the faces at
  those seam edges.
- Touching primitives, such as an environment piece built from many boxes, either merge by
  distance so they share vertices, or stay about 0.6 mm apart. Vertices that coincide without
  merging raise `geometry.duplicates`.
- No loose vertices, zero-area faces, or duplicate geometry. Visible interpenetration
  is a defect; hidden interior faces should be removed where practical.
- Triangle counts within the budget for the asset class (section 6).

## 4. UVs and materials

- Every mesh has exactly one UV map, `UVMap`, with roughly even texel density.
- Two texturing modes:
  - **Unique bake** (default for props, vehicles, characters): non-overlapping UVs,
    all materials baked into a texture set for that asset.
  - **Tiling** (large environment pieces and terrain layers): UVs may overlap and extend past 0–1 so
    tiling materials and trim sheets repeat across the surface. Each tiling texture is
    itself seamless: on each axis, the mean absolute difference between the last and first
    pixel (the wrap) is at most the larger of 1.5 times the mean absolute difference between
    adjacent pixels and 2/255. Integer images are normalised by their maximum value first (#147).
    A source texture that does not tile is made seamless with
    `python -m nmg_game_dev.texture seamless <image.png>`. Texel density is measured per
    material slot; mark a trim-atlas material with `nmg_trim_atlas` (section 6).
- Materials must survive glTF export. At export time each material is a Principled
  BSDF fed only by Image Texture nodes sampling `UVMap`, a Normal Map node, and a
  Separate Color node to split ORM. No procedural texture nodes, no
  Generated/Object/Position/triplanar coordinates. Author procedurally if you want,
  then **bake** to images and rewire the material to the baked images. The bake step is
  `nmggamedev.bake_materials` (see `docs/skills/bake-materials.md`).
- The `.glb` embeds the base color, normal, and ORM images through glTF's metallic-roughness and
  occlusion channels, which Godot's `StandardMaterial3D` reads directly. The PNG set is also written
  beside the `.glb`, because the re-import check (section 8) reads it.
- Texture set per material, power-of-two square, PNG:
  - `T_<Name>_<Part>_BC`: base color (sRGB)
  - `T_<Name>_<Part>_N`: normal (Non-Color, OpenGL convention, which Godot uses as is)
  - `T_<Name>_<Part>_ORM`: R=ambient occlusion, G=roughness, B=metallic (Non-Color)
- Materials named `M_<Name>_<Part>`, where `<Part>` names what the material covers
  (`Body`, `Glass`, `Surface`). Prefer one material per variant; at most the material
  count in section 6.

### Material variants

A material variant is another look of one baked material: a replacement base-colour
texture, a `Tint` value, or both. It shares the material's normal and ORM textures. Unlike
Desktop and Mobile it is not a separate asset: the mesh slots stay bound to the main
`M_<Name>_<Part>`. Replacement normal or ORM textures, masked tinting, and mesh or UV changes are
out of scope.

- **Declaration.** Write `<Name>.material-variants.json` beside the asset's `.blend`. A
  `--blend` run finds it there; otherwise pass its path with `--material-variants` (CLI) or
  `material_variants_path` (MCP). A session run has no `.blend` beside it, so it needs the
  explicit path.
- **Format.**

  ```json
  {
    "schema": 1,
    "material_variants": [
      {"name": "Red", "material": "M_Crate_Body", "base_color": "Red.png"},
      {"name": "Blue", "material": "M_Crate_Body", "parameters": {"Tint": [0.5, 0.25, 1.0]}}
    ]
  }
  ```

  `base_color` is a PNG path, relative to the declaration. `parameters` maps a supported parameter
  to a value; `Tint` is the only one. `Tint` is `[r, g, b]` or `[r, g, b, a]`, with every component
  finite and at least 0; alpha defaults to 1. An entry has `base_color`, `parameters`, or both.
- **Naming.** Finalize writes `T_<Name>_<Part>_BC_<Variant>` (a PNG base colour in sRGB, in both
  the Desktop and Mobile folders). During `import_godot` it writes
  `M_<Name>_<Part>_<Variant>.tres` into each variant folder: a `StandardMaterial3D` whose
  `albedo_texture` is the variant base colour, whose `normal_texture` and ORM channels use the main
  set, and whose `albedo_color` is the `Tint` value (white by default). A parameter-only variant has
  no texture, so its material uses the main base colour. `nmg-variants.json` records each variant's
  `material_resource`. Both variant folders are checked before any `.tres` is written, so a broken
  Mobile export leaves the Desktop materials as they were. A `.tres` an earlier finalize wrote for a
  variant that is no longer declared is removed; the folder's `.nmg-material-variants.json` lists
  what finalize wrote, so a material you made by hand in the folder is never removed.
- **Validation.** `validate` fails with a `material_variant.*` finding before anything is baked
  or exported: `material_variant.name` (not PascalCase letters and digits, or `<Part>_<Variant>`
  names another part), `material_variant.duplicate`, `material_variant.material_missing` (not a
  material the asset has after the bake), `material_variant.material_merged` (see below),
  `material_variant.texture_missing` (not an existing PNG), `material_variant.texture_size` (not
  a power-of-two square, or not the Desktop base-colour size of its material),
  `material_variant.parameter` (not `Tint`, or a malformed value), and
  `material_variant.empty` (neither `base_color` nor `parameters`). A file that is not valid JSON,
  or does not match this format, raises `material_variant.declaration_invalid`.
- **Merged materials.** When the bake merges several authored materials into `M_<Name>_Body`
  (more of them than the Mobile material limit), declare variants on `M_<Name>_Body`. A variant
  on one of the merged authored materials fails `material_variant.material_merged`, which names
  `M_<Name>_Body`. A variant declared on `M_<Name>_Body` is produced for both Desktop and Mobile.
- **Using a variant.** Game code applies a variant by loading its `.tres` and setting it as the
  surface override material of the slot it names.
- **Listing.** The `list_material_variants` MCP tool and
  `python -m nmg_game_dev.finalize material-variants --category <C> --collection <N> [--json]`
  read only `<Category>/<Name>/nmg-variants.json` under the export root (`game/assets` by default)
  and never start Godot. Each row gives the variant's name, its material, and the `res://` path of
  its Desktop and Mobile `.tres`, or `null` for a folder that does not hold it. An asset with no
  material variants returns an empty list; a missing or invalid sidecar fails with
  `finalize.material_variants_failed`.

## 5. Variants

Desktop and Mobile are separate physical assets, both produced in the same session:

- **Desktop**: full quality. Structural cleanup only; no decimation or texture reduction. The one
  exception is a reduce run on a generated asset whose Desktop triangle count is over its class
  budget. Reduce decimates each part to its share of the Desktop budget and rebakes the original's
  look onto the reduced mesh, one `M_<Name>_Body` material and one `T_<Name>_Body_{BC,N,ORM}` set. It
  runs before finalize, never inside it. The reduced `<Name>` carries the custom property
  `nmg_reduced`, and the finalize bake then keeps its atlas layout, including for an
  `environment_piece`. The originals stay in `<Name>_High`.
- **Mobile**: within the mobile budget, by decimating the Desktop mesh or by rebuilding at
  lower detail. Textures re-baked or reduced to mobile resolution, materials merged to the
  mobile material limit. Silhouette must still read.
- The `variants` step cleans every Mobile mesh it produces with the same routine Desktop cleanup
  uses: degenerate, zero-area, non-manifold-edge, duplicate, and loose geometry are removed, and
  normals are recalculated per connected island, the way the `geometry.normals` check judges
  them. The faces at a `geometry.twist_seam` (an island that joins itself with reversed winding)
  are deleted first, then any face that check still flags, each time with the geometry that
  leaves loose, and the recalculation repeats until no seam or flagged face remains. Only an
  island with no consistent orientation (a Klein-bottle-like surface) loses faces, so a
  well-formed mesh loses none;
  this deletion applies to Desktop cleanup too. It then re-seats the Mobile variant so its bottom centre is at the
  world origin, because decimation can move it. The root's origin and the rig are not changed.
- Blender makes no LOD meshes. Godot generates LODs for both variants when it imports the
  `.glb` (the `meshes/generate_lods` import option), so the exported Mobile mesh is LOD 0 and must
  itself be within the mobile triangle budget (section 6).
- A rigged character (its armature `SK_<Name>` is in the collection; see section 7) exports its
  Mobile variant as one skinned mesh, `SM_<Name>_Mobile`, parented to `SK_<Name>` with an Armature
  modifier. Assets with child parts keep their parts, skinned the same way.
- Inside the .blend, Mobile objects, materials, and images may carry a suffix to avoid
  name clashes. Exported files never do: object, material, and texture names in the
  Mobile export are identical to the Desktop export.
- Terrain does not use the rules in this section. Its Mobile variant is derived as section 9
  describes.

## 6. Budgets (defaults; a consumer project may override)

Texture sizes are maximums.

| Class | Example | Desktop tris | Mobile tris | Desktop tex | Mobile tex | Max materials (D/M) |
|---|---|---|---|---|---|---|
| Small prop | bottle, key | 2,000 | 500 | 1024 | 512 | 1 / 1 |
| Standard prop | chest, lamppost, fence segment | 10,000 | 3,000 | 2048 | 1024 | 3 / 1 |
| Hero prop | vehicle, set piece | 40,000 | 10,000 | 4096 | 2048 | 4 / 2 |
| Character | humanoid, creature | 60,000 | 15,000 | 4096 | 2048 | 4 / 2 |
| Environment piece | building, grandstand, road or track section | 40,000 | 10,000 | tiling, 2048 per texture | tiling, 1024 per texture | 6 / 3 |
| Terrain | ground, hillside, valley | n/a | n/a | tiling, 2048 per texture | tiling, 1024 per texture | 4 / 3 |

Environment pieces use the tiling mode and target a texel density of at least
256 px/m on Desktop and 128 px/m on Mobile instead of a single texture set.

Terrain has no triangle budget. Its budget is a heightmap resolution and a layer count:
Desktop `heightmap_px` at most 2017, `layers` at most 4; Mobile `heightmap_px` at most 1009,
`layers` at most 3. Its layers use the same tiling mode and texel density as environment pieces.
Section 9 gives the terrain rules.

Texel density is measured per material slot. Each slot's faces give their own UV area and world
area, and the slot is compared with the minimum on its own, so a dense tiling slot is not diluted by
the atlas and flat-colour faces beside it. Two kinds of slot are exempt, and the reports list each
exempt slot with its reason:

- **Trim atlas** (`trim_atlas`): a material with the custom property `nmg_trim_atlas` set to `True`.
  Set it in Material Properties > Custom Properties, or from a script with
  `material["nmg_trim_atlas"] = True`. The bake and the Mobile variant keep the marker.
- **Flat colour** (`flat_colour`): every face of the slot has its UVs collapsed onto one point or
  cell, so the slot's total UV area is at or below 1e-8 UV units². No marker is needed.

An unmarked slot with UV area that falls below the minimum fails. Its remediation names both ways
out: raise the density, or mark the material as a trim atlas if it is one.

The validation report lists each environment-piece mesh's slots under `snapshot[<object>].texel`,
with each measured slot's Desktop or Mobile px/m, or its exemption. The bake report lists the same
per mesh under `texel_density`.

A project-root `nmg-budgets.json` overrides these defaults. It is keyed by asset class. Top-level
metrics (`tris`, `max_texture_px`, `materials`) override the Mobile budget. A nested `desktop`
object overrides the Desktop budget that validation uses, so a class can allow a larger Desktop
variant:

```json
{
  "hero_prop": {
    "tris": 10000,
    "desktop": { "tris": 300000 }
  }
}
```

## 7. Export

- Terrain exports chunked meshes and a scene instead of one `.glb` per variant. See section 9.
- glTF binary (`.glb`), one file per variant, selected objects only, mesh (and armature if rigged)
  only, modifiers applied, Y up (`export_yup`), at 1 unit = 1 m with the origin at the base centre
  (section 2). The texture set is embedded in the `.glb` and also written as separate PNGs beside
  it.
- Layout, relative to the export root the caller gives (`game/assets` in a consumer project):
  ```
  <Category>/<Name>/Desktop/<Name>.glb + T_*.png + nmg-asset.json
  <Category>/<Name>/Mobile/<Name>.glb  + T_*.png + nmg-asset.json
  <Category>/<Name>/nmg-variants.json
  ```
- `nmg-asset.json` sits in **both** variant folders: `{class, tris, max_texture_px, materials,
  meshes}`, where each entry of `meshes` is `{name, tris, material_slots, bounds}` and `bounds` is
  `{min: [x, y, z], max: [x, y, z]}` in Godot space and metres. `import_godot` compares the imported
  scene against it. `nmg-variants.json` names the variant files `Desktop/<Name>.glb` and
  `Mobile/<Name>.glb`.
- In Godot, each variant is the scene `res://assets/<Category>/<Name>/<Variant>/<Name>.glb`. Godot
  imports it with LOD generation on; nothing else is created beside it except the material-variant
  `.tres` files (section 4).

### Variant references in game code

Desktop and Mobile are separate files, and a build ships only one of them:

- Game code refers to an asset by its variant-free path, `res://assets/<Category>/<Name>/<Name>.glb`,
  and loads it through `NmgAssets.resolve_variant_path(path)` from the `addons/nmg_game_dev` add-on.
  The resolver returns the `Mobile/` path when the running platform has the `mobile` or `web`
  feature tag, and the `Desktop/` path otherwise. A path that is not in that shape, or already names
  a variant folder, is returned unchanged with a warning.
- The export presets that `/onboard-consumer` writes filter the folders: the iOS, Android, and Web
  presets exclude every `assets/*/Desktop/*` folder, and the macOS and Windows presets exclude every
  `assets/*/Mobile/*` folder.

### Rigged characters

A character rigged with `rig_humanoid` (see `docs/rigging-and-animation.md`) exports its armature
with each variant's mesh:

- The armature `SK_<Name>` sits at the world origin with identity transforms and
  lives in collection `<Name>`.
- The root mesh `SM_<Name>` is parented to `SK_<Name>` through an Armature
  modifier. Every vertex has a non-zero weight on at least one deform bone.
- The deform bones are the 26 Mannequin-style bones listed in `docs/rigging-and-animation.md`, in
  that parent hierarchy. The rig has no leaf, finger, twist, or helper bones.
- Each variant's `.glb` holds the armature and that variant's skinned mesh, exported with skins on
  and animations off. Cleanup applies every modifier except the Armature modifier, so the skin and
  the vertex groups survive. In Godot the armature is a `Skeleton3D` inside the variant scene.
- `nmg-variants.json` records `"rigged": true`. An unrigged asset records `"rigged": false`.

### Animation clips

A rigged character's clips are finalized next to its mesh (`docs/mcp/finalize.md`, "Animation
clips"). The contract for them:

- A clip's name is its action's name minus an optional `@SK_<Name>` suffix, where `<Name>` is the
  asset's collection. So `Idle@SK_StreetThug` on `SK_StreetThug` is the clip `Idle`, and an action
  named `Idle` with no suffix is also the clip `Idle`. Several rigs in one `.blend` can each have an
  `Idle` this way. The pattern `^[A-Za-z][A-Za-z0-9_]*$` applies to the bare clip name, not the
  suffix. An action with a foreign suffix, such as `Idle@SK_Cop` on `SK_StreetThug`, stops the
  export with `finalize.clip_rig_mismatch`. Two actions on one rig that give the same clip name, such
  as `Idle` and `Idle@SK_StreetThug`, stop it with `finalize.clip_name_duplicate`. Neither writes a
  file.
- Each clip is one `.glb` at `<export_root>/<Category>/<Name>/Animations/A_<Name>_<Clip>.glb`,
  holding the armature only and exactly one sampled action. `<Clip>` is the bare clip name and
  matches `^[A-Za-z][A-Za-z0-9_]*$`. An action whose bare name breaks the pattern stops the export.
- `Animations/nmg-animations.json` lists each clip's `name`, `file`, `asset_path`, `frame_start`,
  `frame_end`, `frame_count`, `fps`, and `source`. A provenance clip's `source` is its library,
  file, SHA-256, and source skeleton. An authored clip's `source` is `"authored"`. A built-in clip's
  `source` has `library` `"builtin"`, `file` `null`, `skeleton` `"manny"`, and a `sha256` that is the
  SHA-256 of the clip's pose definition (`docs/rigging-and-animation.md`, Built-in library).
- In Godot, each clip file imports as an `AnimationLibrary` (its `.import` file sets
  `importer="animation_library"`). The `Animations/` folder has no Desktop or Mobile split: both
  variants share the same skeleton bone names, so both play the same libraries. Each clip's
  animation and frame count (`round(length * fps)`) must match the sidecar.
- A character with no clips has no `Animations/` folder.

## 8. Before you say it's done

1. **Validate** in Blender with a script and report the numbers: objects in the
   collection, transforms, origin position and dimensions, UV map count/name,
   material node types, triangle counts per variant, texture sizes.
   Any rule above that fails is a blocker, not a footnote.
   Standard tool: the contract validator, `nmggamedev.validate_contract` in the add-on
   panel, or `python -m nmg_game_dev.contract validate --blend <file> --collection <Name>
   --class <class> --report <json>`. It writes a JSON report (`passed`, one finding per
   violated rule, per-object snapshots); a failing report exits 1.
2. **Review the look** by rendering the asset from front, back, side, and three-quarter
   views. Critique each image against: parts floating or poking through each other,
   boxy or primitive-looking shapes where organic ones are expected, attached parts
   that don't sit or connect believably, proportions and real-world scale, texture
   stretching or obvious tiling seams. Fix what you find, then re-render.
   Standard tool: `nmggamedev.render_review` in the add-on panel, or
   `python -m nmg_game_dev.contract render --blend <file> --collection <Name> --out <dir>`.
   Renders land in `<dir>/<variant>/<Name>_{front,back,side,three_quarter}.png`
   (`desktop` and `mobile`). Every view uses the same camera distance and lighting, and
   the open scenes are left unchanged.
3. **Proof the textures in Blender**: the step 2 renders must use the baked,
   export-ready materials, not the procedural or authoring materials they replaced.
   Compare against a render from before baking and check for: baked seams,
   stretching, or blur; missing or black regions; wrong color space; normal maps
   that look inverted; roughness or metallic that reads wrong. Fix and re-bake
   before export.
   Standard tool: pass the exported variant folder and the pre-bake render to the
   same `nmggamedev.render_review` operator, or to `python -m nmg_game_dev.contract
   render --blend <file> --collection <Name> --out <dir> --proof-variant-dir <variant
   folder> --pre-bake <png>`. It writes
   `<dir>/<variant>/<Name>_proof.png`, with the pre-bake, baked, and re-imported renders
   side by side and labeled.
   The bake step writes the pre-bake and baked renders as `<Name>_prebake.png` and
   `<Name>_baked.png`, and fails when they differ beyond tolerance (see
   `docs/skills/bake-materials.md`).
4. **Re-import check**: import the exported `.glb` into an empty scene and confirm it
   still has its base color and normal textures, UVs, scale, orientation, part pivots,
   and names. Render it with the ORM texture wired the way Godot's `StandardMaterial3D`
   reads it, and confirm it matches the proofed look.
   Standard tool: `nmggamedev.reimport_check`, or `python -m nmg_game_dev.contract
   reimport --variant-dir <dir> --pre-report <validate report> --report <json>`. It
   imports the `.glb` in a fresh headless Blender and compares it with the report written
   before export, using the `reimport.*` rules. A missing texture fails with
   `reimport.texture_missing` and names the file.

## 9. Terrain

Terrain (`asset_class` `terrain`) is a heightfield. Finalize turns each variant into chunked meshes
and a Godot scene with heightmap collision instead of one `.glb`. The section 2 origin rule does not
apply, because the grid is centered on the origin, and terrain does not use the section 5 decimation
rules or the section 7 single-file export.

### Grid

- The collection `<Name>` holds one mesh object, `SM_<Name>`, and nothing else.
- The mesh is a regular grid with one vertex per grid point. Its vertex count per side, n, is one of
  127, 253, 505, 1009, 2017, or 4033.
- Adjacent vertices are 1 m apart in X and Y, within 1 mm.
- The grid is centered on the origin: its X and Y extents are symmetric about 0, within 1 mm.
- The §2 transform rules apply to the root object, so the vertex Z values are heights in metres.

### Layers

- Each layer is a float point attribute named `Layer_<L>`, with a value from 0 to 1 at every vertex.
  A terrain has at least one layer and at most 4 on Desktop.
- Each layer `<L>` has a material `M_<Name>_<L>` on the mesh. After the bake, that material uses the
  tiling texture set `T_<Name>_<L>_BC`, `T_<Name>_<L>_N`, and `T_<Name>_<L>_ORM` (section 4).
- Layer materials bake in tiling mode. Their texel density, measured with the mesh's `UVMap`, must be
  at least 256 px/m on Desktop and 128 px/m on Mobile.
- The validator reports each violation as a finding named by rule: `terrain.structure`,
  `terrain.resolution_invalid`, `terrain.spacing`, `terrain.not_centered`, `terrain.layer_missing`,
  `terrain.layer_range`, `terrain.over_budget`, `terrain.layer_texture_missing`, and `texel.density`.
  A failing terrain exports no file and writes nothing into the Godot project.

### Mobile variant

Finalize derives the Mobile variant from the Desktop grid in the same run.

- Heightmap: the Mobile size is the largest valid size within the Mobile budget, reached by halving
  the Desktop size along the valid sizes (2017 becomes 1009). The Mobile grid takes every
  `stride`-th Desktop sample, so it covers the same extent at a spacing of `stride` metres (2 m from
  2017 to 1009).
- Layers: the Mobile variant keeps 3 layers. The layer with the lowest total weight across the grid
  is dropped. At each vertex its weight is redistributed across the remaining layers in proportion to
  their weights. Where the remaining weights are all zero, the vertex goes wholly to the remaining
  layer with the highest total weight.
- Layer textures are resized to no more than 1024 px.

### Exported files

Each variant folder `<Category>/<Name>/<Variant>/`, where `<Variant>` is `Desktop` or `Mobile`, holds:

- `<Name>_Chunk_<row>_<col>.glb`: the variant grid cut into square chunks of 63 quads each (63
  divides every valid size minus one, so chunks tile the grid exactly). Godot generates each chunk's
  LODs on import (`meshes/generate_lods`).
- `T_<Name>_Splat.png`: an 8-bit RGBA weightmap. Layer *i* of the variant is channel *i*, the weights
  are normalized per vertex, and the channels sum to exactly 255 at every pixel. A terrain with more
  than 4 layers fails the `export` step with `export.terrain_layers_unsupported` before anything is
  written (the terrain exporter raises `variants.terrain_layers_unsupported`, and the step reports
  it under its own `export.` prefix like every finalize step error).
- `T_<Name>_<L>_BC.png`, `T_<Name>_<L>_N.png`, and `T_<Name>_<L>_ORM.png`: each layer's tiling texture
  set, at the variant's texture maximum (2048 px Desktop, 1024 px Mobile).
- `T_<Name>_Height.png`: the heightmap as a 16-bit grayscale PNG at the variant's size, kept for the
  re-import check. 0 is the minimum height, 65535 the maximum, and a flat terrain encodes 32768.
  Row 0 is the Blender +Y edge and column 0 the Blender -X edge.
- `<Name>.tscn`, written by `import_godot` (below).

Two sidecars sit in `<Category>/<Name>/`:

- `nmg-variants.json` records `"terrain": true` and, for each variant, its heightmap size, spacing in
  metres, height range in metres, layer list, texture maximum, and height samples. The samples are
  nine points and the lowest and highest vertex.
- `<Variant>/nmg-asset.json` records `"class": "terrain"`, `heightmap_px`, the variant's layer count
  as `layers`, and `max_texture_px`.

### Godot scene

For each variant, `import_godot` writes `<Variant>/<Name>.tscn`:

- The root is a `Node3D` named `<Name>` with one instance of every chunk `.glb`.
- The chunks share a material override, a `ShaderMaterial` that uses
  `res://addons/nmg_game_dev/terrain/nmg_terrain.gdshader` with the splat map and the layer textures.
- A `StaticBody3D` holds a `CollisionShape3D` whose `HeightMapShape3D` has `map_width` and
  `map_depth` equal to `heightmap_px` and `map_data` set to the decoded heights in metres. The shape
  is scaled `(spacing, 1, spacing)` and centred like the mesh, so collision matches the surface.

It then imports the project headless and runs a probe that loads the scene and measures the height
range of `map_data` and of the chunk bounds. If either range differs from the sidecar's height
range (`height_min_m`, `height_max_m`) by more than 5 cm, the step fails with
`import_godot.terrain_height_mismatch`. A missing chunk fails with `import_godot.mismatch`. A region
in the design backlog uses the Desktop `<Name>.tscn` as its ground (`docs/design-contract.md`).

### Re-import check

Terrain's re-import check decodes each variant's PNGs instead of importing a mesh. It checks the
resolution, the layer files, the per-pixel weight sums of 255, and every decoded height against the
pre-export heights within 5 cm. Its findings use the rule `reimport.terrain`.

## 10. Godot import errors

Every finalize, animation, and audio failure on the Godot side stops the run with one of these
codes, a message, and a remediation. Godot always runs headless (`godot --headless`); nothing here
needs an open editor.

| Code | Raised when | Remediation |
|------|-------------|-------------|
| `godot.not_found` | No Godot binary at `GODOT_BIN`, `godot` on `PATH`, or `/Applications/Godot.app`. | Install Godot 4 (latest stable) or set `GODOT_BIN` to its executable. |
| `import_godot.project_missing` | No `project.godot` in the export root or any folder above it. | Run `/onboard-consumer` to create `game/project.godot`, or pass an export root inside the Godot project (`game/assets`). |
| `import_godot.import_failed` | `godot --headless --path game --import` exited non-zero or printed an `ERROR:` line. The first such line is in the message. | Fix the file the error names (usually a malformed `.glb` or `.import`), then rerun `import_godot`. |
| `import_godot.mismatch` | A probed variant's mesh names, triangle counts, material slots, or bounds (within 1 mm) differ from its `nmg-asset.json`, or a terrain chunk is missing. The message names the mesh and the field. | Rerun finalize with `force` so the variant is re-exported and re-imported. If it persists, check the export settings in section 7. |
| `import_godot.terrain_height_mismatch` | A terrain scene's collision or chunk height range differs from the sidecar by more than 5 cm. | Re-export the terrain with `force`. If it persists, check the heightmap encoding and the spacing in `nmg-variants.json`. |
| `import_anims.clip_mismatch` | An imported clip is absent from its `AnimationLibrary`, or its frame count differs from the sidecar. The message names the clip, the expected value, and the measured value. | Re-export the clip, then rerun `import_anims` with `force`. |
| `import_anims.failed` | The clip import or its probe failed. | Run `godot --headless --path game --import` and read its errors, confirm the clip `.glb` files exist, then rerun `import_anims`. |
| `audio.ffmpeg_not_found` | A music import found no ffmpeg at `FFMPEG_BIN` or on `PATH`. Nothing was written under `game/`. | Install ffmpeg or set `FFMPEG_BIN` to its executable. |
