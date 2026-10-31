// Copyright Nunley Media Group. All Rights Reserved.

#include "NmgMissionDefinition.h"

FPrimaryAssetId UNmgMissionDefinition::GetPrimaryAssetId() const
{
    return FPrimaryAssetId(FName(TEXT("NmgMission")), GetFName());
}
