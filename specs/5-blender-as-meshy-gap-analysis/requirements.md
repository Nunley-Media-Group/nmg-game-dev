# Requirements: Converted spike #5

**Issue**: #5
**Date**: 2026-09-05
**Status**: Draft
**Author**: Unknown
**Related Spec**: docs/decisions/2026-05-02-blender-as-meshy-gap-analysis.md
---

## User Story

**As a** maintainer
**I want** this leftover spike converted to an ordinary spec
**So that** execute can require an approved four-file package

## Acceptance Criteria

### AC1: Ordinary spec exists

**Given** leftover spike research
**When** upgrade converts it
**Then** specs/5-blender-as-meshy-gap-analysis/ exists with singular **Issue**: #5

## Change History

| Issue | Date | Summary |
|-------|------|---------|
| #5 | 2026-09-05 | Converted leftover spike ADR |

## Historical spike

Converted from leftover spike ADR `docs/decisions/2026-05-02-blender-as-meshy-gap-analysis.md`. Research is not an executable type.

> # ADR: Blender-as-Meshy Gap Analysis
>
> **Issues**: #5
> **Date**: 2026-05-02
> **Status**: Accepted
> **Decision Type**: Spike gap analysis
>
> ---
>
> ## Context
>
> nmg-game-dev is Blender-first by product direction, and this spike concludes that Blender MCP recipe generation is the v1 asset-creation path. Meshy and model-backed tools are retained only as historical benchmarks, not implementation dependencies. Issue #5 asks whether Blender can become the primary Meshy-parity authoring surface for text-to-3D asset creation, PBR texture generation, retexturing, remesh/topology, LOD generation, rigging, and animation.
