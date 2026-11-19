extends "res://addons/nmg_game_dev/tests/nmg_test_case.gd"
## NmgAudio (#237): the six methods (AC1), a missing sound plays nothing and warns once (AC5),
## music repeat, crossfade, loop, and stinger ducking (AC6), volumes saved and loaded (AC7), and
## region music from the current scene.

const NmgAudioScript: GDScript = preload("res://addons/nmg_game_dev/audio/nmg_audio.gd")
const NmgAudioTableScript: GDScript = preload("res://addons/nmg_game_dev/audio/nmg_audio_table.gd")
## Only the volume test saves here. Other tests use UNSAVED_SETTINGS_PATH, which is never written,
## so a saved volume from an earlier run cannot change their levels.
const SETTINGS_PATH: String = "user://nmg_audio_test_volumes.cfg"
const UNSAVED_SETTINGS_PATH: String = "user://nmg_audio_test_unsaved.cfg"
const METHODS: PackedStringArray = ["sfx", "ui", "music", "stinger", "region_music", "set_volumes"]


func _tree() -> SceneTree:
	return Engine.get_main_loop() as SceneTree


## Save a short silent 16-bit WAV under user:// and return its path.
func _save_wav(sound_name: String) -> String:
	var stream: AudioStreamWAV = AudioStreamWAV.new()
	stream.format = AudioStreamWAV.FORMAT_16_BITS
	stream.mix_rate = 22050
	var data: PackedByteArray = PackedByteArray()
	data.resize(4410)
	stream.data = data
	var path: String = "user://nmg_audio_test_%s.tres" % sound_name
	check_eq(ResourceSaver.save(stream, path), OK, "save %s" % path)
	return path


func _table(sounds: Dictionary, themes: Dictionary = {}) -> Resource:
	var table: Resource = NmgAudioTableScript.new()
	table.set("sounds", sounds)
	table.set("themes", themes)
	return table


## An NmgAudio with no crossfade, not yet in the tree.
func _audio(table: Resource, settings: String = UNSAVED_SETTINGS_PATH) -> Node:
	var audio: Node = NmgAudioScript.new()
	audio.set("table", table)
	audio.set("crossfade_seconds", 0.0)
	audio.set("settings_path", settings)
	return audio


## Add audio under the tree root and wait a frame, so it is inside the tree and its _ready has run.
func _add(audio: Node) -> Node:
	_tree().root.add_child(audio)
	await _tree().process_frame
	return audio


func _discard(audio: Node) -> void:
	_tree().root.remove_child(audio)
	audio.free()


## Return the child player that plays stream, or null.
func _player_for(audio: Node, stream: Resource) -> AudioStreamPlayer:
	for child: Node in audio.get_children():
		var player: AudioStreamPlayer = child as AudioStreamPlayer
		if player != null and player.stream == stream:
			return player
	return null


func _playing_count(audio: Node) -> int:
	var count: int = 0
	for child: Node in audio.get_children():
		if child.get("playing") == true:
			count += 1
	return count


func test_component_has_the_six_methods() -> void:
	var audio: Node = _audio(null)
	for method: String in METHODS:
		check(audio.has_method(method), "NmgAudio has %s" % method)
	audio.free()


func test_missing_sound_plays_nothing_and_warns_once() -> void:
	var audio: Node = await _add(_audio(_table({})))
	take_warnings()
	audio.sfx("NotYetImported", Vector3(1, 0, 0))
	audio.sfx("NotYetImported", Vector3(1, 0, 0))
	var warnings: PackedStringArray = take_warnings()
	check_eq(warnings.size(), 1, "warnings for NotYetImported")
	if warnings.size() == 1:
		check(warnings[0].contains("NotYetImported"), "the warning names the sound: %s" % warnings[0])
	check_eq(_playing_count(audio), 0, "nothing plays")
	_discard(audio)


func test_music_repeat_crossfade_loop_and_stinger_duck() -> void:
	var a_path: String = _save_wav("A")
	var b_path: String = _save_wav("B")
	var s_path: String = _save_wav("S")
	var audio: Node = await _add(_audio(_table({"A": a_path, "B": b_path, "S": s_path})))
	var duck_db: float = audio.get("duck_db")
	var a_stream: Resource = load(a_path)
	var b_stream: Resource = load(b_path)
	var s_stream: Resource = load(s_path)

	audio.music("A")
	var a_player: AudioStreamPlayer = _player_for(audio, a_stream)
	check(a_player != null and a_player.playing, "A plays")
	audio.music("A")
	check(
		_player_for(audio, a_stream) == a_player and a_player.playing,
		"a repeat of A keeps its player playing",
	)

	audio.music("B")
	var b_player: AudioStreamPlayer = _player_for(audio, b_stream)
	check(b_player != null and b_player.playing, "B plays")
	check(a_player != null and not a_player.playing, "A stops once B takes over")

	b_player.finished.emit()
	check(b_player.playing, "B plays again when it finishes")

	var base_db: float = b_player.volume_db
	audio.stinger("S")
	check(absf(b_player.volume_db - (base_db + duck_db)) < 0.001, "the music ducks by duck_db")
	var s_player: AudioStreamPlayer = _player_for(audio, s_stream)
	check(s_player != null and s_player.playing, "S plays")
	s_player.finished.emit()
	check_eq(b_player.volume_db, base_db, "the music returns when S finishes")
	_discard(audio)


func test_volumes_persist_to_a_new_component() -> void:
	var first: Node = await _add(_audio(null, SETTINGS_PATH))
	first.set_volumes(0.8, 0.5, 1.0)
	_discard(first)
	var second: Node = await _add(_audio(null, SETTINGS_PATH))
	check_eq(second.get("master_volume"), 0.8, "master volume")
	check_eq(second.get("music_volume"), 0.5, "music volume")
	check_eq(second.get("sfx_volume"), 1.0, "sfx volume")
	_discard(second)


func test_region_music_plays_the_theme_of_the_current_scene() -> void:
	var theme_path: String = _save_wav("ForestTheme")
	var table: Resource = _table({"ForestTheme": theme_path}, {"Forest": "ForestTheme"})
	var audio: Node = await _add(_audio(table))
	var scene: Node = Node.new()
	scene.name = "Forest"
	_tree().root.add_child(scene)
	_tree().current_scene = scene
	audio.region_music()
	var player: AudioStreamPlayer = _player_for(audio, load(theme_path))
	check(player != null and player.playing, "the Forest theme plays")
	_tree().current_scene = null
	_tree().root.remove_child(scene)
	scene.free()
	_discard(audio)
