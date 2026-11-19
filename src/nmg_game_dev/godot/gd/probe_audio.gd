# Headless probe for one imported audio stream (#249 FR5).
#
# Run as: godot --headless --path <project> -s <this script> -- <params.json>
# Params: {"stream": "res://assets/Audio/<Name>.wav"} (or .ogg)
# Prints exactly one line:
#   NMG_RESULT {"class": "AudioStreamWAV", "loop_mode": <AudioStreamWAV.LoopMode>}
#   NMG_RESULT {"class": "AudioStreamOggVorbis", "loop": <bool>}
# Other stream classes report only "class".
extends SceneTree


func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	if args.is_empty():
		push_error("probe_audio.gd needs the params JSON path after --")
		quit(1)
		return
	var params: Variant = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
	if not params is Dictionary:
		push_error("probe_audio.gd could not read params from %s" % args[0])
		quit(1)
		return
	var stream := load(String(params["stream"])) as AudioStream
	if stream == null:
		push_error("probe_audio.gd could not load %s" % params["stream"])
		quit(1)
		return
	var result := {"class": stream.get_class()}
	if stream is AudioStreamWAV:
		result["loop_mode"] = int((stream as AudioStreamWAV).loop_mode)
	elif stream is AudioStreamOggVorbis:
		result["loop"] = (stream as AudioStreamOggVorbis).loop
	print("NMG_RESULT " + JSON.stringify(result))
	quit(0)
