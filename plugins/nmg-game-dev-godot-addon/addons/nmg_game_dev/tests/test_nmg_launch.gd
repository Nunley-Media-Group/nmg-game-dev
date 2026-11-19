extends "res://addons/nmg_game_dev/tests/nmg_test_case.gd"
## NmgLaunch: option parsing on the command line and the web hash, defaults, the single autoplay
## emission, the autoplay emission reaching a main scene that connects in its own _ready, and the
## test save folder (#251 AC1, AC2, AC7).

const NmgLaunchScript: GDScript = preload("res://addons/nmg_game_dev/nmg_launch.gd")
const AutoplaySceneScript: GDScript = preload(
	"res://addons/nmg_game_dev/tests/nmg_autoplay_scene.gd"
)
const AUTOPLAY_TEST_FRAMES: int = 5

var emissions: int = 0


func _launch(user_args: PackedStringArray, url_hash: String) -> Node:
	var launch: Node = NmgLaunchScript.new()
	launch.configure(user_args, url_hash)
	return launch


func _count_emission() -> void:
	emissions += 1


func test_cmdline_options() -> void:
	var launch: Node = _launch(PackedStringArray(["--hour=12", "--at=Forest"]), "")
	check_eq(launch.get_option("hour", ""), "12", "cmdline hour")
	check_eq(launch.get_option("at", ""), "Forest", "cmdline at")
	check(launch.has_option("hour") and launch.has_option("at"), "cmdline options are present")
	launch.free()


func test_web_hash_options() -> void:
	var launch: Node = _launch(PackedStringArray(), "#hour=12&at=Forest")
	check_eq(launch.get_option("hour", ""), "12", "hash hour")
	check_eq(launch.get_option("at", ""), "Forest", "hash at")
	check(launch.has_option("hour") and launch.has_option("at"), "hash options are present")
	launch.free()


func test_flag_reads_true() -> void:
	var from_args: Node = _launch(PackedStringArray(["--nmg-autoplay"]), "")
	check_eq(from_args.get_option("nmg-autoplay", ""), "true", "cmdline flag reads true")
	from_args.free()
	var from_hash: Node = _launch(PackedStringArray(), "#nmg-autoplay")
	check_eq(from_hash.get_option("nmg-autoplay", ""), "true", "hash flag reads true")
	from_hash.free()


func test_absent_option_returns_default() -> void:
	var launch: Node = _launch(PackedStringArray(["--hour=12"]), "#at=Forest")
	check_eq(launch.get_option("missing", "Town"), "Town", "absent option returns the default")
	check_eq(launch.get_option("missing", ""), "", "absent option returns an empty default")
	check(not launch.has_option("missing"), "absent option is not present")
	launch.free()


func test_hash_wins_over_command_line() -> void:
	var launch: Node = _launch(PackedStringArray(["--at=Town"]), "#at=Forest")
	check_eq(launch.get_option("at", ""), "Forest", "the hash wins on a repeated name")
	launch.free()


func test_non_option_arguments_are_ignored() -> void:
	var launch: Node = _launch(PackedStringArray(["hour=12"]), "")
	check(not launch.has_option("hour"), "an argument without -- is not an option")
	launch.free()


func test_autoplay_emits_once() -> void:
	var launch: Node = _launch(PackedStringArray(["--nmg-autoplay"]), "")
	emissions = 0
	launch.connect("autoplay_requested", _count_emission)
	launch.request_autoplay()
	launch.request_autoplay()
	check_eq(emissions, 1, "autoplay_requested emitted once")
	launch.free()


## The launch node's _ready runs while the main scene is already current but before the main
## scene's _ready, as for the NmgLaunch autoload. The emission must still reach the main scene's
## handler, exactly once.
func test_autoplay_reaches_a_scene_that_connects_in_ready() -> void:
	var tree: SceneTree = Engine.get_main_loop() as SceneTree
	var scene: Node = AutoplaySceneScript.new()
	var launch: Node = _launch(PackedStringArray(["--nmg-autoplay"]), "")
	scene.set("launch", launch)
	scene.add_child(launch)
	tree.root.add_child(scene)
	check_eq(scene.get("received"), 0, "autoplay_requested not emitted before a frame passes")
	for _frame: int in AUTOPLAY_TEST_FRAMES:
		await tree.process_frame
	check_eq(scene.get("received"), 1, "the main scene received autoplay_requested once")
	tree.current_scene = null
	scene.free()


func test_save_dir_with_test_saves() -> void:
	var launch: Node = _launch(PackedStringArray(["--nmg-test-saves"]), "")
	check_eq(launch.save_dir(), "user://nmg-test/", "test save folder")
	check(DirAccess.dir_exists_absolute("user://nmg-test/"), "test save folder exists")
	launch.free()


func test_save_dir_default() -> void:
	var launch: Node = _launch(PackedStringArray(), "")
	check_eq(launch.save_dir(), "user://", "default save folder")
	launch.free()
