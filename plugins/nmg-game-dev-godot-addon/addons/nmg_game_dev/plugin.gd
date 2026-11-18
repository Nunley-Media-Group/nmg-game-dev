@tool
extends EditorPlugin
## Registers the NmgAssets autoload while the add-on is enabled.

const AUTOLOAD_NAME: String = "NmgAssets"
const AUTOLOAD_PATH: String = "res://addons/nmg_game_dev/nmg_assets.gd"


func _enter_tree() -> void:
	add_autoload_singleton(AUTOLOAD_NAME, AUTOLOAD_PATH)


func _exit_tree() -> void:
	remove_autoload_singleton(AUTOLOAD_NAME)
