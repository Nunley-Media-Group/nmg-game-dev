// Copyright Nunley Media Group. All Rights Reserved.

#include "NmgLandscapeLibrary.h"

#include "Engine/Texture.h"
#include "Engine/World.h"
#include "IImageWrapper.h"
#include "IImageWrapperModule.h"
#include "Landscape.h"
#include "LandscapeInfo.h"
#include "LandscapeLayerInfoObject.h"
#include "LandscapeProxy.h"
#include "MaterialEditingLibrary.h"
#include "Materials/Material.h"
#include "Materials/MaterialExpressionComponentMask.h"
#include "Materials/MaterialExpressionLandscapeLayerBlend.h"
#include "Materials/MaterialExpressionLandscapeLayerCoords.h"
#include "Materials/MaterialExpressionTextureSample.h"
#include "Misc/FileHelper.h"
#include "Misc/PackageName.h"
#include "Modules/ModuleManager.h"
#include "UObject/Package.h"
#include "UObject/SavePackage.h"
#include "UObject/UObjectGlobals.h"
#include <limits>

DEFINE_LOG_CATEGORY_STATIC(LogNmgLandscape, Log, All);

namespace
{
    /** Landscape components are one section of 63 quads each (#154 FR6). */
    constexpr int32 SectionQuads = 63;

    FString PackageNameFor(const FString& Dest, const FString& Name)
    {
        return Dest.EndsWith(TEXT("/")) ? Dest + Name : Dest + TEXT("/") + Name;
    }

    /** Renames an asset already loaded under Package out of the way so the new asset can take its name. */
    void MoveAsideExistingAsset(UPackage* Package, const FString& Name)
    {
        if (UObject* Existing = FindObject<UObject>(Package, *Name))
        {
            Existing->Rename(nullptr, GetTransientPackage(), REN_DontCreateRedirectors | REN_NonTransactional);
        }
    }

    bool SaveAsset(UPackage* Package, UObject* Asset)
    {
        FString Filename;
        if (!FPackageName::TryConvertLongPackageNameToFilename(Package->GetName(), Filename,
                                                               FPackageName::GetAssetPackageExtension()))
        {
            UE_LOG(LogNmgLandscape, Error, TEXT("Cannot map package '%s' to a file path."), *Package->GetName());
            return false;
        }

        FSavePackageArgs SaveArgs;
        SaveArgs.TopLevelFlags = RF_Public | RF_Standalone;
        if (!UPackage::SavePackage(Package, Asset, *Filename, SaveArgs))
        {
            UE_LOG(LogNmgLandscape, Error, TEXT("Failed to save '%s'."), *Package->GetName());
            return false;
        }
        return true;
    }

    template <typename ExpressionType>
    ExpressionType* CreateExpression(UMaterial* Material, int32 NodePosX, int32 NodePosY)
    {
        return Cast<ExpressionType>(
            UMaterialEditingLibrary::CreateMaterialExpression(Material, ExpressionType::StaticClass(), NodePosX, NodePosY));
    }

    UMaterialExpressionTextureSample* CreateTextureSample(UMaterial* Material, UTexture* Texture,
                                                          EMaterialSamplerType SamplerType,
                                                          UMaterialExpression* Coordinates, int32 NodePosX,
                                                          int32 NodePosY)
    {
        UMaterialExpressionTextureSample* Sample =
            CreateExpression<UMaterialExpressionTextureSample>(Material, NodePosX, NodePosY);
        Sample->Texture = Texture;
        Sample->SamplerType = SamplerType;
        Sample->Coordinates.Connect(0, Coordinates);
        return Sample;
    }

    void AddLayerInput(UMaterialExpressionLandscapeLayerBlend* Blend, const FString& LayerName,
                       UMaterialExpression* LayerSource)
    {
        FLayerBlendInput& Input = Blend->Layers.AddDefaulted_GetRef();
        Input.LayerName = FName(*LayerName);
        Input.BlendType = LB_WeightBlend;
        Input.LayerInput.Connect(0, LayerSource);
    }

