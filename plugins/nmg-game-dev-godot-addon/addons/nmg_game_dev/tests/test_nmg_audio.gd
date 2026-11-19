extends "res://addons/nmg_game_dev/tests/nmg_test_case.gd"
## NmgAudio (#237): the six methods (AC1), a missing sound plays nothing and warns once (AC5),
## music repeat, crossfade, loop, and stinger ducking (AC6), volumes saved and loaded (AC7), and
## region music from the current scene, a timed crossfade, and new volumes reaching every sound
## that is playing.

const NmgAudioScript: GDScript = preload("res://addons/nmg_game_dev/audio/nmg_audio.gd")
const NmgAudioTableScript: GDScript = preload("res://addons/nmg_game_dev/audio/nmg_audio_table.gd")
## Only the volume tests save here, and each removes the file before and after it runs, because
## user:// persists between runs. Other tests use UNSAVED_SETTINGS_PATH, which is never written,
## so a saved volume from an earlier run cannot change their levels.
const SETTINGS_PATH: String = "user://nmg_audio_test_volumes.cfg"
const UNSAVED_SETTINGS_PATH: String = "user://nmg_audio_test_unsaved.cfg"
## How long a real-playback test waits for a 0.2 s sound to end.
const REAL_END_TIMEOUT_S: float = 3.0
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


## Wait frames until done returns true, or REAL_END_TIMEOUT_S passes.
func _until(done: Callable) -> void:
	var deadline: int = Time.get_ticks_msec() + int(REAL_END_TIMEOUT_S * 1000.0)
	while not done.call() and Time.get_ticks_msec() < deadline:
		await _tree().process_frame


## Add audio under the tree root and wait a frame, so it is inside the tree and its _ready has run.
func _add(audio: Node) -> Node:
	_tree().root.add_child(audio)
	await _tree().process_frame
	return audio


## Stop every player, free audio, and give the audio server time to drop the stopped playbacks, so
## no stream or playback is still in use when the runner quits.
func _discard(audio: Node) -> void:
	for child: Node in audio.get_children():
		if child.has_method("stop"):
			child.call("stop")
	_tree().root.remove_child(audio)
	audio.free()
	await _tree().create_timer(0.1).timeout


func _remove_saved_volumes() -> void:
	var absolute: String = ProjectSettings.globalize_path(SETTINGS_PATH)
	if FileAccess.file_exists(SETTINGS_PATH):
		check_eq(DirAccess.remove_absolute(absolute), OK, "remove %s" % SETTINGS_PATH)


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
	await _discard(audio)


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
	audio.set("pitch_jitter", 0.5)
	audio.stinger("S")
	check(absf(b_player.volume_db - (base_db + duck_db)) < 0.001, "the music ducks by duck_db")
	var s_player: AudioStreamPlayer = _player_for(audio, s_stream)
	check(s_player != null and s_player.playing, "S plays")
	check_eq(s_player.pitch_scale, 1.0, "a stinger plays at its own pitch, without pitch_jitter")
	s_player.finished.emit()
	check_eq(b_player.volume_db, base_db, "the music returns when S finishes")
	await _discard(audio)


## Let the streams really end, rather than emitting finished by hand: headless Godot mixes through
## its dummy audio driver, so a 0.2 s sound finishes in real time.
func test_music_loops_and_the_duck_ends_when_the_streams_really_end() -> void:
	var m_path: String = _save_wav("RealEndMusic")
	var s_path: String = _save_wav("RealEndStinger")
	var audio: Node = await _add(_audio(_table({"M": m_path, "S": s_path})))
	audio.music("M")
	var m_player: AudioStreamPlayer = _player_for(audio, load(m_path))
	check(m_player != null and m_player.playing, "M plays")
	if m_player == null:
		await _discard(audio)
		return
	var base_db: float = m_player.volume_db
	var m_ends: Array[int] = [0]
	m_player.finished.connect(func() -> void: m_ends[0] += 1)
	await _until(func() -> bool: return m_ends[0] > 0)
	check(m_ends[0] > 0, "M reached its end within %s s" % REAL_END_TIMEOUT_S)
	check(m_player.playing, "M plays again after it really ends")

	audio.stinger("S")
	var s_player: AudioStreamPlayer = _player_for(audio, load(s_path))
	check(s_player != null and s_player.playing, "S plays")
	check(m_player.volume_db < base_db, "the music ducks under S")
	if s_player != null:
		var s_ends: Array[int] = [0]
		s_player.finished.connect(func() -> void: s_ends[0] += 1)
		await _until(func() -> bool: return s_ends[0] > 0)
		check(s_ends[0] > 0, "S reached its end within %s s" % REAL_END_TIMEOUT_S)
	check_eq(m_player.volume_db, base_db, "the music returns when S really ends")
	await _discard(audio)


