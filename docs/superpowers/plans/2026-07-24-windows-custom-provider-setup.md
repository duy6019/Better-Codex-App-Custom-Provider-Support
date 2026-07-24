# Windows Credential Manager Provider Setup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable `setup_custom_provider.py` to store and retrieve custom-provider API keys through native Windows Credential Manager.

**Architecture:** Keep `ProviderSetup` and TOML writing intact, making authentication validation and command construction platform-aware. Windows storage and lookup use PowerShell with the Credential Manager API; macOS retains `security`.

**Tech Stack:** Python 3.9+, `unittest`, PowerShell, Windows Credential Manager (`CredReadW` / `CredWriteW`).

## Global Constraints

- Do not add Python packages or persist literal API keys in configuration files.
- Keep macOS `keychain` behavior and `none` compatible with existing users.
- Windows uses a current-user Generic Credential named `codex-<provider-id>`.
- A platform-incompatible method raises `SetupError` before configuration files change.
- Tests inject the platform and command runner, so they run on non-Windows hosts.

---

## File structure

- `setup_custom_provider.py`: platform-aware auth validation, PowerShell command generation, and secure-store dispatch.
- `tests/test_setup_custom_provider.py`: red/green tests for Windows auth and regressions.
- `README.md`: native Windows Credential Manager instructions.

### Task 1: Add platform-aware Windows credential authentication

**Files:**

- Modify: `tests/test_setup_custom_provider.py`
- Modify: `setup_custom_provider.py`

**Interfaces:**

- Consumes: `ProviderSetup`, `SetupError`, `keychain_service(provider_id)`, and the injected `command_runner` pattern.
- Produces: `validate_auth_method(value, *, platform_name: Optional[str] = None) -> str`, `default_auth_method(*, platform_name: Optional[str] = None) -> str`, and `store_api_key(provider_id, api_key, auth_method, *, command_runner, platform_name) -> None`.

- [ ] **Step 1: Write failing tests for Windows method selection and TOML lookup generation**

Add these tests to `ProviderConfigurationTests` and `InteractiveSetupTests`:

```python
def test_windows_credential_manager_auth_toml_uses_powershell_lookup(self):
    provider = setup.ProviderSetup(
        "acme", "Acme", "https://api.acme.example/v1", "responses", "credential-manager"
    )

    updated = setup.update_provider_toml("", provider, platform_name="win32")

    self.assertIn('[model_providers.acme.auth]\\ncommand = "powershell.exe"', updated)
    self.assertIn("CredRead", updated)
    self.assertIn("codex-acme", updated)
    self.assertNotIn("test-key", updated)

def test_windows_default_auth_method_is_credential_manager(self):
    self.assertEqual(setup.default_auth_method(platform_name="win32"), "credential-manager")

def test_rejects_platform_incompatible_secure_store(self):
    with self.assertRaisesRegex(setup.SetupError, "Windows Credential Manager"):
        setup.validate_auth_method("keychain", platform_name="win32")
    with self.assertRaisesRegex(setup.SetupError, "macOS Keychain"):
        setup.validate_auth_method("credential-manager", platform_name="darwin")
```

Update the interactive test to pass `platform_name="win32"`; an empty auth answer must select `credential-manager`.

- [ ] **Step 2: Run the focused test module to verify it fails for missing behavior**

Run: `python -m unittest tests.test_setup_custom_provider -v`

Expected: FAIL because `credential-manager` is not accepted, `default_auth_method` does not exist, and `update_provider_toml` has no `platform_name` argument.

- [ ] **Step 3: Implement platform-aware validation and lookup-command generation**

Extend the permitted methods and add these helpers in `setup_custom_provider.py`:

```python
AUTH_METHODS = {"keychain", "credential-manager", "none"}

def default_auth_method(*, platform_name: Optional[str] = None) -> str:
    platform_name = platform_name or sys.platform
    if platform_name == "darwin":
        return "keychain"
    if platform_name == "win32":
        return "credential-manager"
    raise SetupError("Secure credential storage is supported only on macOS and Windows")

def validate_auth_method(value: str, *, platform_name: Optional[str] = None) -> str:
    auth_method = value.strip().lower()
    if auth_method not in AUTH_METHODS:
        raise SetupError("Authentication must be 'keychain', 'credential-manager', or 'none'")
    if auth_method == "keychain" and (platform_name or sys.platform) != "darwin":
        raise SetupError("macOS Keychain authentication is available only on macOS")
    if auth_method == "credential-manager" and (platform_name or sys.platform) != "win32":
        raise SetupError("Windows Credential Manager authentication is available only on Windows")
    return auth_method
```

Create pure helpers for PowerShell lookup and write scripts. Each script defines a Unicode `CREDENTIAL` interop struct and calls the appropriate `Advapi32.dll` function: `CredReadW` for retrieval and `CredWriteW` for storage. The lookup script writes only the UTF-16LE-decoded `CredentialBlob` to standard output; the write script creates or updates a type-1 Generic Credential for the current user and throws after a false API result.

Change `update_provider_toml(contents, provider, *, platform_name=None)` to retain the existing `security` command for `keychain`, and generate the following command for `credential-manager`:

