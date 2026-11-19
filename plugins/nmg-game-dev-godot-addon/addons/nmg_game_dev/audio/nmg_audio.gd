class_name NmgAudio
extends Node
## Plays imported sounds by name (#237): sound effects, optionally positional, UI sounds, music that
## crossfades and loops, and stingers that duck the music.
##
## The scaffolded <Name>Component extends this and loads its table in _init. Gameplay calls
## sfx("DoorCreak", position), ui("Click"), music("ForestTheme"), and stinger("Fanfare"). A name the
## table does not hold plays nothing and pushes one warning. Volumes are linear 0 to 1 and persist in
## settings_path, so the player's choice survives a restart.

const MIN_DB: float = -80.0
const VOLUMES_SECTION: String = "volumes"
const MUSIC_PLAYERS: int = 2

## Sound names to res:// paths, and region scene names to their theme.
@export var table: NmgAudioTable
## Seconds a music change fades over. 0 switches at once.
@export var crossfade_seconds: float = 1.0
## How far the music drops, in dB, while a stinger plays.
@export var duck_db: float = -12.0
## Each sound plays at a pitch within 1 plus or minus this factor.
@export var pitch_jitter: float = 0.05
## Where set_volumes saves the volumes and _ready loads them.
@export var settings_path: String = "user://nmg_audio.cfg"

## Linear volumes from 0 to 1, saved by set_volumes.
var master_volume: float = 1.0
var music_volume: float = 1.0
var sfx_volume: float = 1.0

var _music_players: Array[AudioStreamPlayer] = []
var _music_slot: int = 0
var _music_name: StringName = &""
var _stinger_player: AudioStreamPlayer = null
var _sfx_pool: Array[AudioStreamPlayer] = []
var _fades: Dictionary = {}
var _ducked: bool = false
var _warned: Dictionary = {}


func _ready() -> void:
	_ensure_players()
	_load_volumes()
	call_deferred("region_music")


## Play a sound effect. A zero position plays it without a place. Any other position plays it through
## an AudioStreamPlayer3D there, which is freed when it finishes.
func sfx(sound_name: StringName, position: Vector3 = Vector3.ZERO) -> void:
	var stream: AudioStream = _stream_for(sound_name)
	if stream == null:
		return
	if position == Vector3.ZERO:
		_play_pooled(stream, master_volume * sfx_volume, _jitter())
		return
	var player: AudioStreamPlayer3D = AudioStreamPlayer3D.new()
	player.stream = stream
	player.volume_db = _db(master_volume * sfx_volume)
	player.pitch_scale = _jitter()
	add_child(player)
	if player.is_inside_tree():
		player.global_position = position
	else:
		player.position = position
	player.finished.connect(player.queue_free)
	player.play()


## Play a UI sound at the sfx volume, without a place or a pitch change.
func ui(sound_name: StringName) -> void:
	var stream: AudioStream = _stream_for(sound_name)
	if stream != null:
		_play_pooled(stream, master_volume * sfx_volume, 1.0)


## Play the named track, crossfading from the track playing now. A repeat of the current track
## changes nothing, so it keeps its player and its stream.
func music(sound_name: StringName) -> void:
	if sound_name == _music_name:
		return
	var stream: AudioStream = _stream_for(sound_name)
	if stream == null:
		return
	_ensure_players()
	var outgoing: AudioStreamPlayer = _music_players[_music_slot]
	_music_slot = (_music_slot + 1) % MUSIC_PLAYERS
	var incoming: AudioStreamPlayer = _music_players[_music_slot]
	_music_name = sound_name
	incoming.stream = stream
	incoming.volume_db = MIN_DB
	incoming.play()
	_fade(incoming, _music_target_db(), crossfade_seconds, false)
	if outgoing.playing:
		_fade(outgoing, MIN_DB, crossfade_seconds, true)


## Play a one-shot stinger over the music. The music ducks by duck_db until the stinger finishes.
## A stinger is musical, so it plays at its own pitch: pitch_jitter applies to sfx only.
func stinger(sound_name: StringName) -> void:
	var stream: AudioStream = _stream_for(sound_name)
	if stream == null:
		return
	_ensure_players()
	_stinger_player.stream = stream
	_stinger_player.volume_db = _db(master_volume * sfx_volume)
	_stinger_player.pitch_scale = 1.0
	_stinger_player.play()
	_ducked = true
	_refresh_music_volume(crossfade_seconds)


## Play the table's theme for the current scene when it names one. Otherwise nothing plays.
func region_music() -> void:
	if table == null or not is_inside_tree():
		return
	var scene: Node = get_tree().current_scene
	if scene == null:
		return
	var scene_name: String = String(scene.name)
	if table.themes.has(scene_name):
		music(StringName(String(table.themes[scene_name])))


