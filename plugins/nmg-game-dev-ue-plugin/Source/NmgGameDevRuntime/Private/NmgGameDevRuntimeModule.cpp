// Copyright Nunley Media Group. All Rights Reserved.

#include "NmgGameDevPluginUtils.h"
#include "Modules/ModuleManager.h"

class FNmgGameDevRuntimeModule : public IModuleInterface
{
public:
    virtual void StartupModule() override
    {
        NmgGameDev::LogModuleInitialized(TEXT("NmgGameDevRuntime"));
    }

    virtual void ShutdownModule() override
    {
        NmgGameDev::LogModuleShutdown(TEXT("NmgGameDevRuntime"));
    }
};

IMPLEMENT_MODULE(FNmgGameDevRuntimeModule, NmgGameDevRuntime)
