# Blender API reference for freeform modeling

Each fenced `python` block is self-contained: it imports what it uses, builds what it needs, and
runs headless in Blender 5.2 after the scene is cleared. Paste a block into `execute_blender_code`
and replace the placeholder values with the plan's metres.

## bmesh construction

Build a mesh from primitives in bmesh, translate it into place, and link it into the scene.

```python
import bmesh
import bpy

bm = bmesh.new()
bmesh.ops.create_cube(bm, size=0.5)  # a 0.5 m cube centred on the origin
bmesh.ops.translate(bm, verts=bm.verts[:], vec=(0.0, 0.0, 0.25))  # stand it on z = 0
mesh = bpy.data.meshes.new("Block")
bm.to_mesh(mesh)
bm.free()
obj = bpy.data.objects.new("Block", mesh)
bpy.context.scene.collection.objects.link(obj)
```

Use `bm.faces`, `bm.edges`, and `bm.verts` with `bmesh.ops` for edits. Call `bm.free()` once the
mesh is written back with `bm.to_mesh(mesh)`.

## Modifier stacks

Add modifiers with `obj.modifiers.new`. The stack evaluates from the top down, so order matters.
Apply a modifier with `bpy.ops.object.modifier_apply` inside a `temp_override`, or write the
evaluated mesh back without operators.

```python
import bmesh
import bpy

bm = bmesh.new()
bmesh.ops.create_cube(bm, size=0.2)
mesh = bpy.data.meshes.new("Stack")
bm.to_mesh(mesh)
bm.free()
obj = bpy.data.objects.new("Stack", mesh)
bpy.context.scene.collection.objects.link(obj)

bevel = obj.modifiers.new(name="Bevel", type="BEVEL")
bevel.width = 0.01
bevel.segments = 2
array = obj.modifiers.new(name="Array", type="ARRAY")
array.count = 3
array.use_relative_offset = True
array.relative_offset_displace = (1.0, 0.0, 0.0)

with bpy.context.temp_override(object=obj, active_object=obj):
    bpy.ops.object.modifier_apply(modifier="Bevel")
```

To bake the whole stack into the mesh without an operator, copy the evaluated mesh and drop the
modifiers, so they are not applied twice:

```python
import bmesh
import bpy

bm = bmesh.new()
bmesh.ops.create_cube(bm, size=0.2)
mesh = bpy.data.meshes.new("Baked")
bm.to_mesh(mesh)
bm.free()
obj = bpy.data.objects.new("Baked", mesh)
bpy.context.scene.collection.objects.link(obj)
obj.modifiers.new(name="Array", type="ARRAY").count = 2

depsgraph = bpy.context.evaluated_depsgraph_get()
evaluated = bpy.data.meshes.new_from_object(obj.evaluated_get(depsgraph), depsgraph=depsgraph)
old_mesh = obj.data
for modifier in list(obj.modifiers):
    obj.modifiers.remove(modifier)
obj.data = evaluated
bpy.data.meshes.remove(old_mesh)
```

## Geometry Nodes node groups

Create a node group with `bpy.data.node_groups.new(name, "GeometryNodeTree")`, declare its sockets
on `group.interface`, wire the nodes, and attach the group with a `NODES` modifier.

```python
import bmesh
import bpy

group = bpy.data.node_groups.new("GN_Refine", "GeometryNodeTree")
group.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
group.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
group_in = group.nodes.new("NodeGroupInput")
group_out = group.nodes.new("NodeGroupOutput")
subdivide = group.nodes.new("GeometryNodeSubdivideMesh")
subdivide.inputs["Level"].default_value = 1
group.links.new(group_in.outputs["Geometry"], subdivide.inputs["Mesh"])
group.links.new(subdivide.outputs["Mesh"], group_out.inputs["Geometry"])

bm = bmesh.new()
bmesh.ops.create_cube(bm, size=0.2)
mesh = bpy.data.meshes.new("GN_Box")
bm.to_mesh(mesh)
bm.free()
obj = bpy.data.objects.new("GN_Box", mesh)
bpy.context.scene.collection.objects.link(obj)
modifier = obj.modifiers.new(name="Refine", type="NODES")
modifier.node_group = group
```

## Shader nodes by type

Look up nodes by their `type`, never by their name: names are localized and can be renamed.
Set material colors on the shader node inputs. `material.diffuse_color` only changes the viewport.

```python
import bpy

material = bpy.data.materials.new("M_Example")
material.use_nodes = True
bsdf = next(node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
bsdf.inputs["Base Color"].default_value = (0.8, 0.3, 0.1, 1.0)
bsdf.inputs["Roughness"].default_value = 0.6
bsdf.inputs["Metallic"].default_value = 0.0
```

## Changes since Blender 4.x

These changes affect the calls above and the ones the loop makes. Read the enum identifiers and
input names at runtime when a script must run on more than one Blender release.

### Node group interface (4.0)

Sockets are declared on `group.interface.new_socket(...)`. The old `group.inputs.new(...)` and
`group.outputs.new(...)` calls are gone. The Modeling section above already uses the new form.

### Principled BSDF input names (4.0)

Several inputs were renamed: `Specular` is now `Specular IOR Level`, `Subsurface` is
`Subsurface Weight`, `Transmission` is `Transmission Weight`, `Clearcoat` is `Coat Weight`, and
`Emission` is `Emission Color`. Look them up by name from `bsdf.inputs`, and check the name exists
before you set it.

```python
import bpy

material = bpy.data.materials.new("M_Renamed")
material.use_nodes = True
bsdf = next(node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
bsdf.inputs["Specular IOR Level"].default_value = 0.5
bsdf.inputs["Coat Weight"].default_value = 0.0
bsdf.inputs["Emission Color"].default_value = (0.0, 0.0, 0.0, 1.0)
```

### Auto Smooth (removed in 4.1)

The mesh-level Auto Smooth option is gone. Shade smooth by angle with the operator instead, inside a
`temp_override`.

```python
import bmesh
import bpy

bm = bmesh.new()
bmesh.ops.create_cube(bm, size=0.2)
mesh = bpy.data.meshes.new("Smooth")
bm.to_mesh(mesh)
bm.free()
obj = bpy.data.objects.new("Smooth", mesh)
bpy.context.scene.collection.objects.link(obj)
with bpy.context.temp_override(object=obj, active_object=obj, selected_editable_objects=[obj]):
    bpy.ops.object.shade_smooth_by_angle(angle=0.5236)  # 30 degrees, in radians
```

### Render engine identifiers

The EEVEE identifier has changed across the 4.x and 5.x releases. Never hardcode it. Read the enum
and pick an identifier that exists.

```python
import bpy

identifiers = [
    item.identifier for item in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items
]
preferred = "CYCLES" if "CYCLES" in identifiers else identifiers[0]
bpy.context.scene.render.engine = preferred
```

### Context overrides (4.0)

The old dictionary form of an operator's context override is removed. Pass the override as keyword
arguments to `bpy.context.temp_override(...)`, as the modifier and smoothing examples above do.

### Material.use_nodes deprecation (5.x)

Blender 5.2 reports that `Material.use_nodes` is expected to be removed in Blender 6.0. The snippets
here still set it because the supported runtime is 5.2. Update them when the toolchain moves to 6.0.
