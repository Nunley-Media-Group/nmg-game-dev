class_name NmgAudioTable
extends Resource
## The name table an NmgAudio component plays from (#237).
##
## sounds maps each sound name to its res:// stream path (an AudioStreamWAV or
## AudioStreamOggVorbis). themes maps a region's scene name to the music name that plays while
## that scene is current.
## python -m nmg_game_dev.audio refresh rewrites both from the imported files and the design
## backlog.

@export var sounds: Dictionary = {}
@export var themes: Dictionary = {}
