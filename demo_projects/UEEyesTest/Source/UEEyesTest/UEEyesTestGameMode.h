// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "UEEyesTestGameMode.generated.h"

/**
 *  Simple GameMode for a third person game
 */
UCLASS(abstract)
class AUEEyesTestGameMode : public AGameModeBase
{
	GENERATED_BODY()

public:
	
	/** Constructor */
	AUEEyesTestGameMode();
};



