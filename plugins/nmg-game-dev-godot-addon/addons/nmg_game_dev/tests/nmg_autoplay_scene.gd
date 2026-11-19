extends Node
## Stand-in main scene for test_nmg_launch.gd. It becomes the current scene when it enters the tree,
## before any child's _ready (as the engine sets the main scene current before the autoloads'
## _ready), and connects to its launch node's autoplay_requested in its own _ready, as a game would.

var launch: Node = null
var received: int = 0


func _enter_tree() -> void:
	get_tree().current_scene = self


func _ready() -> void:
	launch.connect("autoplay_requested", _on_autoplay_requested)


func _on_autoplay_requested() -> void:
	received += 1