    UMaterialExpressionComponentMask* CreateChannelMask(UMaterial* Material, UMaterialExpression* Source,
                                                        bool bRed, bool bGreen, bool bBlue, int32 NodePosX,
                                                        int32 NodePosY)
    {
        UMaterialExpressionComponentMask* Mask =
            CreateExpression<UMaterialExpressionComponentMask>(Material, NodePosX, NodePosY);
        Mask->R = bRed;
        Mask->G = bGreen;
        Mask->B = bBlue;
        Mask->A = false;
        Mask->Input.Connect(0, Source);
        return Mask;
    }

    /**
     * Decodes a square grayscale PNG into OutSamples, row 0 first. The file must hold Side x Side
     * pixels at BitDepth bits per sample. The 16-bit path returns native byte order, because
     * IImageWrapper swaps PNG's big-endian samples on little-endian platforms.
     */
    template <typename SampleType>
    bool LoadGrayscalePng(const FString& Path, int32 Side, int32 BitDepth, TArray<SampleType>& OutSamples)
    {
        TArray64<uint8> FileData;
        if (!FFileHelper::LoadFileToArray(FileData, *Path))
        {
            UE_LOG(LogNmgLandscape, Error, TEXT("Cannot read '%s'."), *Path);
            return false;
        }

        IImageWrapperModule& ImageWrapperModule =
            FModuleManager::LoadModuleChecked<IImageWrapperModule>(FName("ImageWrapper"));
        const TSharedPtr<IImageWrapper> Wrapper = ImageWrapperModule.CreateImageWrapper(EImageFormat::PNG);
        if (!Wrapper.IsValid() || !Wrapper->SetCompressed(FileData.GetData(), FileData.Num()))
        {
            UE_LOG(LogNmgLandscape, Error, TEXT("'%s' is not a readable PNG."), *Path);
            return false;
        }

        if (Wrapper->GetWidth() != Side || Wrapper->GetHeight() != Side || Wrapper->GetFormat() != ERGBFormat::Gray ||
            Wrapper->GetBitDepth() != BitDepth)
        {
            UE_LOG(LogNmgLandscape, Error, TEXT("'%s' must be a %dx%d grayscale PNG at %d bits per sample."), *Path,
                   Side, Side, BitDepth);
            return false;
        }

        const int64 ExpectedBytes = static_cast<int64>(Side) * Side * sizeof(SampleType);
        TArray64<uint8> Raw;
        if (!Wrapper->GetRaw(Raw) || Raw.Num() != ExpectedBytes)
        {
            UE_LOG(LogNmgLandscape, Error, TEXT("Decoding '%s' produced the wrong byte count."), *Path);
            return false;
        }

        OutSamples.SetNumUninitialized(Side * Side);
        FMemory::Memcpy(OutSamples.GetData(), Raw.GetData(), static_cast<SIZE_T>(ExpectedBytes));
        return true;
    }
}

