#include "UEEyesModule.h"

#define LOCTEXT_NAMESPACE "FUEEyesModule"

void FUEEyesModule::StartupModule()
{
	UE_LOG(LogTemp, Log, TEXT("UEEyes: Module started"));
}

void FUEEyesModule::ShutdownModule()
{
	UE_LOG(LogTemp, Log, TEXT("UEEyes: Module shut down"));
}

#undef LOCTEXT_NAMESPACE

IMPLEMENT_MODULE(FUEEyesModule, UEEyes)
