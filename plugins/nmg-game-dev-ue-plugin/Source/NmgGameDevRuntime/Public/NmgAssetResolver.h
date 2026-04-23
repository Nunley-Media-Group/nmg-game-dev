#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "NmgAssetResolver.generated.h"

UCLASS()
class NMGGAMEDEVRUNTIME_API UNmgAssetResolver : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()

public:
    /**
     * Resolve a parent asset path (no variant subfolder) to its platform-appropriate
     * Desktop/ or Mobile/ variant. See steering/structure.md § split-variant convention.
     *
     * The "parent path" convention: the path ends with <ParentFolder>/<AssetName> where
     * <AssetName> matches <ParentFolder>, with no Desktop/ or Mobile/ subfolder present.
     * Example: /Game/Weapons/Katana/Katana → /Game/Weapons/Katana/Desktop/Katana (on Mac).
     *
     * Platform routing:
     *   Windows, Mac, Linux  → Desktop/ variant
     *   IOS, Android         → Mobile/ variant
     *   Unknown platforms    → Desktop/ variant + LogNmgGameDev Warning
     *
     * On malformed input, logs a LogNmgGameDev warning and returns the input unchanged
     * (never crashes, never returns an empty path).
     */
    UFUNCTION(BlueprintPure, Category = "nmg-game-dev|Variants",
              meta = (DisplayName = "Resolve Variant Path"))
    static FSoftObjectPath ResolveVariantPath(const FSoftObjectPath& ParentPath);
};
