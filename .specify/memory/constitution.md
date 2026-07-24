<!--
Sync Impact Report
- Version change: 2.0.0 -> 3.0.0
- Modified principles:
  - V. Explicit Provider Selection -> V. Explicit Provider Selection
    (guest New Task normalization added; descendant inheritance protected)
- Added sections: None
- Removed sections: None
- Templates requiring updates:
  - ✅ .specify/templates/plan-template.md
  - ✅ .specify/templates/spec-template.md
  - ✅ .specify/templates/tasks-template.md
- Runtime guidance reviewed:
  - ✅ README.md (signed-in default behavior remains aligned; guest guidance is
    already scheduled in the active feature tasks)
- Installed Spec Kit commands reviewed:
  - ✅ .agents/skills/speckit-*/SKILL.md (no outdated agent-specific guidance found)
- Follow-up TODOs: None
-->

# Better Codex App Custom Provider Support Constitution

## Core Principles

### I. Verified Backup Before Mutation

Every operation that modifies `ChatGPT.app` MUST create a complete backup of the
target application before replacing any installed file. The backup MUST be
verified to contain the expected application metadata and `app.asar`. Mutation
MUST NOT begin when backup creation or verification fails. This protects users
from an unrecoverable application state.

### II. Fail Closed on ASAR Incompatibility

The patcher MUST validate the source ASAR integrity and identify compatible,
unambiguous patch targets before changing the installed application. An
unsupported, ambiguous, corrupted, or unexpectedly modified ASAR MUST cause a
clear failure while leaving `ChatGPT.app` unchanged. Compatibility MUST be
proven by validation; it MUST NOT be assumed from an application version alone.

### III. Automatic Restoration on Installation Failure

After installed application files have changed, any failure during file
replacement, integrity metadata updates, signing, or final verification MUST
automatically restore the original application from the verified backup. If
restoration itself cannot complete, the tool MUST preserve the backup, report
its exact path, and exit with a failure status. A failed patched copy MAY be
retained for diagnosis only when the original application is restored.

### IV. Preserve User Settings and Credentials

Configuration operations MUST modify only the fields and tables they explicitly
own. Unrelated Codex settings, project configuration, provider configuration,
and nested authentication data MUST be preserved. Credentials MUST NOT be
written to generated routing JSON or exposed in normal command output. Any file
that is recreated on each run MUST be documented as generated and unsafe to
hand-edit.

### V. Explicit Provider Selection

Every new root task MUST use the provider active in the New Task provider
control. In signed-in mode, a missing, invalid, or legacy selection MUST resolve
to the configured default provider. In custom-provider guest mode, OpenAI MUST
remain disabled; when the saved New Task selection is OpenAI and therefore
disabled in guest mode, the application MUST select the first available
configured non-OpenAI provider according to the existing provider order. Model
selection or model
identifiers MUST NOT implicitly select or change the provider. Existing tasks,
Side Chats, sub-agents, and other descendants MUST retain the provider
association and inheritance behavior already established by Codex; this project
MUST NOT override that inheritance.

## Operational Safety Requirements

- The installed ChatGPT application, Codex configuration, custom model catalog,
  and desktop provider-routing file are protected user state.
- Validation MUST complete before destructive application mutation. Validation
  MUST cover input structure, patch-target uniqueness, ASAR integrity, backup
  completeness, and configuration shape as applicable.
- Writes to generated configuration files MUST be atomic so an interrupted write
  does not leave a partial file.
- The provider-routing file MUST contain identifiers and display metadata only;
  secrets belong in the existing Codex provider authentication configuration.
- The project MUST remain explicit about its unofficial, macOS-only scope and
  MUST document recovery and reapplication requirements after app updates.

## Development Workflow and Quality Gates

- Feature specifications MUST identify affected application or configuration
  state, failure behavior, recovery behavior, preserved state, and provider
  selection behavior whenever those concerns are in scope.
- Implementation plans MUST pass every applicable Constitution Check before
  research and MUST pass it again after design. A non-applicable gate requires a
  written justification; a violation of a MUST rule cannot be waived in a plan.
- Tasks that affect a protected behavior MUST include regression coverage for
  backup verification, incompatibility rejection, restoration, state
  preservation, or explicit provider routing as applicable.
- Reviews MUST verify that user-visible documentation matches actual ownership,
  generated-file behavior, limitations, and recovery procedures.
- Final validation MUST include the relevant automated tests and must confirm
  that unsupported or failed operations do not leave protected state partially
  modified.

## Governance

This constitution supersedes conflicting guidance in specifications, plans,
tasks, and implementation notes. Amendments require a documented rationale, an
updated Sync Impact Report, review of dependent templates and runtime guidance,
and a semantic version change. Removing or redefining a principle requires a
MAJOR version bump; adding or materially expanding policy requires a MINOR bump;
clarifications without changed obligations require a PATCH bump.

Every feature plan and code review MUST verify compliance with applicable
principles. Any conflict with a MUST rule MUST be resolved by changing the lower
level artifact or by explicitly amending this constitution. Compliance reviews
MUST use repository evidence, tests, and documented recovery behavior rather
than unsupported assumptions.

**Version**: 3.0.0 | **Ratified**: 2026-07-20 | **Last Amended**: 2026-07-20
