# Windows custom-provider setup design

## Goal

Allow `setup_custom_provider.py` to configure API-key authentication on Windows
without writing the key to a Codex configuration file or requiring a third-party
secret-store dependency.

## Scope

- Retain the existing macOS Keychain flow.
- Add native Windows Credential Manager support through PowerShell and the
  Windows Credential Manager API.
- Keep unauthenticated providers (`none`) available on both platforms.
- Update setup documentation and automated tests.

The patching workflow and model synchronization scripts are out of scope.

## Platform-specific authentication

`keychain` is available on macOS and `credential-manager` on Windows. The setup
wizard defaults to the native secure-store method for the current supported
platform; `none` remains an explicit alternative. Supplying an authentication
method that is unsupported by the current platform fails with a clear
`SetupError`.

Provider credentials continue to use the stable service name
`codex-<provider-id>`. On Windows, this is the Generic Credential target name
for the current user.

## Configuration and data flow

1. The wizard validates the provider information and the selected authentication
   method for the current platform.
2. For Windows Credential Manager, the setup script launches
   `powershell.exe -NoProfile -NonInteractive` with a small script that calls
   the Windows Credential Manager API to create or update a Generic Credential.
3. `config.toml` receives an auth command that invokes PowerShell with a
   self-contained read-only credential lookup script. It returns only the
   credential value on standard output, as required by Codex.
4. The script atomically updates `config.toml` and the provider-menu JSON as it
   does today. Keys never appear in either file.

macOS retains the existing `security` commands for both storage and lookup.

## Failure handling

- An empty key, unsupported auth method, missing PowerShell executable, or
  Credential Manager API failure produces `SetupError` without writing the
  configuration files.
- If a credential is stored but a subsequent configuration write fails, the
  existing warning remains, identifying the secure-store service name.
- `none` never invokes a secure-store command or creates an auth table.

## Tests

Tests will inject the platform and command runner to remain runnable on all
operating systems. They will cover Windows auth-table generation, the exact
Credential Manager storage invocation, platform-aware defaults, incompatible
method rejection, and the existing macOS/no-auth behavior. Documentation tests
will assert that Windows Credential Manager setup is described without exposing
literal API keys.
