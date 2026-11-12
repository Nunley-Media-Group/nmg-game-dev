// Copyright Nunley Media Group. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "NmgLandscapeLibrary.generated.h"

class ALandscape;
class ALandscapeProxy;
class UMaterial;
class UMaterialInterface;
class ULandscapeLayerInfoObject;
class UTexture;
class UWorld;

/**
 * Editor-only helpers for the terrain import (#154). The generated UE Python for a terrain variant
 * calls these statics in order: create the layer infos and the landscape material, then import the
 * Landscape and sample its heights.
 *
 * Each static logs an error and returns nullptr (or an empty array) on failure, so the Python caller
 * can report the failure through its NMG_RESULT.
 */
UCLASS()
class NMGGAMEDEVEDITOR_API UNmgLandscapeLibrary : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()

public:
    /**
     * Creates and saves the landscape material <Dest>/<Name>. For each layer it adds one
     * LandscapeLayerCoords node (scaled by MappingScale) and one texture sample per texture. The
     * samples feed three LandscapeLayerBlend nodes (base color, normal, ORM), each set to LB_WeightBlend
     * with the layer name, so the blend follows the painted weightmap of the same name.
     * ORM R, G, and B drive Ambient Occlusion, Roughness, and Metallic.
     *
     * @param Dest         Package folder, for example /Game/Terrain/Foo/Desktop.
     * @param Name         Material asset name, for example M_Foo_Landscape.
     * @param Layers       Layer names in weightmap order. Each must match a layer info LayerName.
     * @param BC           One base color texture per layer, in Layers order.
     * @param N            One normal texture per layer, in Layers order.
     * @param ORM          One ORM texture per layer, in Layers order.
     * @param MappingScale Layer coordinate scale (uv_tile_m / spacing_m). Must be positive.
     * @return The saved material, or nullptr.
     */
    UFUNCTION(BlueprintCallable, Category = "nmg-game-dev|Landscape")
    static UMaterial* BuildLayeredMaterial(const FString& Dest, const FString& Name, const TArray<FString>& Layers,
                                           const TArray<UTexture*>& BC, const TArray<UTexture*>& N,
                                           const TArray<UTexture*>& ORM, float MappingScale);

    /**
     * Creates and saves the layer info asset <Dest>/<Name>. Its LayerName is Layer, which must match the
     * layer name used in BuildLayeredMaterial and the weightmap it is imported with.
     *
     * @return The saved layer info, or nullptr.
     */
    UFUNCTION(BlueprintCallable, Category = "nmg-game-dev|Landscape")
    static ULandscapeLayerInfoObject* CreateLayerInfo(const FString& Dest, const FString& Name,
                                                      const FString& Layer);

    /**
     * Spawns an ALandscape at Location with the given Scale and imports the heightmap and weightmaps.
     * The landscape uses one section per component with 63 quads, so there are (N - 1) / 63
     * components per side. It has one import layer per weightmap, with additive weights.
     *
     * @param World       Editor world to spawn into.
     * @param HeightmapPath  Path to a 16-bit grayscale PNG of N x N samples.
     * @param WeightmapPaths One 8-bit grayscale PNG per layer, in LayerInfos order.
     * @param LayerInfos  One layer info per weightmap.
     * @param Material    Landscape material built by BuildLayeredMaterial.
     * @param N           Vertices per side. Must satisfy (N - 1) % 63 == 0.
     * @param Location    Actor location in cm.
     * @param Scale       Actor scale: X and Y are the spacing in cm, Z is the height scale.
     * @return The spawned landscape, or nullptr.
     */
    UFUNCTION(BlueprintCallable, Category = "nmg-game-dev|Landscape")
    static ALandscape* ImportLandscape(UWorld* World, const FString& HeightmapPath,
                                       const TArray<FString>& WeightmapPaths,
                                       const TArray<ULandscapeLayerInfoObject*>& LayerInfos,
                                       UMaterialInterface* Material, int32 N, const FVector& Location,
                                       const FVector& Scale);

    /**
     * Returns the landscape height (world Z, cm) at each XY point (world X and Y, cm). A point the
     * landscape does not cover yields NaN, so a comparison against it fails.
     */
    UFUNCTION(BlueprintCallable, Category = "nmg-game-dev|Landscape")
    static TArray<float> SampleHeights(ALandscapeProxy* Landscape, const TArray<FVector2D>& XY);
};
