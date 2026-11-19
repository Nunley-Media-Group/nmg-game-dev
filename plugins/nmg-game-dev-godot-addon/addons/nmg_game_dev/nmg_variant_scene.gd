@tool
class_name NmgVariantScene
extends Node3D
## Instances a split asset's scene for the running platform's variant.
##
## A scene that ships on every platform must not hard-link a Desktop/ or Mobile/ path: the export
## presets drop one of those folders, which would leave a dangling reference. This node holds the
## variant-free path instead (res://assets/<Category>/<Name>/<Name>.tscn) and, when it enters the
## tree, loads the variant NmgAssets picks (Mobile on "mobile" and "web" feature tags, Desktop
## otherwise) and adds it as its child. /design writes one of these for a region's terrain.
##
## In the editor it shows the Desktop variant as a preview, so a designer composing the level sees
## the terrain. The preview child has no owner, so it is never saved into the scene.

const NmgAssetsScript: GDScript = preload("res://addons/nmg_game_dev/nmg_assets.gd")

## The variant-free scene path, for example res://assets/Terrain/Valley/Valley.tscn.
@export var scene_path: String = "":
	set(value):
		scene_path = value
		if Engine.is_editor_hint() and is_inside_tree():
			preview()

var _instance: Node = null


func _ready() -> void:
	if Engine.is_editor_hint():
		preview()
	else:
		instance_variant(OS.has_feature("mobile") or OS.has_feature("web"))


## Return the variant path this node loads for an explicit choice of variant.
func variant_path(mobile: bool) -> String:
	var assets: Node = NmgAssetsScript.new()
	var resolved: String = assets.resolve_variant_path_for(scene_path, mobile)
	assets.free()
	return resolved


## Replace any previous instance with the Desktop variant, unowned so it is never saved. The
## editor calls this when the node enters the tree and whenever scene_path changes.
func preview() -> Node:
	_clear()
	if scene_path.is_empty():
		return null
	return instance_variant(false)


## Load the variant scene and add it as an unowned child. Returns the child, or null with a
## warning when the variant scene does not exist or is not a PackedScene.
func instance_variant(mobile: bool) -> Node:
	var path: String = variant_path(mobile)
	if not ResourceLoader.exists(path):
		push_warning("NmgVariantScene: %s does not exist; nothing was instanced." % path)
		return null
	var packed: PackedScene = load(path) as PackedScene
	if packed == null:
		push_warning("NmgVariantScene: %s is not a scene; nothing was instanced." % path)
		return null
	_instance = packed.instantiate()
	add_child(_instance)
	return _instance


func _clear() -> void:
	if _instance != null and is_instance_valid(_instance):
		remove_child(_instance)
		_instance.free()
	_instance = null
