// Copyright Nunley Media Group. All Rights Reserved.

using UnrealBuildTool;

public class DogfoodTarget : TargetRules
{
    public DogfoodTarget(TargetInfo Target) : base(Target)
    {
        Type = TargetType.Game;
        DefaultBuildSettings = BuildSettingsVersion.Latest;
        IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
        ExtraModuleNames.Add("Dogfood");
    }
}
