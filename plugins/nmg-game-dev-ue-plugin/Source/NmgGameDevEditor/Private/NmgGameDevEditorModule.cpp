// Copyright Nunley Media Group. All Rights Reserved.

#include "NmgGameDevPluginUtils.h"
#include "Modules/ModuleManager.h"

class FNmgGameDevEditorModule : public IModuleInterface
{
public:
    virtual void StartupModule() override
    {
        NmgGameDev::LogModuleInitialized(TEXT("NmgGameDevEditor"));
    }

    virtual void ShutdownModule() override
    {
        NmgGameDev::LogModuleShutdown(TEXT("NmgGameDevEditor"));
    }
};

IMPLEMENT_MODULE(FNmgGameDevEditorModule, NmgGameDevEditor)
