// Copyright Nunley Media Group. All Rights Reserved.

using UnrealBuildTool;

public class Dogfood : ModuleRules
{
    public Dogfood(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

        PublicDependencyModuleNames.AddRange(new string[]
        {
            "Core",
            "CoreUObject",
            "Engine",
        });
    }
}
