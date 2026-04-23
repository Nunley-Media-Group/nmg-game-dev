// Copyright Nunley Media Group. All Rights Reserved.

using UnrealBuildTool;

public class NmgGameDevRuntime : ModuleRules
{
    public NmgGameDevRuntime(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

        PublicDependencyModuleNames.AddRange(new string[]
        {
            "Core",
            "CoreUObject",
            "Engine",
            "Projects",
        });

        // No PrivateDependencyModuleNames needed for this module.
        // No editor-only modules (UnrealEd, Slate, EditorSubsystem, etc.) may appear here —
        // this module cooks into shipped game binaries. Adding any editor dep breaks AC3 (cook isolation).
    }
}
