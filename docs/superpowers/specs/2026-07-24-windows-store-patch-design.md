# Windows Store ChatGPT Provider Patch Design

## Goal

Allow `patch_chatgpt_providers.py` to patch the Microsoft Store installation of
the ChatGPT Windows app while retaining the macOS installer's verified
clean-original, previous-snapshot, and automatic-rollback guarantees.

## Scope

- Support only the ChatGPT package installed through Microsoft Store on Windows.
- Preserve the existing macOS bundle workflow unchanged.
- Keep the official Store package untouched and runnable.
- Create a separately named, locally signed patched MSIX package for the current
  Windows user.
- Do not require Developer Mode. Windows 10 version 2004 or later and Windows
  11 normally allow trusted-app sideloading; enterprise policy may still prevent
  it.
- Continue to reject an app payload whose known JavaScript markers or patch
  contexts do not match exactly.

The standalone provider-setup wizard and non-Store Windows distributions are
out of scope.

## Prerequisites

The Windows path requires an elevated PowerShell session only to trust the
public half of the local package-signing certificate in `LocalMachine\\TrustedPeople`
and to read the protected Store payload. The installer locates `MakeAppx.exe`
and `SignTool.exe` from the Windows SDK and fails before mutation when either
is absent. It creates or reuses a current-user code-signing certificate; the
private key stays in the current user's certificate store.

## Architecture

`patch_chatgpt_providers.py` gains a Windows Store deployment adapter alongside
the existing macOS bundle adapter. The adapter obtains the official package
metadata and installed layout through `Get-AppxPackage`, but never writes inside
`WindowsApps`.

It creates a custom package identity whose name is derived from the Store
package and whose publisher matches the local signing certificate. This makes
the patched package a separate package family, so it can coexist with the
official Store app. The installer rewrites the copied manifest identity,
rebuilds the Electron ASAR after applying the existing strict JavaScript patch,
then packages and signs the result as MSIX. The Store app's already-installed
framework dependencies are reused; a missing dependency stops the install with
the deployment error.

The Windows deployment state lives under the invoking user's local application
data directory, in a dedicated `ChatGPTProviderPatch` directory. It contains:

- `original`: a verified, unmodified copy of the precise Store payload used as
  patch source, plus its package full name and content identity metadata.
- `active`: the signed patched MSIX and metadata for the deployed custom package.
- `previous`: an atomic snapshot of `active`, retained only while replacing it
  and during any failed recovery.

The location is user-writable, unlike `WindowsApps`, but its role is identical
to the sibling backups used by the macOS installer.

## Installation and update flow

1. Confirm `sys.platform == "win32"`, discover exactly one installed ChatGPT
   Store package, and obtain its package full name, version, architecture,
   manifest, and install location.
2. Check the Windows SDK tools, certificate trust, source readability, and all
   source markers before modifying `active` or the installed patched package.
3. Create or refresh `original` transactionally from the untouched Store
   layout. Validate its manifest identity, ASAR structure, marker absence, and
   supported JavaScript bundle before accepting it as clean source.
4. In a temporary directory, copy `original`, patch `app.asar`, update any
   required Electron ASAR-integrity metadata, assign the custom identity,
   package with `MakeAppx`, sign with `SignTool`, and validate the signed
   package. At this point the installed patched app remains untouched.
5. If an `active` artifact exists, atomically snapshot it as `previous`. Stop
   only processes launched from the custom patched package, respecting the
   existing `--allow-running` policy.
6. Install or update the signed package with `Add-AppxPackage`, then verify its
   custom package identity, version, installed ASAR marker, and package
   registration.
7. Atomically promote the new artifact to `active` and remove `previous` only
   after all verification succeeds.

The official Store app can update independently. The patched package does not
update automatically: after a Store update, the user reruns the patcher. The
installer detects the new Store package identity, creates a new clean original,
and performs the same transactional replacement. If the new Store build has
different assets or patch contexts, it fails safely before changing the active
patched app.

## Recovery behavior

Any failure after the `previous` snapshot is created triggers recovery:

1. Remove the partially deployed custom package when registration succeeded.
2. Reinstall and verify `previous` when one exists; otherwise restore the
   no-patched-package state.
3. Restore the on-disk `active` metadata and artifact from `previous`.
4. Keep `previous` and print its exact location if any recovery step fails.

An existing `previous` snapshot at startup is treated as an interrupted
installation. The script refuses to continue until it has restored it or the
user explicitly resolves the reported recovery state. The official Store
package remains untouched throughout installation and recovery.

## Error handling

- No Store-installed ChatGPT package, multiple matching packages, inaccessible
  protected payload, disabled sideload policy, missing Windows SDK tools, or an
  untrusted certificate causes a clear preflight error with no patched-package
  mutation.
- Source, bundle-marker, patch-context, package-signing, deployment, and
  verification errors follow the recovery flow above once a `previous` snapshot
  exists.
- The installer never disables package-integrity checks, alters Store ACLs, or
  overwrites the official package.
- Existing macOS behavior, its app path arguments, backup layout, and recovery
  semantics remain unchanged.

## Testing

Automated tests run on every platform by injecting the Windows platform value,
PowerShell/SDK command runner, Store metadata, and temporary deployment root.
They cover:

- Store-package discovery and strict preflight failures.
- Manifest identity generation, SDK command construction, certificate trust,
  MSIX packaging, signing, and deployment commands.
- A successful deployment that promotes `active` and removes `previous`.
- Failures at package, signing, installation, and verification stages that
  restore the prior MSIX and preserve recovery evidence when restoration fails.
- Source updates that leave the previous patched package untouched when the new
  Store payload is unsupported.
- Regression coverage proving the macOS adapter retains its existing backup and
  rollback flow.

Before declaring the feature supported, a manual Windows acceptance test must
use a real Microsoft Store ChatGPT installation: patch it, launch the custom
package, confirm the provider picker works, simulate an install failure to
confirm rollback, update the Store app, and run the manual refresh path.
