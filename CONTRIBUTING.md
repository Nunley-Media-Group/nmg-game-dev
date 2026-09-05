# Contributing

## Project Context

nmg-game-dev is a Blender-first content-generation framework for Unreal Engine
games. It ships as a Codex plugin, Blender add-on, and Unreal Engine plugin,
with consumer-side onboarding handled by framework skills and templates.

Before changing behavior, read:

- `steering/snippets/project-product.md` for the product mission, target users, value
  proposition, and success metrics.
- `steering/snippets/project-tech.md` for architecture, supported tool versions, versioning,
  coding standards, and verification gates.
- `steering/snippets/project-structure.md` for repository layout, layer boundaries, naming
  conventions, and file ownership.

Existing code and reconciled specs are contribution context. Treat `specs/` as
the history of accepted product and technical decisions, not just planning
notes.

## Issue and Spec Workflow

Start work from a clear GitHub issue with acceptance criteria. Feature and bug
implementation should flow through nmg-sdlc specs in `specs/`, using the normal
issue -> spec -> code -> simplify -> verify -> PR path.

Use `$nmg-sdlc:draft-issue` for new work, `$nmg-sdlc:start-issue` to pick up an
issue, `$nmg-sdlc:write-spec` to create or amend specs, `$nmg-sdlc:write-code`
to implement, `$nmg-sdlc:simplify` to clean up, `$nmg-sdlc:verify-code` to
validate, and `$nmg-sdlc:open-pr` to deliver the branch.

## Steering Expectations

Align changes with the steering docs before editing code or specs:

- Product work should preserve the Blender-first authoring model,
  variant-aware asset flow, consumer onboarding path, and automated quality
  gates.
- Technical work should keep the Codex plugin, Blender add-on, Unreal plugin,
  MCP launchers, and version-managed artifacts in sync.
- Structural changes should respect the repo layout and the boundary between
  framework-owned artifacts and consumer-project templates.

If a change intentionally moves away from steering, update the relevant steering
doc in the same branch and call out the decision in the spec or PR.

## Implementation and Verification

Keep edits scoped to the issue and spec. Update code, specs, tests,
version-managed metadata, and docs together when the contract requires it.

Use the project gates described in `steering/snippets/project-tech.md`, including Python checks,
BDD scenarios, Blender or Unreal automation where relevant, and version
consistency across `VERSION`, `.codex-plugin/plugin.json`, Blender metadata,
Unreal metadata, and `pyproject.toml`.

Consumer-facing behavior should include onboarding or template updates when
needed, especially for `.codex` consumer artifacts installed by future
onboarding skills.

## nmg-sdlc Contribution Workflow

Use a linked GitHub issue as the source of truth before implementation starts.
The issue should include the user story or bug context, BDD-style acceptance
criteria, functional requirements, scope boundaries, priority, and automation
suitability. Draft new work with `$nmg-sdlc:draft-issue` when that structure is
missing.

Create or amend the relevant `specs/feature-*` or `specs/bug-*` package before
editing behavior. Each spec package should include `requirements.md`,
`design.md`, `tasks.md`, and `feature.gherkin` when applicable, with
`**Issues**: #N` frontmatter for feature specs. Treat existing code and
reconciled specs as brownfield context when planning a change.

Before requesting review, confirm the change remains aligned with
`steering/snippets/project-product.md`, `steering/snippets/project-tech.md`, and `steering/snippets/project-structure.md`. Keep
implementation scope within the approved spec, avoid unrelated refactors, and
update framework-owned artifacts plus consumer templates together when the
contract spans both sides.

PRs should be review-ready before `$nmg-sdlc:open-pr` or manual submission:

- Link the issue and affected spec package.
- Summarize steering alignment and any intentional steering changes.
- List implementation scope and known out-of-scope work.
- Include verification evidence from tests, `$nmg-sdlc:verify-code`, Blender or
  Unreal automation, or `verification-report.md`.
- Note known gaps, follow-up issues, or reviewer context needed to evaluate the
  branch.

The managed nmg-sdlc contribution gate checks for issue, spec, steering,
verification, and guide evidence. Fix missing evidence at the source instead of
bypassing the gate: add the issue link, update the spec package, explain
steering alignment, attach verification results, or refresh this guide with
`$nmg-sdlc:upgrade-project`.

### Current contract (v3 invocations)

Interactive commands:

- `/sdlc-draft-issue [need]`
- `/sdlc-write-spec #N`
- `/sdlc-onboard-project`
- `/sdlc-upgrade-project`
- `/sdlc-execute [#N …]`
- `/sdlc-status`

Automated file commands: `/sdlc-verify-code`, `/sdlc-open-pr`. `/sdlc-execute` drives Herdr `omp` workers through implementation, verification, exact-head merge, and issue closure. `/sdlc-upgrade-project` detects and proposes repairs; it never applies silently.

One issue owns exactly one `specs/{N}-{slug}/` package with singular `**Issue**: #N`. GitHub official blocked-by is the sole sequencing authority. `Depends on:` / `Blocks:` body text is historical evidence only.

PR readiness: link `Closes #N` or `**Issue**: #N`; name the matching `specs/{N}-{slug}/` artifacts; explain alignment with the manifest-registered product, technical, and structure snippets; record verification as a command plus outcome (for example `` `python -m pytest tests/unit` — passed ``) or a committed `verification-report.md`. Exact path evidence names a file; directory evidence ends in `/`.

| Mode | Declaration and validation | Reduced checks | Still required | Invalidating conditions |
|------|----------------------------|----------------|----------------|-------------------------|
| Documentation-only | `SDLC-Exception: docs-only — <non-empty reason>` and every change is project documentation | Spec correlation, relevant-path mapping, and specific verification | Current issue linkage, steering artifacts and alignment, guide discoverability, and all other checks | Source, workflow, script, skill, template, shared reference, spec, ADR, or any other non-documentation path |
| Repository rewrite | `SDLC-Exception: repository-rewrite — <non-empty reason>`; PR title starts `feat!:`; `package.json`, `VERSION`, `README.md`, `CONTRIBUTING.md`, all steering files, the managed contribution gate, `references/rewrite-contract.{json,md}`, and `references/rewrite-verification.md` change | Current PR issue/spec identity only | Genuinely owned current spec archive, explicit rewrite contract, durable verification, steering alignment, exact changed-path mapping, specific verification, and guide discoverability | Missing contract path, non-breaking title, unmatched relevant path, missing steering, or missing verification |
| Spec-only write-spec | Title matches `^docs: approve spec for #(\d+)$`; that issue number appears in current PR text; every changed path is class `spec` under exactly one `specs/{N}-{slug}/` whose leading number is that issue | Steering alignment text and specific verification | Current issue linkage, spec correlation, steering artifacts, guide discoverability, and all other checks | Any non-spec path, title mismatch, multiple spec directories, or issue number mismatch |

If the contribution gate fails, fix the named evidence category. Do not bypass the workflow.