## Set the master, music, and sfx volumes (linear 0 to 1), apply them to the audio playing now (the
## music, the stinger, and every sfx and UI sound, positional ones included), and save them to
## settings_path.
func set_volumes(master_level: float, music_level: float, sfx_level: float) -> void:
	master_volume = clampf(master_level, 0.0, 1.0)
	music_volume = clampf(music_level, 0.0, 1.0)
	sfx_volume = clampf(sfx_level, 0.0, 1.0)
	_ensure_players()
	var sfx_db: float = _db(master_volume * sfx_volume)
	_stinger_player.volume_db = sfx_db
	for player: AudioStreamPlayer in _sfx_pool:
		player.volume_db = sfx_db
	for child: Node in get_children():
		if child is AudioStreamPlayer3D:
			(child as AudioStreamPlayer3D).volume_db = sfx_db
	_refresh_music_volume(0.0)
	_save_volumes()


func _ensure_players() -> void:
	if not _music_players.is_empty():
		return
	for _index: int in range(MUSIC_PLAYERS):
		var player: AudioStreamPlayer = AudioStreamPlayer.new()
		add_child(player)
		player.finished.connect(_on_music_finished.bind(player))
		_music_players.append(player)
	_stinger_player = AudioStreamPlayer.new()
	add_child(_stinger_player)
	_stinger_player.finished.connect(_on_stinger_finished)


## Return the stream for a sound name, or null after one warning per name when it cannot play.
func _stream_for(sound_name: StringName) -> AudioStream:
	var path: String = _path_for(sound_name)
	var problem: String = ""
	if path.is_empty():
		problem = "no sound named %s" % sound_name
	elif not ResourceLoader.exists(path):
		problem = "%s is not imported at %s" % [sound_name, path]
	if not problem.is_empty():
		if not _warned.has(sound_name):
			_warned[sound_name] = true
			push_warning("NmgAudio: " + problem)
		return null
	return load(path) as AudioStream


func _path_for(sound_name: StringName) -> String:
	if table == null:
		return ""
	return String(table.sounds.get(String(sound_name), ""))


func _play_pooled(stream: AudioStream, linear: float, pitch: float) -> void:
	var player: AudioStreamPlayer = _idle_player()
	player.stream = stream
	player.volume_db = _db(linear)
	player.pitch_scale = pitch
	player.play()


func _idle_player() -> AudioStreamPlayer:
	for candidate: AudioStreamPlayer in _sfx_pool:
		if not candidate.playing:
			return candidate
	var player: AudioStreamPlayer = AudioStreamPlayer.new()
	add_child(player)
	_sfx_pool.append(player)
	return player


func _jitter() -> float:
	return randf_range(1.0 - pitch_jitter, 1.0 + pitch_jitter)


func _music_target_db() -> float:
	var target: float = _db(master_volume * music_volume)
	return target + duck_db if _ducked else target


func _refresh_music_volume(seconds: float) -> void:
	if _music_name.is_empty():
		return
	_fade(_music_players[_music_slot], _music_target_db(), seconds, false)


## Move player's volume to target_db over seconds, stopping it afterwards when stop_after is set. A
## new fade replaces the one already running on the player.
func _fade(player: AudioStreamPlayer, target_db: float, seconds: float, stop_after: bool) -> void:
	if _fades.has(player):
		var running: Tween = _fades[player]
		running.kill()
		_fades.erase(player)
	if seconds <= 0.0:
		player.volume_db = target_db
		if stop_after:
			player.stop()
		return
	var tween: Tween = create_tween()
	tween.tween_property(player, "volume_db", target_db, seconds)
	if stop_after:
		tween.tween_callback(player.stop)
	tween.finished.connect(_on_fade_finished.bind(player))
	_fades[player] = tween


func _on_fade_finished(player: AudioStreamPlayer) -> void:
	_fades.erase(player)


func _on_music_finished(player: AudioStreamPlayer) -> void:
	if player == _music_players[_music_slot]:
		player.play()


func _on_stinger_finished() -> void:
	_ducked = false
	_refresh_music_volume(crossfade_seconds)


func _db(linear: float) -> float:
	if linear <= 0.0:
		return MIN_DB
	return maxf(linear_to_db(linear), MIN_DB)


func _load_volumes() -> void:
	var config: ConfigFile = ConfigFile.new()
	if config.load(settings_path) != OK:
		return
	master_volume = _saved_volume(config, "master", master_volume)
	music_volume = _saved_volume(config, "music", music_volume)
	sfx_volume = _saved_volume(config, "sfx", sfx_volume)


func _saved_volume(config: ConfigFile, key: String, fallback: float) -> float:
	return clampf(float(config.get_value(VOLUMES_SECTION, key, fallback)), 0.0, 1.0)


func _save_volumes() -> void:
	var config: ConfigFile = ConfigFile.new()
	config.load(settings_path)
	config.set_value(VOLUMES_SECTION, "master", master_volume)
	config.set_value(VOLUMES_SECTION, "music", music_volume)
	config.set_value(VOLUMES_SECTION, "sfx", sfx_volume)
	var error: Error = config.save(settings_path)
	if error != OK:
		push_warning("NmgAudio: could not save the volumes to %s (error %d)" % [settings_path, error])
