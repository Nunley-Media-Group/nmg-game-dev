// Copyright Nunley Media Group. All Rights Reserved.

#if WITH_DEV_AUTOMATION_TESTS

#include "CoreMinimal.h"
#include "Misc/AutomationTest.h"
#include "NmgAssetResolver.h"

// Mobile-platform positive coverage requires mocking UGameplayStatics::GetPlatformName, which
// is a compile-time query on a desktop CI host. Cover Mobile via a live IOS/Android build.

BEGIN_DEFINE_SPEC(FNmgAssetResolverSpec,
                  "NmgGameDev.Runtime.AssetResolver",
                  EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)
END_DEFINE_SPEC(FNmgAssetResolverSpec)

void FNmgAssetResolverSpec::Define()
{
    It("resolves Desktop variant on host desktop platforms", [this]()
    {
        const TArray<TPair<FString, FString>> Cases = {
            {TEXT("/Game/Weapons/Katana/Katana"),          TEXT("/Game/Weapons/Katana/Desktop/Katana")},
            {TEXT("/Game/Props/Crate/Crate"),              TEXT("/Game/Props/Crate/Desktop/Crate")},
            {TEXT("/Game/Characters/Hero/Hero"),           TEXT("/Game/Characters/Hero/Desktop/Hero")},
            {TEXT("/Game/Environments/Forest/Forest"),     TEXT("/Game/Environments/Forest/Desktop/Forest")},
        };

        for (const TPair<FString, FString>& Case : Cases)
        {
            const FSoftObjectPath Result = UNmgAssetResolver::ResolveVariantPath(FSoftObjectPath(Case.Key));
            TestEqual(FString::Printf(TEXT("'%s' resolves to Desktop variant"), *Case.Key),
                      Result.ToString(), Case.Value);
        }
    });

    It("returns input unchanged on path with /Desktop/ already present", [this]()
    {
        AddExpectedError(TEXT("does not match parent-path convention"), EAutomationExpectedErrorFlags::Contains, 1);

        const FSoftObjectPath Input(TEXT("/Game/Weapons/Katana/Desktop/Katana"));
        const FSoftObjectPath Result = UNmgAssetResolver::ResolveVariantPath(Input);
        TestEqual("Returned path equals the input (fail-closed)", Result.ToString(), Input.ToString());
    });

    It("returns input unchanged on path with /Mobile/ already present", [this]()
    {
        AddExpectedError(TEXT("does not match parent-path convention"), EAutomationExpectedErrorFlags::Contains, 1);

        const FSoftObjectPath Input(TEXT("/Game/Weapons/Katana/Mobile/Katana"));
        const FSoftObjectPath Result = UNmgAssetResolver::ResolveVariantPath(Input);
        TestEqual("Returned path equals the input (fail-closed)", Result.ToString(), Input.ToString());
    });

    It("returns input unchanged on too-short path", [this]()
    {
        AddExpectedError(TEXT("does not match parent-path convention"), EAutomationExpectedErrorFlags::Contains, 1);

        const FSoftObjectPath Input(TEXT("/Game/TooShort"));
        const FSoftObjectPath Result = UNmgAssetResolver::ResolveVariantPath(Input);
        TestEqual("Returned path equals the input (fail-closed)", Result.ToString(), Input.ToString());
    });

    It("returns input unchanged when asset name does not match parent folder name", [this]()
    {
        AddExpectedError(TEXT("does not match parent-path convention"), EAutomationExpectedErrorFlags::Contains, 1);

        const FSoftObjectPath Input(TEXT("/Game/Foo/Bar.Bar_C"));
        const FSoftObjectPath Result = UNmgAssetResolver::ResolveVariantPath(Input);
        TestEqual("Returned path equals the input (fail-closed)", Result.ToString(), Input.ToString());
    });

    It("emits a single LogNmgGameDev warning per malformed input", [this]()
    {
        AddExpectedError(TEXT("does not match parent-path convention"), EAutomationExpectedErrorFlags::Contains, 1);

        UNmgAssetResolver::ResolveVariantPath(FSoftObjectPath(TEXT("/Game/Weapons/Katana/Desktop/Katana")));
    });
}

#endif // WITH_DEV_AUTOMATION_TESTS
