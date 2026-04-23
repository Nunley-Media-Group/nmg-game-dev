// Copyright Nunley Media Group. All Rights Reserved.

#include "NmgAssetResolver.h"
#include "NmgGameDevLog.h"
#include "Kismet/GameplayStatics.h"
#include "Misc/Paths.h"

FSoftObjectPath UNmgAssetResolver::ResolveVariantPath(const FSoftObjectPath& ParentPath)
{
    const FString PackagePath = ParentPath.GetLongPackageName();

    if (PackagePath.IsEmpty())
    {
        UE_LOG(LogNmgGameDev, Warning,
               TEXT("ResolveVariantPath: input '%s' does not match parent-path convention (empty package path); returning unchanged."),
               *ParentPath.ToString());
        return ParentPath;
    }

    if (PackagePath.Contains(TEXT("/Desktop/")) || PackagePath.Contains(TEXT("/Mobile/")))
    {
        UE_LOG(LogNmgGameDev, Warning,
               TEXT("ResolveVariantPath: input '%s' does not match parent-path convention (path already contains /Desktop/ or /Mobile/); returning unchanged."),
               *PackagePath);
        return ParentPath;
    }

    const FString AssetName = FPaths::GetCleanFilename(PackagePath);
    const FString ParentDir = FPaths::GetPath(PackagePath);
    const FString ParentFolder = FPaths::GetCleanFilename(ParentDir);

    if (ParentDir.IsEmpty() || ParentFolder.IsEmpty() ||
        !ParentFolder.Equals(AssetName, ESearchCase::CaseSensitive))
    {
        UE_LOG(LogNmgGameDev, Warning,
               TEXT("ResolveVariantPath: input '%s' does not match parent-path convention (asset name '%s' does not match parent folder '%s'); returning unchanged."),
               *PackagePath, *AssetName, *ParentFolder);
        return ParentPath;
    }

    FString Variant = TEXT("Desktop");
    const FString PlatformName = UGameplayStatics::GetPlatformName();
    if (PlatformName == TEXT("IOS") || PlatformName == TEXT("Android"))
    {
        Variant = TEXT("Mobile");
    }
    else if (PlatformName != TEXT("Windows") && PlatformName != TEXT("Mac") && PlatformName != TEXT("Linux"))
    {
        UE_LOG(LogNmgGameDev, Warning,
               TEXT("ResolveVariantPath: unknown platform '%s'; defaulting to Desktop variant."),
               *PlatformName);
    }

    return FSoftObjectPath(FString::Printf(TEXT("%s/%s/%s"), *ParentDir, *Variant, *AssetName));
}
