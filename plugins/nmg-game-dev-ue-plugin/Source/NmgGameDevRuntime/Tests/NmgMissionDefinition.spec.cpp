// Copyright Nunley Media Group. All Rights Reserved.

#if WITH_DEV_AUTOMATION_TESTS

#include "CoreMinimal.h"
#include "Misc/AutomationTest.h"
#include "NmgMissionDefinition.h"

BEGIN_DEFINE_SPEC(FNmgMissionDefinitionSpec,
                  "NmgGameDev.Runtime.MissionDefinition",
                  EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)
END_DEFINE_SPEC(FNmgMissionDefinitionSpec)

void FNmgMissionDefinitionSpec::Define()
{
    It("holds the fields the scaffold writes", [this]()
    {
        UNmgMissionDefinition* Mission = NewObject<UNmgMissionDefinition>(GetTransientPackage());
        Mission->MissionName = TEXT("First Light");
        Mission->Act = 2;
        Mission->Region = FName(TEXT("OldTown"));
        Mission->DependsOn = {FName(TEXT("Crate")), FName(TEXT("FirstStep"))};
        Mission->DesignDocPath = TEXT("docs/design/missions/first-light.md");

        TestEqual(TEXT("MissionName"), Mission->MissionName, FString(TEXT("First Light")));
        TestEqual(TEXT("Act"), Mission->Act, 2);
        TestEqual(TEXT("Region"), Mission->Region, FName(TEXT("OldTown")));
        TestEqual(TEXT("DependsOn count"), Mission->DependsOn.Num(), 2);
        TestEqual(TEXT("DependsOn[0]"), Mission->DependsOn[0], FName(TEXT("Crate")));
        TestEqual(TEXT("DesignDocPath"), Mission->DesignDocPath,
                  FString(TEXT("docs/design/missions/first-light.md")));
    });

    It("reports the NmgMission primary asset type", [this]()
    {
        UNmgMissionDefinition* Mission = NewObject<UNmgMissionDefinition>(GetTransientPackage(),
                                                                          TEXT("DA_FirstLight"));
        const FPrimaryAssetId Id = Mission->GetPrimaryAssetId();

        TestEqual(TEXT("PrimaryAssetType"), Id.PrimaryAssetType.GetName(), FName(TEXT("NmgMission")));
        TestEqual(TEXT("PrimaryAssetName"), Id.PrimaryAssetName, FName(TEXT("DA_FirstLight")));
    });
}

#endif // WITH_DEV_AUTOMATION_TESTS
