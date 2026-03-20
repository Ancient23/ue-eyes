#pragma once

#include "Modules/ModuleManager.h"

class FUEEyesModule : public IModuleInterface
{
public:
	virtual void StartupModule() override;
	virtual void ShutdownModule() override;
};
