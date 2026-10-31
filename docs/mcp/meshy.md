# Meshy MCP: optional model generation and retexture

Meshy is an optional, opt-in, paid source of 3D models. The `meshy` MCP server and the
`python -m nmg_game_dev.meshy` CLI run one implementation. Generation takes a text prompt, one to
four reference images, or both, and retexturing takes a mesh already authored in Blender. A result
lands in the open Blender session as a `<Name>` collection, the same contract the finalize pipeline
uses. Nothing in `pipeline/` or `finalize/` depends on Meshy, and nothing runs unless a key is set.

## Set the key

Add one line to the project's `.env`, at the project root:

```
MESHY_API_KEY=<your key>
```

`.env` is git-ignored: onboarding adds it to the consumer's `.gitignore`. The process environment
variable `MESHY_API_KEY` wins when both are set. Onboarding never asks for, creates, or writes the
key. A missing key fails with `meshy.api_key_missing` before any Meshy request, job, or file write.

## Tools

| Tool | Arguments | Returns |
|------|-----------|---------|
| `generate_model` | `name`, `prompt?`, `image_paths?` (1–4), `texture=true`, `pose?` | `{"job_id"}` |
| `retexture_model` | `name`, `prompt?` or `image_path?` (exactly one) | `{"job_id"}` |
| `get_meshy_job` | `job_id` | The status document |

`name` is PascalCase (`Crate`, `Lamppost`) and becomes the collection name. Poll `get_meshy_job`
until `state` is `succeeded` or `failed`. Meshy tasks run for minutes, longer than the 180 s MCP
limit, so each job runs detached.

## Input combinations

| Inputs | Meshy requests | Notes |
|--------|----------------|-------|
| prompt, `texture=true` | text-to-3D `preview`, then `refine` (PBR) | Meshy shapes the geometry from the text |
| prompt, `texture=false` | text-to-3D `preview` only | Untextured mesh |
| 1 image (± prompt) | image-to-3D | The image shapes the model; the prompt becomes `texture_prompt` |
| 2–4 images (± prompt) | multi-image-to-3D | The images shape the model; the prompt becomes `texture_prompt` |

With images, the images shape the geometry and the prompt steers only the texture. Meshy has no
text input that shapes geometry when images are given. Images are PNG, JPEG, or WebP, at most
20 MB each. A prompt sent with images is at most 800 characters, and a prompt with images cannot
be combined with `texture=false`, because the prompt would go unused.

## Pose

`pose` is `a-pose` or `t-pose`. It is sent as `pose_mode` on the geometry request only when given.
Set it only for characters and creatures with limbs. Never set it for props, which it distorts.

