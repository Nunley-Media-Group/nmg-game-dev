@tool
extends Node
## NmgAssets autoload: routes an asset path to its Desktop or Mobile variant.
##
## @tool so NmgVariantScene can resolve its editor preview; it has no per-frame or editor hooks.
##
## Finalized assets live at res://assets/<Category>/<Name>/<Desktop|Mobile>/<Name>.<ext>. Game code
## names the asset without the variant folder and lets this autoload pick it:
##     var path := NmgAssets.resolve_variant_path("res://assets/Props/Crate/Crate.glb")
## Platforms with the "mobile" or "web" feature tag get Mobile; every other platform gets Desktop.

const DESKTOP_FOLDER: String = "Desktop"
const MOBILE_FOLDER: String = "Mobile"


## Return the variant path for the running platform.
func resolve_variant_path(path: String) -> String:
	return resolve_variant_path_for(path, OS.has_feature("mobile") or OS.has_feature("web"))


## Return the variant path for an explicit choice of variant.
##
## A well-formed path is <dir>/<Folder>/<File> where File's basename equals Folder; the result is
## <dir>/<Folder>/<Mobile|Desktop>/<File>. Any other path is returned unchanged with a warning.
func resolve_variant_path_for(path: String, mobile: bool) -> String:
	var reason: String = _malformed_reason(path)
	if not reason.is_empty():
		push_warning("NmgAssets: %s; returning %s unchanged." % [reason, path])
		return path
	var variant: String = MOBILE_FOLDER if mobile else DESKTOP_FOLDER
	return path.get_base_dir().path_join(variant).path_join(path.get_file())


func _malformed_reason(path: String) -> String:
	if path.is_empty():
		return "the path is empty"
	if ("/%s/" % DESKTOP_FOLDER) in path or ("/%s/" % MOBILE_FOLDER) in path:
		return "the path already names a variant folder"
	var folder: String = path.get_base_dir().get_file()
	if folder.is_empty():
		return "the path has no parent folder"
	if path.get_file().get_basename() != folder:
		return "the file name does not match its folder %s" % folder
	return ""
