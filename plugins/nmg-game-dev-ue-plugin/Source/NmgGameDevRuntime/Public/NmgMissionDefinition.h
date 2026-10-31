// Copyright Nunley Media Group. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Engine/DataAsset.h"
#include "NmgMissionDefinition.generated.h"

/**
 * Data asset for one mission.  The design scaffold creates these from a docs/design mission entry
 * (#112 FR6).  The asset's primary asset type is NmgMission.
 */
UCLASS(BlueprintType)
class NMGGAMEDEVRUNTIME_API UNmgMissionDefinition : public UPrimaryDataAsset
{
    GENERATED_BODY()

public:
    /** The mission's display name, from the design entry's name. */
    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Mission")
    FString MissionName;

    /** The act the mission belongs to.  0 when the design entry names no act. */
    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Mission")
    int32 Act = 0;

    /** The asset name of the region the mission takes place in, or None. */
    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Mission")
    FName Region;

    /** The asset names of the missions and other entries this mission depends on. */
    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Mission")
    TArray<FName> DependsOn;

    /** The design doc this asset was scaffolded from, relative to the project root. */
    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Mission")
    FString DesignDocPath;

    virtual FPrimaryAssetId GetPrimaryAssetId() const override;
};