UMaterial* UNmgLandscapeLibrary::BuildLayeredMaterial(const FString& Dest, const FString& Name,
                                                      const TArray<FString>& Layers,
                                                      const TArray<UTexture*>& BC, const TArray<UTexture*>& N,
                                                      const TArray<UTexture*>& ORM, float MappingScale)
{
    const int32 LayerCount = Layers.Num();
    if (LayerCount == 0 || BC.Num() != LayerCount || N.Num() != LayerCount || ORM.Num() != LayerCount ||
        MappingScale <= 0.0f)
    {
        UE_LOG(LogNmgLandscape, Error,
               TEXT("BuildLayeredMaterial '%s': expected one BC, N, and ORM texture per layer (%d layers) and a positive MappingScale."),
               *Name, LayerCount);
        return nullptr;
    }

    for (int32 LayerIndex = 0; LayerIndex < LayerCount; ++LayerIndex)
    {
        if (!BC[LayerIndex] || !N[LayerIndex] || !ORM[LayerIndex])
        {
            UE_LOG(LogNmgLandscape, Error, TEXT("BuildLayeredMaterial '%s': layer %d is missing a texture."), *Name,
                   LayerIndex);
            return nullptr;
        }
    }

    UPackage* Package = CreatePackage(*PackageNameFor(Dest, Name));
    MoveAsideExistingAsset(Package, Name);
    UMaterial* Material = NewObject<UMaterial>(Package, FName(*Name), RF_Public | RF_Standalone);

    UMaterialExpressionLandscapeLayerBlend* BaseColorBlend =
        CreateExpression<UMaterialExpressionLandscapeLayerBlend>(Material, 600, 0);
    UMaterialExpressionLandscapeLayerBlend* NormalBlend =
        CreateExpression<UMaterialExpressionLandscapeLayerBlend>(Material, 600, 300);
    UMaterialExpressionLandscapeLayerBlend* ORMBlend =
        CreateExpression<UMaterialExpressionLandscapeLayerBlend>(Material, 600, 600);

    for (int32 LayerIndex = 0; LayerIndex < LayerCount; ++LayerIndex)
    {
        const int32 Row = LayerIndex * 800;

        UMaterialExpressionLandscapeLayerCoords* Coords =
            CreateExpression<UMaterialExpressionLandscapeLayerCoords>(Material, 0, Row);
        Coords->MappingType = TCMT_XY;
        Coords->MappingScale = MappingScale;

        UMaterialExpressionTextureSample* BaseColorSample =
            CreateTextureSample(Material, BC[LayerIndex], SAMPLERTYPE_Color, Coords, 300, Row);
        UMaterialExpressionTextureSample* NormalSample =
            CreateTextureSample(Material, N[LayerIndex], SAMPLERTYPE_Normal, Coords, 300, Row + 250);
        UMaterialExpressionTextureSample* ORMSample =
            CreateTextureSample(Material, ORM[LayerIndex], SAMPLERTYPE_LinearColor, Coords, 300, Row + 500);

        AddLayerInput(BaseColorBlend, Layers[LayerIndex], BaseColorSample);
        AddLayerInput(NormalBlend, Layers[LayerIndex], NormalSample);
        AddLayerInput(ORMBlend, Layers[LayerIndex], ORMSample);
    }

    UMaterialEditingLibrary::ConnectMaterialProperty(BaseColorBlend, TEXT(""), MP_BaseColor);
    UMaterialEditingLibrary::ConnectMaterialProperty(NormalBlend, TEXT(""), MP_Normal);

    UMaterialExpressionComponentMask* AOMask = CreateChannelMask(Material, ORMBlend, true, false, false, 900, 600);
    UMaterialExpressionComponentMask* RoughnessMask =
        CreateChannelMask(Material, ORMBlend, false, true, false, 900, 800);
    UMaterialExpressionComponentMask* MetallicMask =
        CreateChannelMask(Material, ORMBlend, false, false, true, 900, 1000);
    UMaterialEditingLibrary::ConnectMaterialProperty(AOMask, TEXT(""), MP_AmbientOcclusion);
    UMaterialEditingLibrary::ConnectMaterialProperty(RoughnessMask, TEXT(""), MP_Roughness);
    UMaterialEditingLibrary::ConnectMaterialProperty(MetallicMask, TEXT(""), MP_Metallic);

    // Compile errors are reported, not fatal: the saved material is still the import's output, and the
    // verify gate reports any remaining problem.
    for (const FString& CompileError : UMaterialEditingLibrary::RecompileMaterial(Material))
    {
        UE_LOG(LogNmgLandscape, Warning, TEXT("BuildLayeredMaterial '%s': %s"), *Name, *CompileError);
    }

    return SaveAsset(Package, Material) ? Material : nullptr;
}

ULandscapeLayerInfoObject* UNmgLandscapeLibrary::CreateLayerInfo(const FString& Dest, const FString& Name,
                                                                 const FString& Layer)
{
    if (Layer.IsEmpty())
    {
        UE_LOG(LogNmgLandscape, Error, TEXT("CreateLayerInfo '%s': Layer is empty."), *Name);
        return nullptr;
    }

    UPackage* Package = CreatePackage(*PackageNameFor(Dest, Name));
    MoveAsideExistingAsset(Package, Name);
    ULandscapeLayerInfoObject* LayerInfo =
        NewObject<ULandscapeLayerInfoObject>(Package, FName(*Name), RF_Public | RF_Standalone);
    LayerInfo->SetLayerName(FName(*Layer), /*bInModify=*/false);

    return SaveAsset(Package, LayerInfo) ? LayerInfo : nullptr;
}

