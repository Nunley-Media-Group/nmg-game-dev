// Copyright Nunley Media Group. All Rights Reserved.

using UnrealBuildTool;

public class NmgGameDevEditor : ModuleRules
{
    public NmgGameDevEditor(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

        // Public deps re-exported to anything that depends on NmgGameDevEditor.
        // NmgGameDevRuntime is Public so editor tools can call into the runtime resolver.
        // UnrealEd is Private — no public Editor headers expose it in this skeleton.
        PublicDependencyModuleNames.AddRange(new string[]
        {
            "Core",
            "CoreUObject",
            "Engine",
            "NmgGameDevRuntime",
        });

        // UnrealEd is Private per design § Alternatives E — do not promote to Public unless
        // a concrete consumer of the type appears in a public header.
        PrivateDependencyModuleNames.AddRange(new string[]
        {
            "UnrealEd",
        });
    }
}
