// Four-layer splat shader for finalized terrain (nmg-game-dev).
//
// splat is the RGBA weightmap T_<Name>_Splat.png: layer i is weighted by channel i. The weights
// are linear data, so splat is not declared source_color (that would sRGB-decode them). Each layer has
// base color (BC), normal (N), and occlusion-roughness-metallic (ORM) textures, tiled by uv_scale.
shader_type spatial;

uniform sampler2D splat : filter_linear, repeat_disable;

uniform sampler2D layer0_bc : source_color, filter_linear_mipmap, repeat_enable;
uniform sampler2D layer0_n : hint_normal, filter_linear_mipmap, repeat_enable;
uniform sampler2D layer0_orm : filter_linear_mipmap, repeat_enable;

uniform sampler2D layer1_bc : source_color, filter_linear_mipmap, repeat_enable;
uniform sampler2D layer1_n : hint_normal, filter_linear_mipmap, repeat_enable;
uniform sampler2D layer1_orm : filter_linear_mipmap, repeat_enable;

uniform sampler2D layer2_bc : source_color, filter_linear_mipmap, repeat_enable;
uniform sampler2D layer2_n : hint_normal, filter_linear_mipmap, repeat_enable;
uniform sampler2D layer2_orm : filter_linear_mipmap, repeat_enable;

uniform sampler2D layer3_bc : source_color, filter_linear_mipmap, repeat_enable;
uniform sampler2D layer3_n : hint_normal, filter_linear_mipmap, repeat_enable;
uniform sampler2D layer3_orm : filter_linear_mipmap, repeat_enable;

uniform float uv_scale = 16.0;

void fragment() {
	vec4 weights = texture(splat, UV);
	float total = max(weights.r + weights.g + weights.b + weights.a, 0.0001);
	weights /= total;
	vec2 tiled = UV * uv_scale;

	vec3 albedo = texture(layer0_bc, tiled).rgb * weights.r
		+ texture(layer1_bc, tiled).rgb * weights.g
		+ texture(layer2_bc, tiled).rgb * weights.b
		+ texture(layer3_bc, tiled).rgb * weights.a;
	vec3 normal = texture(layer0_n, tiled).rgb * weights.r
		+ texture(layer1_n, tiled).rgb * weights.g
		+ texture(layer2_n, tiled).rgb * weights.b
		+ texture(layer3_n, tiled).rgb * weights.a;
	vec3 orm = texture(layer0_orm, tiled).rgb * weights.r
		+ texture(layer1_orm, tiled).rgb * weights.g
		+ texture(layer2_orm, tiled).rgb * weights.b
		+ texture(layer3_orm, tiled).rgb * weights.a;

	ALBEDO = albedo;
	NORMAL_MAP = normal;
	AO = orm.r;
	ROUGHNESS = orm.g;
	METALLIC = orm.b;
}
