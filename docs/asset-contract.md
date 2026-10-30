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
  - **Tiling** (large environment pieces): UVs may overlap and extend past 0–1 so
    tiling materials and trim sheets repeat across the surface. Each tiling texture is
    itself seamless.
- Materials must survive FBX export. At export time each material is a Principled
  BSDF fed only by Image Texture nodes sampling `UVMap`, a Normal Map node, and a
  Separate Color node to split ORM. No procedural texture nodes, no
  Generated/Object/Position/triplanar coordinates. Author procedurally if you want,
  then **bake** to images and rewire the material to the baked images.
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
- Inside the .blend, Mobile objects, materials, and images may carry a suffix to avoid
  name clashes. Exported files never do: object, material, and texture names in the
  Mobile export are identical to the Desktop export.

## 6. Budgets (defaults; a consumer project may override)

Texture sizes are maximums.

| Class | Example | Desktop tris | Mobile tris | Desktop tex | Mobile tex | Max materials (D/M) |
|---|---|---|---|---|---|---|
| Small prop | bottle, key | 2,000 | 500 | 1024 | 512 | 1 / 1 |
| Standard prop | chest, lamppost, fence segment | 10,000 | 3,000 | 2048 | 1024 | 3 / 1 |
| Hero prop | vehicle, set piece | 40,000 | 10,000 | 4096 | 2048 | 4 / 2 |
| Character | humanoid, creature | 60,000 | 15,000 | 4096 | 2048 | 4 / 2 |
| Environment piece | building, grandstand, road or track section | 40,000 | 10,000 | tiling, 2048 per texture | tiling, 1024 per texture | 6 / 3 |

Environment pieces use the tiling mode and target a texel density of at least
256 px/m on Desktop and 128 px/m on Mobile instead of a single texture set.

## 7. Export

- FBX, one file per variant, selected objects only, mesh (and armature if rigged) only,
  modifiers applied, smoothing = Face, Apply Scalings = FBX Units Scale, no embedded
  textures. Textures are written as separate PNGs beside the FBX.
- Layout (relative to the export root the caller gives you):
  ```
  <Category>/<Name>/Desktop/SM_<Name>.fbx + T_*.png
  <Category>/<Name>/Mobile/SM_<Name>.fbx  + T_*.png
  ```

## 8. Before you say it's done

1. **Validate** in Blender with a script and report the numbers: objects in the
   collection, transforms, origin position and dimensions, UV map count/name,
   material node types, triangle counts per variant, texture sizes.
   Any rule above that fails is a blocker, not a footnote.
2. **Review the look** by rendering the asset from front, back, side, and three-quarter
   views. Critique each image against: parts floating or poking through each other,
   boxy or primitive-looking shapes where organic ones are expected, attached parts
   that don't sit or connect believably, proportions and real-world scale, texture
   stretching or obvious tiling seams. Fix what you find, then re-render.
3. **Re-import check**: import the exported FBX into an empty scene and confirm it
   still has its base color and normal textures, UVs, scale, orientation, part pivots,
   and names.
