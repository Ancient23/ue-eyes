#include "UEEyesCaptureService.h"
#include "UEEyesCameraPresetComponent.h"

#include "Engine/TextureRenderTarget2D.h"
#include "Engine/World.h"
#include "Components/SceneCaptureComponent2D.h"
#include "Kismet/KismetRenderingLibrary.h"
#include "Kismet/GameplayStatics.h"
#include "GameFramework/PlayerController.h"
#include "Misc/Paths.h"

AUEEyesCaptureService::AUEEyesCaptureService()
{
	PrimaryActorTick.bCanEverTick = false;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

bool AUEEyesCaptureService::CaptureFromPreset(const FString& PresetName, const FString& OutputDir)
{
	UUEEyesCameraPresetComponent* Preset = FindPreset(PresetName);
	if (!Preset)
	{
		UE_LOG(LogTemp, Warning, TEXT("UEEyes: Preset '%s' not found"), *PresetName);
		return false;
	}

	AActor* PresetOwner = Preset->GetOwner();
	if (!PresetOwner)
	{
		UE_LOG(LogTemp, Warning, TEXT("UEEyes: Preset '%s' has no owning actor"), *PresetName);
		return false;
	}

	FVector Location = PresetOwner->GetActorLocation() + Preset->Offset;
	FRotator Rotation = PresetOwner->GetActorRotation();

	// Apply tracking mode
	if (Preset->TrackingMode != EUEEyesTrackingMode::Fixed)
	{
		AActor* Target = Preset->TargetActor.Get();
		if (Target)
		{
			FVector TargetLocation = Target->GetActorLocation();

			if (Preset->TrackingMode == EUEEyesTrackingMode::LookAt)
			{
				// Rotate to face the target from the preset position
				FVector Direction = TargetLocation - Location;
				Rotation = Direction.Rotation();
			}
			else if (Preset->TrackingMode == EUEEyesTrackingMode::Follow)
			{
				// Move to target location + offset, keep preset rotation
				Location = TargetLocation + Preset->Offset;
			}
		}
		else
		{
			UE_LOG(LogTemp, Warning,
				TEXT("UEEyes: Preset '%s' has tracking mode but no valid TargetActor"),
				*PresetName);
		}
	}

	return CaptureAtTransform(Location, Rotation, Preset->Resolution, OutputDir);
}

bool AUEEyesCaptureService::CaptureFromViewport(const FString& OutputDir)
{
	UWorld* World = GetWorld();
	if (!World)
	{
		UE_LOG(LogTemp, Warning, TEXT("UEEyes: No world available"));
		return false;
	}

	APlayerController* PC = World->GetFirstPlayerController();
	if (!PC)
	{
		UE_LOG(LogTemp, Warning, TEXT("UEEyes: No player controller available"));
		return false;
	}

	FVector Location;
	FRotator Rotation;
	PC->GetPlayerViewPoint(Location, Rotation);

	const FIntPoint DefaultResolution(1920, 1080);
	return CaptureAtTransform(Location, Rotation, DefaultResolution, OutputDir);
}

// ---------------------------------------------------------------------------
// Private helpers
// ---------------------------------------------------------------------------

UUEEyesCameraPresetComponent* AUEEyesCaptureService::FindPreset(const FString& PresetName) const
{
	UWorld* World = GetWorld();
	if (!World)
	{
		return nullptr;
	}

	TArray<AActor*> AllActors;
	UGameplayStatics::GetAllActorsOfClass(World, AActor::StaticClass(), AllActors);

	for (AActor* Actor : AllActors)
	{
		UUEEyesCameraPresetComponent* Comp =
			Actor->FindComponentByClass<UUEEyesCameraPresetComponent>();
		if (Comp && Comp->PresetName == PresetName)
		{
			return Comp;
		}
	}

	return nullptr;
}

bool AUEEyesCaptureService::CaptureAtTransform(
	const FVector& Location,
	const FRotator& Rotation,
	const FIntPoint& Resolution,
	const FString& OutputDir)
{
	UWorld* World = GetWorld();
	if (!World)
	{
		UE_LOG(LogTemp, Warning, TEXT("UEEyes: No world for capture"));
		return false;
	}

	// 1. Create a transient render target
	UTextureRenderTarget2D* RenderTarget = NewObject<UTextureRenderTarget2D>(this);
	RenderTarget->InitAutoFormat(Resolution.X, Resolution.Y);
	RenderTarget->RenderTargetFormat = RTF_RGBA8;

	// 2. Create a transient SceneCaptureComponent2D attached to this actor
	USceneCaptureComponent2D* CaptureComp = NewObject<USceneCaptureComponent2D>(this);
	CaptureComp->RegisterComponentWithWorld(World);
	CaptureComp->SetWorldLocationAndRotation(Location, Rotation);
	CaptureComp->TextureTarget = RenderTarget;
	CaptureComp->CaptureSource = ESceneCaptureSource::SCS_FinalColorLDR;

	// 3. Capture the scene
	CaptureComp->CaptureScene();

	// 4. Build output file path
	FString SafeOutputDir = OutputDir;
	FPaths::NormalizeDirectoryName(SafeOutputDir);

	// Ensure directory exists
	IPlatformFile& PlatformFile = FPlatformFileManager::Get().GetPlatformFile();
	PlatformFile.CreateDirectoryTree(*SafeOutputDir);

	const FString Timestamp = FDateTime::Now().ToString(TEXT("%Y%m%d_%H%M%S"));
	const FString Filename = FString::Printf(TEXT("capture_%s.png"), *Timestamp);
	const FString FullPath = FPaths::Combine(SafeOutputDir, Filename);

	// 5. Export render target to PNG on disk
	UKismetRenderingLibrary::ExportRenderTarget(
		World, RenderTarget, SafeOutputDir, Filename);

	UE_LOG(LogTemp, Log, TEXT("UEEyes: Captured to %s"), *FullPath);

	// 6. Clean up
	CaptureComp->DestroyComponent();

	return true;
}
