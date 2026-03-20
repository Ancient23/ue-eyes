// Copyright Epic Games, Inc. All Rights Reserved.

using UnrealBuildTool;

public class UEEyesTest : ModuleRules
{
	public UEEyesTest(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

		PublicDependencyModuleNames.AddRange(new string[] {
			"Core",
			"CoreUObject",
			"Engine",
			"InputCore",
			"EnhancedInput",
			"AIModule",
			"StateTreeModule",
			"GameplayStateTreeModule",
			"UMG",
			"Slate"
		});

		PrivateDependencyModuleNames.AddRange(new string[] { });

		PublicIncludePaths.AddRange(new string[] {
			"UEEyesTest",
			"UEEyesTest/Variant_Platforming",
			"UEEyesTest/Variant_Platforming/Animation",
			"UEEyesTest/Variant_Combat",
			"UEEyesTest/Variant_Combat/AI",
			"UEEyesTest/Variant_Combat/Animation",
			"UEEyesTest/Variant_Combat/Gameplay",
			"UEEyesTest/Variant_Combat/Interfaces",
			"UEEyesTest/Variant_Combat/UI",
			"UEEyesTest/Variant_SideScrolling",
			"UEEyesTest/Variant_SideScrolling/AI",
			"UEEyesTest/Variant_SideScrolling/Gameplay",
			"UEEyesTest/Variant_SideScrolling/Interfaces",
			"UEEyesTest/Variant_SideScrolling/UI"
		});

		// Uncomment if you are using Slate UI
		// PrivateDependencyModuleNames.AddRange(new string[] { "Slate", "SlateCore" });

		// Uncomment if you are using online features
		// PrivateDependencyModuleNames.Add("OnlineSubsystem");

		// To include OnlineSubsystemSteam, add it to the plugins section in your uproject file with the Enabled attribute set to true
	}
}
