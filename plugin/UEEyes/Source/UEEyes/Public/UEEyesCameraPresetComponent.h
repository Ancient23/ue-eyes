#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "UEEyesCameraPresetComponent.generated.h"

UENUM(BlueprintType)
enum class EUEEyesTrackingMode : uint8
{
	Fixed    UMETA(DisplayName = "Fixed"),
	LookAt   UMETA(DisplayName = "Look At"),
	Follow   UMETA(DisplayName = "Follow")
};

/**
 * Data component that marks an actor as a camera preset.
 * Attach to any actor to define a named capture viewpoint
 * with resolution, tracking mode, and optional target.
 */
UCLASS(ClassGroup=(UEEyes), meta=(BlueprintSpawnableComponent))
class UEEYES_API UUEEyesCameraPresetComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	UUEEyesCameraPresetComponent();

	/** Human-readable name used to look up this preset. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "UE Eyes")
	FString PresetName;

	/** Capture resolution in pixels (width x height). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "UE Eyes")
	FIntPoint Resolution = FIntPoint(1920, 1080);

	/** How the camera orients itself relative to the target. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "UE Eyes")
	EUEEyesTrackingMode TrackingMode = EUEEyesTrackingMode::Fixed;

	/** Optional actor to track (used by LookAt and Follow modes). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "UE Eyes")
	TSoftObjectPtr<AActor> TargetActor;

	/** Optional bone on the target actor to track. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "UE Eyes")
	FName TargetBone;

	/** World-space offset applied after tracking. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "UE Eyes")
	FVector Offset = FVector::ZeroVector;

	/** Free-form notes (displayed in editor details panel). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "UE Eyes")
	FString Notes;
};