ALandscape* UNmgLandscapeLibrary::ImportLandscape(UWorld* World, const FString& HeightmapPath,
                                                  const TArray<FString>& WeightmapPaths,
                                                  const TArray<ULandscapeLayerInfoObject*>& LayerInfos,
                                                  UMaterialInterface* Material, int32 N, const FVector& Location,
                                                  const FVector& Scale)
{
    if (!World || !Material || N <= 1 || (N - 1) % SectionQuads != 0 || LayerInfos.Num() == 0 ||
        WeightmapPaths.Num() != LayerInfos.Num())
    {
        UE_LOG(LogNmgLandscape, Error,
               TEXT("ImportLandscape: needs a world, a material, one weightmap per layer info, and (n - 1) divisible by %d (n=%d, %d weightmaps, %d layer infos)."),
               SectionQuads, N, WeightmapPaths.Num(), LayerInfos.Num());
        return nullptr;
    }

    // Decode everything before spawning, so a bad file leaves no half-built landscape in the world.
    TArray<uint16> Heights;
    if (!LoadGrayscalePng<uint16>(HeightmapPath, N, 16, Heights))
    {
        return nullptr;
    }

    TArray<FLandscapeImportLayerInfo> ImportLayers;
    ImportLayers.Reserve(LayerInfos.Num());
    for (int32 LayerIndex = 0; LayerIndex < LayerInfos.Num(); ++LayerIndex)
    {
        ULandscapeLayerInfoObject* LayerInfo = LayerInfos[LayerIndex];
        if (!LayerInfo)
        {
            UE_LOG(LogNmgLandscape, Error, TEXT("ImportLandscape: layer info %d is null."), LayerIndex);
            return nullptr;
        }

        FLandscapeImportLayerInfo ImportLayer(LayerInfo->GetLayerName());
        ImportLayer.LayerInfo = LayerInfo;
        if (!LoadGrayscalePng<uint8>(WeightmapPaths[LayerIndex], N, 8, ImportLayer.LayerData))
        {
            return nullptr;
        }
        ImportLayers.Add(MoveTemp(ImportLayer));
    }

    ALandscape* Landscape = World->SpawnActor<ALandscape>(Location, FRotator::ZeroRotator);
    if (!Landscape)
    {
        UE_LOG(LogNmgLandscape, Error, TEXT("ImportLandscape: could not spawn an ALandscape."));
        return nullptr;
    }
    Landscape->LandscapeMaterial = Material;
    Landscape->SetActorRelativeScale3D(Scale);

    // The engine's own import keys height and layer data by FGuid() and needs a fresh landscape GUID.
    TMap<FGuid, TArray<uint16>> HeightDataPerLayer;
    HeightDataPerLayer.Add(FGuid(), MoveTemp(Heights));

    TMap<FGuid, TArray<FLandscapeImportLayerInfo>> LayerDataPerLayer;
    LayerDataPerLayer.Add(FGuid(), MoveTemp(ImportLayers));

    Landscape->Import(FGuid::NewGuid(), 0, 0, N - 1, N - 1, 1, SectionQuads, HeightDataPerLayer, *HeightmapPath,
                      LayerDataPerLayer, ELandscapeImportAlphamapType::Additive, TArrayView<const FLandscapeLayer>());

    for (ULandscapeLayerInfoObject* LayerInfo : LayerInfos)
    {
        Landscape->AddTargetLayer(LayerInfo->GetLayerName(), FLandscapeTargetLayerSettings(LayerInfo));
    }
    if (ULandscapeInfo* LandscapeInfo = Landscape->GetLandscapeInfo())
    {
        LandscapeInfo->UpdateLayerInfoMap(Landscape);
    }

    return Landscape;
}

TArray<float> UNmgLandscapeLibrary::SampleHeights(ALandscapeProxy* Landscape, const TArray<FVector2D>& XY)
{
    if (!Landscape)
    {
        UE_LOG(LogNmgLandscape, Error, TEXT("SampleHeights: no landscape to sample."));
    }

    TArray<float> Heights;
    Heights.Reserve(XY.Num());
    for (const FVector2D& Point : XY)
    {
        const TOptional<float> Height =
            Landscape ? Landscape->GetHeightAtLocation(FVector(Point.X, Point.Y, 0.0)) : TOptional<float>();
        Heights.Add(Height.IsSet() ? Height.GetValue() : std::numeric_limits<float>::quiet_NaN());
    }
    return Heights;
}
