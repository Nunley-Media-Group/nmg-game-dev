// Copyright Nunley Media Group. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"

namespace NmgGameDev
{
    NMGGAMEDEVRUNTIME_API void LogModuleInitialized(const TCHAR* ModuleName);
    NMGGAMEDEVRUNTIME_API void LogModuleShutdown(const TCHAR* ModuleName);
}
