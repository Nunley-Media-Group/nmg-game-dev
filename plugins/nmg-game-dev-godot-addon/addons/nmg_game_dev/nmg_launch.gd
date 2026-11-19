extends Node
## NmgLaunch autoload: launch options, the autoplay signal, the test save folder, and the in-game
## screenshot (#251). It has no per-frame hook.
##
## Options read the same on desktop and web. On desktop they come after "--" on the command line;
## on web they come from the URL hash:
##     godot --path game -- --hour=12 --at=Forest        (desktop)
##     https://example.com/game/#hour=12&at=Forest        (web)
##     var at: String = NmgLaunch.get_option("at", "Town")
## A bare flag such as --nmg-autoplay or #nmg-autoplay reads "true".
##
## The framework reads these flags: --nmg-autoplay emits autoplay_requested once the main scene's
## _ready has run, so a main scene that connects in its own _ready receives it; --nmg-test-saves
## makes save_dir() return a test folder; --nmg-shot=<path> with --nmg-shot-after=<seconds> saves
## the root viewport as a PNG and quits.

signal autoplay_requested

const TEST_SAVE_DIR: String = "user://nmg-test/"
const DEFAULT_SAVE_DIR: String = "user://"
const AUTOPLAY_WAIT_FRAMES: int = 600

var _options: Dictionary = {}
var _configured: bool = false
var _autoplay_sent: bool = false


## Read the launch options, unless configure() already set them before the node entered the tree.
func _ready() -> void:
	if not _configured:
		configure(OS.get_cmdline_user_args(), _web_hash())
	if has_option("nmg-shot"):
		_take_shot()
	if has_option("nmg-autoplay"):
		_autoplay_when_scene_ready()


## Replace the parsed options with those in user_args and url_hash. A "--name=value" argument (or a
## bare "--name") is read; other arguments are ignored. The hash is read after the arguments, so it
## wins when a name appears in both.
func configure(user_args: PackedStringArray, url_hash: String) -> void:
	_options.clear()
	_configured = true
	for token: String in user_args:
		if token.begins_with("--"):
			_store_pair(token.substr(2), false)
	for part: String in url_hash.trim_prefix("#").split("&", false):
		_store_pair(part, true)


## Return the value of option name, or default_value when the option was not given.
func get_option(name: String, default_value: String = "") -> String:
	if not _options.has(name):
		return default_value
	return str(_options[name])


func has_option(name: String) -> bool:
	return _options.has(name)


## Return the folder saves go to. With --nmg-test-saves it is TEST_SAVE_DIR, created on demand, so
## test runs never touch the player's saves; otherwise it is DEFAULT_SAVE_DIR.
func save_dir() -> String:
	if not has_option("nmg-test-saves"):
		return DEFAULT_SAVE_DIR
	DirAccess.make_dir_recursive_absolute(TEST_SAVE_DIR)
	return TEST_SAVE_DIR


## Emit autoplay_requested. Only the first call emits, so the game can call it from anywhere.
func request_autoplay() -> void:
	if _autoplay_sent:
		return
	_autoplay_sent = true
	autoplay_requested.emit()


func _web_hash() -> String:
	if not OS.has_feature("web"):
		return ""
	var value: Variant = JavaScriptBridge.eval("window.location.hash", true)
	return "" if value == null else str(value)


func _store_pair(pair: String, decode: bool) -> void:
	var split: int = pair.find("=")
	var option_name: String = pair if split < 0 else pair.substr(0, split)
	var value: String = "true" if split < 0 else pair.substr(split + 1)
	if decode:
		option_name = option_name.uri_decode()
		value = value.uri_decode()
	if not option_name.is_empty():
		_options[option_name] = value


## The autoload's _ready runs before the main scene's _ready, even when the main scene is already
## current, so wait at least one frame, then until the current scene is ready.
func _autoplay_when_scene_ready() -> void:
	for _frame: int in AUTOPLAY_WAIT_FRAMES:
		await get_tree().process_frame
		var scene: Node = get_tree().current_scene
		if scene != null and scene.is_node_ready():
			break
	request_autoplay()


func _take_shot() -> void:
	var path: String = get_option("nmg-shot")
	await get_tree().create_timer(get_option("nmg-shot-after", "0").to_float()).timeout
	await RenderingServer.frame_post_draw
	var image: Image = get_viewport().get_texture().get_image()
	var error: Error = FAILED if image == null else image.save_png(path)
	if error == OK:
		get_tree().quit(0)
		return
	push_error("NmgLaunch: could not save the screenshot to %s (error %d)" % [path, error])
	get_tree().quit(1)