Meshy's `a-pose` drops the arms about 55° below horizontal, and `rig_humanoid` rejects arms dropped
more than 50°. So an `a-pose` import raises each arm about its shoulder until its drop is 48°,
leaving 2° of margin. The raise is described under [Arm raise](#arm-raise). A `t-pose` import, or an
import with no pose, is left as the GLB has it.

## Retexture

`retexture_model` exports the collection's meshes to GLB, sends them to Meshy with a text or
image style, and downloads the PBR maps. It wires them into `M_<Name>_Body` on `SM_<Name>`: base
color is sRGB, the other maps are Non-Color, and the normal map goes through a Normal Map node.
The collection must already be in the session, with its `SM_<Name>` mesh.

## Outputs

| Output | Path or place |
|--------|---------------|
| Generated model | `SourceArt/Meshy/<Name>/<Name>.glb` |
| Session collection | `<Name>` with root mesh `SM_<Name>` and material `M_<Name>_Body` |
| Retextured maps | `SourceArt/Textures/Meshy/<Name>/{base_color,normal,roughness,metallic}.png` |
| Job files | `SourceArt/Meshy/.jobs/<job_id>/` with `request.json`, `status.json`, `job.log`, and `input.glb` for retexture |

No job file holds the key. If the Blender session is unreachable at import or apply time, the
downloaded files are kept and the result carries a warning with code `mcp.blender.unreachable`.
`loaded_into_session` or `applied_to_session` is then `false`.

## Imported mesh

Each import into the session normalizes `SM_<Name>`. The glTF importer splits vertices along UV
seams, so the import first welds vertices within 1e-5 m, which keeps the face count, UVs, and
material slots. It then bakes the object transform into the geometry and recenters the mesh so its
bottom center sits at the world origin, with identity location, rotation, and scale. That is the
contract's `pivot.bottom_center` check. Last, it clears imported custom normals and smooths the mesh
by 30°, keeping edges sharper than 30° marked sharp.

The `import_glb` result reports this as `merged_vertices` (vertices the weld removed, an integer
of at least 0) and `origin_offset` (the `[x, y, z]` translation applied to the geometry, in meters).

## Arm raise

After the normalization, an `a-pose` import raises the arms. It finds each shoulder pivot from the
mesh's world bounding box, at `(x_c ± 0.10·H, y_c, z_min + 0.81·H)`, where `H` is the height. The
hand tip is the vertex farthest on that side. The arm's drop is the angle below horizontal of the
line from the pivot to the hand tip. A side whose drop is 48° or less keeps every vertex. Otherwise
each vertex outboard of the pivot, and no more than 20° below the hand tip, rotates about the pivot
around the front-to-back axis by the excess. The rotation blends linearly over `0.04·H` outward from
the pivot, so the midline and the legs do not move. Vertex and face counts, connectivity, and face
orientation are unchanged. This is vertex math only, with no modifier and no armature.

The import reports this as `arm_raise`, with `left` and `right` each holding:

| Field | Meaning |
|-------|---------|
| `drop_before_deg` | The arm's drop below horizontal before the raise |
| `drop_after_deg` | The drop after the raise, 48° within 0.5° when the raise applied |
| `rotation_deg` | The degrees the hand tip rotated; 0 when that side was already at 48° or less |

`arm_raise` is `null` for any pose other than `a-pose`, and for an import with no pose. A generate
job's `result` carries `arm_raise` only when `loaded_into_session` is `true`.

## Status document

```json
{"job_id": "…", "kind": "generate", "state": "running", "stage": "refine", "progress": 40}
```

`state` is `queued`, `running`, `succeeded`, or `failed`. A succeeded generate job's `result` holds
`name`, `route` (`text`, `image`, or `multi_image`), `glb_path`, `loaded_into_session`,
`collection`, `mesh`, `material`, `merged_vertices`, `origin_offset`, `arm_raise`, and `warnings`.
`collection`, `mesh`, `material`, `merged_vertices`, `origin_offset`, and `arm_raise` are set only
when `loaded_into_session` is `true`; they carry the import's values. A succeeded retexture job's `result` holds `name`,
`maps`, `applied_to_session`, and `warnings`. A failed job carries `error` with `code`, `message`,
and `remediation`.

## CLI

```
python -m nmg_game_dev.meshy generate --name Crate --prompt "weathered wooden crate" [--image PATH ...] [--no-texture] [--pose a-pose] [--wait]
python -m nmg_game_dev.meshy retexture --name Crate (--prompt "mossy stone" | --image PATH) [--wait]
python -m nmg_game_dev.meshy status JOB_ID
```

The CLI prints the same JSON the tools return. `--wait` polls until the job finishes. An error
prints `ERROR [<code>]: …` and `Remediation: …` to stderr and exits 1. Argument errors exit 2.

## Error codes

| Code | Meaning |
|------|---------|
| `meshy.api_key_missing` | No key in the environment or the project `.env` |
| `meshy.invalid_request` | The name, inputs, or pose break a validation rule; nothing was sent |
| `meshy.collection_exists` | A generate targets a collection that already exists in the session |
| `meshy.collection_not_found` | A retexture targets a collection or `SM_<Name>` mesh that is missing |
| `meshy.auth_failed` | Meshy answered 401 |
| `meshy.insufficient_credits` | Meshy answered 402 |
| `meshy.rate_limited` | Meshy answered 429 |
| `meshy.request_failed` | Another HTTP error or a network error |
| `meshy.task_failed` | The task ended `FAILED`, `CANCELED`, or `EXPIRED`; the message is Meshy's |
| `meshy.task_timeout` | No terminal state after 30 minutes |
| `meshy.job_not_found` | No job with that id under the project |
| `meshy.job_crashed` | The detached job hit an unexpected error; the log has the traceback |
| `meshy.session_failed` | The Blender session script reported an error |
| `mcp.blender.unreachable` | Warning only, at import or apply time: the file is kept |

## Requirements

- A Meshy account with credits, and network access to `api.meshy.ai`.
- A reachable Blender session for import and retexture. Start it with `scripts/start-blender-mcp.sh`.
