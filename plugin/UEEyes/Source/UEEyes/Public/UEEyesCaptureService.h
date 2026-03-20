#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "UEEyesCaptureService.generated.h"

class UUEEyesCameraPresetComponent;

/**
 * Actor that manages SceneCapture2D lifecycle for AI agent visual access.
 * Spawn one in the level, then call CaptureFromPreset or CaptureFromViewport
 * to produce PNG screenshots on disk.
 */
UCLASS()
class UEEYES_API AUEEyesCaptureService : public AActor
{
	GENERATED_BODY()

public:
	AUEEyesCaptureService();

	/**
	 * Capture a frame from the named camera preset and save to OutputDir.
	 * @param PresetName  Name matching a UUEEyesCameraPresetComponent in the level.
	 * @param OutputDir   Directory on disk where the PNG will be written.
	 * @return true if capture and export succeeded.
	 */
	UFUNCTION(BlueprintCallable, Category = "UE Eyes")
	bool CaptureFromPreset(const FString& PresetName, const FString& OutputDir);

	/**
	 * Capture a frame from the current viewport (PIE) camera and save to OutputDir.
	 * @param OutputDir  Directory on disk where the PNG will be written.
	 * @return true if capture and export succeeded.
	 */
	UFUNCTION(BlueprintCallable, Category = "UE Eyes")
	bool CaptureFromViewport(const FString& OutputDir);

private:
	/** Find the first actor with a UUEEyesCameraPresetComponent whose PresetName matches. */
	UUEEyesCameraPresetComponent* FindPreset(const FString& PresetName) const;

	/** Spawn a transient SceneCapture2D, capture, export to PNG, and clean up. */
	bool CaptureAtTransform(const FVector& Location, const FRotator& Rotation,
	                        const FIntPoint& Resolution, const FString& OutputDir);
};
