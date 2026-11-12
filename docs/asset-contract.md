# Asset contract

What "done" means for any asset generated in Blender for an NMG game. This covers
the deliverable, not how you model it: build it however you like, but what you hand
over must satisfy every rule below. Anything that looks right only in Blender's
viewport or renderer is not done.

## 1. Scene layout

- Each asset lives in its own collection named `<Name>` (PascalCase, e.g. `Lamppost`).
- That collection contains only what ships. Ground planes, lights, cameras, and
  set dressing go in a separate `<Name>_Preview` collection that is never exported.
- One root mesh object per variant: `SM_<Name>` (Desktop) and `SM_<Name>_Mobile` (Mobile).
  Split into multiple objects only for parts that must move independently, named
  `SM_<Name>_<Part>`, parented to the root.
- When one request produces several assets, each one is a separate deliverable with
  its own collection at the world origin; overlapping in Blender is expected. Don't
  compose scenes in Blender. Placement and level composition happen in Unreal.

## 2. Units, orientation, pivot

- Meters, scene unit scale 1.0, real-world size (a door is ~2.1 m tall).
- Z up. The asset's front faces -Y (Blender's Front view looks at it). For assets with
  no natural front (terrain, tracks), the side a player first sees faces -Y.
- Root object origin at the bottom center of the asset (where it meets the ground),
  placed at world origin.
- Root object transforms applied: location (0,0,0), rotation (0,0,0), scale (1,1,1).
- Child parts: rotation (0,0,0) and scale (1,1,1), with the origin at the hinge or
  axle and the location wherever that pivot sits relative to the root.
- All modifiers applied before export.

## 3. Geometry

- Normals point outward and are consistent; shading uses custom/auto smoothing,
  not unwanted flat facets.
- No loose vertices, zero-area faces, or duplicate geometry. Visible interpenetration
  is a defect; hidden interior faces should be removed where practical. Open surfaces
  (terrain, ground sheets) are fine where nothing will see underneath.
- Triangle counts within the budget for the asset class (section 6).

## 4. UVs and materials

- Every mesh has exactly one UV map, `UVMap`, with roughly even texel density.
- Two texturing modes:
  - **Unique bake** (default for props, vehicles, characters): non-overlapping UVs,
    all materials baked into a texture set for that asset.
  - **Tiling** (large environment pieces and terrain layers): UVs may overlap and extend past 0–1 so
    tiling materials and trim sheets repeat across the surface. Each tiling texture is
    itself seamless.
- Materials must survive FBX export. At export time each material is a Principled
  BSDF fed only by Image Texture nodes sampling `UVMap`, a Normal Map node, and a
  Separate Color node to split ORM. No procedural texture nodes, no
  Generated/Object/Position/triplanar coordinates. Author procedurally if you want,
  then **bake** to images and rewire the material to the baked images. The bake step is
  `nmggamedev.bake_materials` (see `docs/skills/bake-materials.md`).
- FBX carries base color and normal; it does not carry the ORM wiring. Ship the ORM
  texture anyway: the Unreal import step wires it.
- Texture set per material, power-of-two square, PNG:
  - `T_<Name>_<Part>_BC`: base color (sRGB)
  - `T_<Name>_<Part>_N`: normal (Non-Color, OpenGL convention; the Unreal import step
    sets Flip Green Channel)
  - `T_<Name>_<Part>_ORM`: R=ambient occlusion, G=roughness, B=metallic (Non-Color)
- Materials named `M_<Name>_<Part>`, where `<Part>` names what the material covers
  (`Body`, `Glass`, `Surface`). Prefer one material per variant; at most the material
  count in section 6.

## 5. Variants

Desktop and Mobile are separate physical assets, both produced in the same session:

- **Desktop**: full quality. Structural cleanup only; no decimation or texture reduction.
- **Mobile**: within the mobile budget, by decimating the Desktop mesh or by rebuilding at
  lower detail. Textures re-baked or reduced to mobile resolution, materials merged to the
  mobile material limit. Silhouette must still read.
- The `variants` step cleans every Mobile mesh it produces with the same routine Desktop cleanup
  uses: degenerate, zero-area, non-manifold-edge, duplicate, and loose geometry are removed, and
  normals are recalculated. It then re-seats the Mobile variant so its bottom centre is at the
  world origin, because decimation can move it. The root's origin and the rig are not changed.
- Mobile export is an LOD group: an Empty `SM_<Name>` with `fbx_type = "LodGroup"` whose
  children are `SM_<Name>_LOD0`, `SM_<Name>_LOD1`, and `SM_<Name>_LOD2`. LOD1 and LOD2 are
  50% and 25% of LOD0's triangles. Assets with child parts keep the root mesh `SM_<Name>`
  and their parts, with LOD0 only.
- A rigged character (its armature `SK_<Name>` is in the collection; see §7) has no LOD
  group. Its Mobile variant is three skinned meshes, `SM_<Name>_Mobile`,
  `SM_<Name>_Mobile_LOD1`, and `SM_<Name>_Mobile_LOD2`, each parented to `SK_<Name>` with an
  Armature modifier. Each exports to its own FBX: one per LOD level. LOD1 and LOD2 are 50%
  and 25% of LOD0's triangles. Assets with child parts keep LOD0 only, skinned the same way.
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

## 7. Export

- Terrain exports PNG heightfields and layer textures instead of FBX. See section 9.
- FBX, one file per variant, selected objects only, mesh (and armature if rigged) only,
  modifiers applied, smoothing = Face, Apply Scalings = FBX Units Scale, no embedded
  textures. Textures are written as separate PNGs beside the FBX.
