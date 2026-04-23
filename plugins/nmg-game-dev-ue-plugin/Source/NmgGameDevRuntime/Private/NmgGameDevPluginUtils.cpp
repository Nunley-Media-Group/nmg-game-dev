// Copyright Nunley Media Group. All Rights Reserved.

#include "NmgGameDevPluginUtils.h"
#include "NmgGameDevLog.h"
#include "Interfaces/IPluginManager.h"

namespace NmgGameDev
{
    void LogModuleInitialized(const TCHAR* ModuleName)
    {
        FString VersionName = TEXT("unknown");
        const TSharedPtr<IPlugin> Plugin = IPluginManager::Get().FindPlugin(TEXT("nmg-game-dev"));
        if (Plugin.IsValid())
        {
            VersionName = Plugin->GetDescriptor().VersionName;
        }
        else
        {
            UE_LOG(LogNmgGameDev, Warning,
                   TEXT("%s: IPluginManager could not locate the 'nmg-game-dev' plugin descriptor; version reported as 'unknown'."),
                   ModuleName);
        }

        UE_LOG(LogNmgGameDev, Display, TEXT("%s Initialized v%s"), ModuleName, *VersionName);
    }

    void LogModuleShutdown(const TCHAR* ModuleName)
    {
        UE_LOG(LogNmgGameDev, Display, TEXT("%s Shutdown"), ModuleName);
    }
}
