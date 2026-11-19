@tool
extends EditorPlugin
## Registers the NmgAssets and NmgLaunch autoloads while the add-on is enabled.

const AUTOLOAD_NAME: String = "NmgAssets"
const AUTOLOAD_PATH: String = "res://addons/nmg_game_dev/nmg_assets.gd"
const LAUNCH_AUTOLOAD_NAME: String = "NmgLaunch"
const LAUNCH_AUTOLOAD_PATH: String = "res://addons/nmg_game_dev/nmg_launch.gd"


func _enter_tree() -> void:
	add_autoload_singleton(AUTOLOAD_NAME, AUTOLOAD_PATH)
	add_autoload_singleton(LAUNCH_AUTOLOAD_NAME, LAUNCH_AUTOLOAD_PATH)


func _exit_tree() -> void:
	remove_autoload_singleton(AUTOLOAD_NAME)
	remove_autoload_singleton(LAUNCH_AUTOLOAD_NAME)