- Layout (relative to the export root the caller gives you):
  ```
  <Category>/<Name>/Desktop/SM_<Name>.fbx + T_*.png
  <Category>/<Name>/Mobile/SM_<Name>.fbx  + T_*.png
  ```

### Rigged characters

A character rigged with `rig_humanoid` (see
`docs/rigging-and-animation.md`) exports one FBX that carries its armature and
every baked clip:

- The armature `SK_<Name>` sits at the world origin with identity transforms and
  lives in collection `<Name>`.
- The root mesh `SM_<Name>` is parented to `SK_<Name>` through an Armature
  modifier. Every vertex has a non-zero weight on at least one deform bone.
- The deform bones are the 26 UE5 Mannequin bones, in the Mannequin parent
  hierarchy. The rig has no leaf, finger, twist, or helper bones.
- The FBX holds the armature and each baked clip as an action. The armature is
  named `Armature` inside the FBX, so it does not add an extra root bone.
- `nmg-animations.json` sits beside the FBX. It lists each clip's name, frame
  range, frame count, fps, and source (library, file, SHA-256, skeleton).

The finalize export places a rigged character in the layout above:

- `Desktop/SM_<Name>.fbx` holds the armature and the skinned Desktop mesh. Cleanup
  applies every modifier except the Armature modifier, so the skin and the vertex
  groups survive.
- `Mobile/SM_<Name>.fbx`, `Mobile/SM_<Name>_LOD1.fbx`, and `Mobile/SM_<Name>_LOD2.fbx`
  each hold the armature and one skinned mesh. An asset with child parts writes only
  `Mobile/SM_<Name>.fbx`, which holds LOD0 and its parts.
- Both variants export with the armature named `Armature`, `add_leaf_bones` off,
  deform-only armature export, primary bone axis Y, secondary X, and no baked animation.
- In Unreal, `/Game/<Category>/<Name>/Desktop/SM_<Name>` is a Skeletal Mesh. It creates
  `SM_<Name>_Skeleton` and `SM_<Name>_PhysicsAsset` beside it. `/Game/<Category>/<Name>/Mobile/SM_<Name>`
  is a Skeletal Mesh with up to three LODs that uses the Desktop skeleton and physics asset.
  Each skeletal material slot `M_<Name>_<Part>` binds to `MI_<Name>_<Part>`.
- `nmg-variants.json` records `"rigged": true` and, when rigged, lists the Mobile files
  in `mobile.lod_files`. An unrigged asset records `"rigged": false` and writes the
  Static Mesh layout above.

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
4. **Re-import check**: import the exported FBX into an empty scene and confirm it
   still has its base color and normal textures, UVs, scale, orientation, part pivots,
   and names. Render it with the ORM texture wired in the same way the Unreal import
   will wire it, and confirm it matches the proofed look.
   Standard tool: `nmggamedev.reimport_check`, or `python -m nmg_game_dev.contract
   reimport --variant-dir <dir> --pre-report <validate report> --report <json>`. It
   imports the FBX in a fresh headless Blender and compares it with the report written
   before export, using the `reimport.*` rules. A missing texture fails with
   `reimport.texture_missing` and names the file.

## 9. Terrain

Terrain (`asset_class` `terrain`) is a heightfield. Finalize turns each variant into an Unreal
Landscape instead of a Static Mesh. The §2 origin rule does not apply, because the grid is centered
on the origin, and terrain does not use the §5 decimation or LOD rules or the §7 FBX export.

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
  A failing terrain exports no file and creates no Unreal asset.

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

- `T_<Name>_Height.png`: the heightmap as a 16-bit grayscale PNG at the variant's size. 0 is the
  minimum height, 65535 the maximum, and a flat terrain encodes 32768. Row 0 is the Blender +Y edge
  and column 0 the Blender -X edge.
- `T_<Name>_Layer_<L>.png`: one 8-bit grayscale weightmap per layer of that variant. The weights are
  normalized per vertex, and the weightmaps of a variant sum to exactly 255 at every pixel.
- `T_<Name>_<L>_BC.png`, `T_<Name>_<L>_N.png`, and `T_<Name>_<L>_ORM.png`: each layer's tiling texture
  set, at the variant's texture maximum (2048 px Desktop, 1024 px Mobile).

No FBX is written. Two sidecars sit in `<Category>/<Name>/`:

- `nmg-variants.json` records `"terrain": true` and, for each variant, its heightmap size, spacing in
  metres, height range in metres, layer list, texture maximum, and height samples. The samples are
  nine points and the lowest and highest vertex.
- `Mobile/nmg-asset.json` records `"class": "terrain"`, `heightmap_px`, the Mobile layer count as
  `layers`, and `max_texture_px`.

### Unreal import

For each variant, finalize imports into `/Game/<Category>/<Name>/<Variant>/`:

- `T_<Name>_<L>_{BC,N,ORM}`: the layer textures. The Height and weightmap PNGs are read by the
  Landscape import and are not imported as textures.
- `M_<Name>_Landscape`: a layered landscape material that blends one layer per weightmap.
- `LI_<Name>_<L>`: one layer info per layer.
- `L_<Name>`: the level that holds the Landscape. Re-importing replaces the level.

The Landscape is centered on the origin. Its XY scale is the spacing in centimetres, and its Z scale
and location reproduce the sidecar's height range. The import samples the Landscape at the sidecar's
sample points. If any sample differs from the Blender height by more than 5 cm, the step fails with
`import_ue.terrain_height_mismatch`.

### Re-import check

Terrain's re-import check decodes each variant's PNGs instead of importing an FBX. It checks the
resolution, the layer files, the per-pixel weight sums of 255, and every decoded height against the
pre-export heights within 5 cm. Its findings use the rule `reimport.terrain`.
