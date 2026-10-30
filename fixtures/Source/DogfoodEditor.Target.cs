// Copyright Nunley Media Group. All Rights Reserved.

using UnrealBuildTool;

public class DogfoodEditorTarget : TargetRules
{
    public DogfoodEditorTarget(TargetInfo Target) : base(Target)
    {
        Type = TargetType.Editor;
        DefaultBuildSettings = BuildSettingsVersion.Latest;
        IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
        ExtraModuleNames.Add("Dogfood");
    }
}