```python
auth_body = "\\n".join((
    'command = "powershell.exe"',
    "args = " + json.dumps([
        "-NoProfile", "-NonInteractive", "-Command",
        windows_credential_lookup_script(), keychain_service(provider_id),
    ]),
))
```

Thread `platform_name` through `setup_provider` and `prompt_provider_setup`. Make the wizard use `default_auth_method()` and prompt with `Authentication [keychain/credential-manager/none] [<native default>]: `.

- [ ] **Step 4: Run the focused test module to verify the new behavior passes**

Run: `python -m unittest tests.test_setup_custom_provider -v`

Expected: PASS, including Windows validation and TOML generation tests.

- [ ] **Step 5: Write a failing test for Windows Credential Manager storage dispatch**

```python
def test_store_windows_api_key_calls_powershell_credential_write(self):
    runner = mock.Mock(return_value=subprocess.CompletedProcess([], 0, "", ""))
    setup.store_api_key(
        "acme", "test-key", "credential-manager",
        command_runner=runner, platform_name="win32",
    )
    command = runner.call_args.args[0]
    self.assertEqual(command[:4], ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command"])
    self.assertIn("CredWrite", command[4])
    self.assertEqual(command[5:], ["codex-acme", "acme", "test-key"])
```

- [ ] **Step 6: Run the single storage test to verify it fails for missing dispatch**

Run: `python -m unittest tests.test_setup_custom_provider.ProviderConfigurationTests.test_store_windows_api_key_calls_powershell_credential_write -v`

Expected: FAIL because `store_api_key` does not exist.

- [ ] **Step 7: Implement minimal secure-store dispatch and retain Keychain compatibility**

Add this dispatcher and use it from `setup_provider` instead of directly calling the Keychain implementation:

```python
def store_api_key(provider_id, api_key, auth_method, *, command_runner=subprocess.run, platform_name=None):
    auth_method = validate_auth_method(auth_method, platform_name=platform_name)
    if not api_key:
        raise SetupError("API key cannot be empty")
    if auth_method == "keychain":
        store_keychain_api_key(provider_id, api_key, command_runner=command_runner)
        return
    if auth_method == "credential-manager":
        command = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                   windows_credential_write_script(), keychain_service(provider_id), provider_id, api_key]
        try:
            command_runner(command, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except (FileNotFoundError, subprocess.CalledProcessError) as exc:
            raise SetupError(f"Could not store Windows Credential Manager entry '{keychain_service(provider_id)}'") from exc
```

Call it only when `provider.auth_method != "none"`. Keep the configuration-write failure warning, but make it secure-store-neutral.

- [ ] **Step 8: Run the focused module to verify storage dispatch and regressions**

Run: `python -m unittest tests.test_setup_custom_provider -v`

Expected: PASS with the Windows storage test and all existing tests.

- [ ] **Step 9: Commit the code and test deliverable**

Run `git add setup_custom_provider.py tests/test_setup_custom_provider.py`, then `git commit -m "feat: support Windows credential manager providers"`.

Expected: a commit containing only Task 1 code and test changes.

### Task 2: Document Windows provider setup

**Files:**

- Modify: `README.md`
- Modify: `tests/test_setup_custom_provider.py`

**Interfaces:**

- Consumes: platform-specific method labels added in Task 1.
- Produces: user instructions identifying native secret storage without literal API keys.

- [ ] **Step 1: Write the failing README assertion**

```python
def test_readme_documents_windows_credential_manager_without_a_literal_key(self):
    readme = (Path(__file__).parents[1] / "README.md").read_text(encoding="utf-8")
    self.assertIn("Windows Credential Manager", readme)
    self.assertIn("credential-manager", readme)
    self.assertNotIn("API_KEY_CUA_BAN", readme)
```

- [ ] **Step 2: Run the documentation test to verify it fails**

Run: `python -m unittest tests.test_setup_custom_provider.DocumentationTests.test_readme_documents_windows_credential_manager_without_a_literal_key -v`

Expected: FAIL because the README does not mention Windows Credential Manager.

- [ ] **Step 3: Update the custom-provider README section**

Replace the macOS-only Keychain wording with:

```markdown
Choose the native secure-store option to keep the API key out of configuration
files: `keychain` on macOS stores it in macOS Keychain, while
`credential-manager` on Windows stores it as a Generic Credential in Windows
Credential Manager. Choose `none` for endpoints that do not require authentication.
```

Clarify that the wizard supports macOS and Windows, while the application patch remains macOS-specific.

- [ ] **Step 4: Run the documentation test to verify it passes**

Run: `python -m unittest tests.test_setup_custom_provider.DocumentationTests -v`

Expected: PASS.

- [ ] **Step 5: Run the complete repository test suite**

Run: `python -m unittest discover -s tests -v`

Expected: PASS with zero failures and zero errors.

- [ ] **Step 6: Commit the documentation deliverable**

Run `git add README.md tests/test_setup_custom_provider.py`, then `git commit -m "docs: explain Windows credential manager setup"`.

Expected: a commit containing only Task 2 documentation and test changes.