func test_volumes_persist_to_a_new_component() -> void:
	_remove_saved_volumes()
	var first: Node = await _add(_audio(null, SETTINGS_PATH))
	check_eq(first.get("master_volume"), 1.0, "master volume before set_volumes")
	check_eq(first.get("music_volume"), 1.0, "music volume before set_volumes")
	first.set_volumes(0.8, 0.5, 1.0)
	await _discard(first)
	check(FileAccess.file_exists(SETTINGS_PATH), "set_volumes saved %s" % SETTINGS_PATH)
	var second: Node = await _add(_audio(null, SETTINGS_PATH))
	check_eq(second.get("master_volume"), 0.8, "master volume")
	check_eq(second.get("music_volume"), 0.5, "music volume")
	check_eq(second.get("sfx_volume"), 1.0, "sfx volume")
	await _discard(second)
	_remove_saved_volumes()


func test_new_volumes_reach_the_sfx_ui_and_positional_sounds_playing_now() -> void:
	_remove_saved_volumes()
	var pooled_path: String = _save_wav("Pooled")
	var placed_path: String = _save_wav("Placed")
	var table: Resource = _table({"Pooled": pooled_path, "Placed": placed_path})
	var audio: Node = await _add(_audio(table, SETTINGS_PATH))
	audio.set("pitch_jitter", 0.0)
	audio.sfx("Pooled")
	audio.sfx("Placed", Vector3(2, 0, 0))
	var pooled: AudioStreamPlayer = _player_for(audio, load(pooled_path))
	var placed: AudioStreamPlayer3D = null
	for child: Node in audio.get_children():
		if child is AudioStreamPlayer3D:
			placed = child as AudioStreamPlayer3D
	check(pooled != null and pooled.playing, "the pooled sfx plays")
	check(placed != null and placed.playing, "the positional sfx plays")
	check(pooled != null and absf(pooled.volume_db) < 0.001, "the pooled sfx starts at 0 dB")

	audio.set_volumes(0.5, 1.0, 0.5)
	var expected_db: float = linear_to_db(0.25)
	if pooled != null:
		check(absf(pooled.volume_db - expected_db) < 0.001, "pooled sfx at %f dB" % pooled.volume_db)
	if placed != null:
		check(
			absf(placed.volume_db - expected_db) < 0.001,
			"positional sfx at %f dB" % placed.volume_db,
		)
	await _discard(audio)
	_remove_saved_volumes()


func test_music_change_fades_over_crossfade_seconds() -> void:
	var a_path: String = _save_wav("FadeA")
	var b_path: String = _save_wav("FadeB")
	var audio: Node = _audio(_table({"FadeA": a_path, "FadeB": b_path}))
	audio.set("crossfade_seconds", 0.2)
	await _add(audio)

	audio.music("FadeA")
	await _tree().create_timer(0.4).timeout
	var a_player: AudioStreamPlayer = _player_for(audio, load(a_path))
	check(a_player != null and absf(a_player.volume_db) < 0.01, "A has faded in to 0 dB")

	audio.music("FadeB")
	var b_player: AudioStreamPlayer = _player_for(audio, load(b_path))
	check(b_player != null and b_player.volume_db < -40.0, "B starts the fade near silence")
	await _tree().create_timer(0.4).timeout
	check(b_player != null and absf(b_player.volume_db) < 0.01, "B has faded in to 0 dB")
	check(a_player != null and a_player.volume_db < -40.0, "A has faded out")
	check(a_player != null and not a_player.playing, "A stops after its fade")
	await _discard(audio)


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
	await _discard(audio)
