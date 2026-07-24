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
- The complete repository test suite must import all test modules on Windows.

---

## File structure

- `setup_custom_provider.py`: platform-aware auth validation, PowerShell command generation, and secure-store dispatch.
- `tests/test_setup_custom_provider.py`: red/green tests for Windows auth and regressions.
- `README.md`: native Windows Credential Manager instructions.
- `patch_chatgpt_providers.py`: preserve macOS sudo-home resolution without requiring the POSIX-only `pwd` module on Windows.
- `tests/test_windows_compatibility.py`: subprocess-level Windows import regression test for the macOS patch script.

### Task 0: Make the macOS patch module importable on Windows

**Files:**

- Create: `tests/test_windows_compatibility.py`
- Modify: `patch_chatgpt_providers.py`

**Interfaces:**

- Consumes: `invoking_user_home()` which uses `pwd.getpwnam` only when a non-root `SUDO_USER` value exists on POSIX hosts.
- Produces: successful `import patch_chatgpt_providers` under the Windows Python runtime while retaining the existing macOS behavior.

- [ ] **Step 1: Write a failing subprocess import test**

```python
import subprocess
import sys
import unittest

class WindowsCompatibilityTests(unittest.TestCase):
    def test_patch_module_imports_when_the_pwd_module_is_unavailable(self):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; sys.modules['pwd'] = None; import patch_chatgpt_providers",
            ],
            text=True,
            capture_output=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
```

- [ ] **Step 2: Run the new test to verify the POSIX-only import failure**

Run: `python -m unittest tests.test_windows_compatibility -v`

Expected: FAIL with an import error for `pwd`.

- [ ] **Step 3: Guard the optional POSIX dependency at its source**

Replace the unconditional `import pwd` in `patch_chatgpt_providers.py` with:

```python
try:
    import pwd
except ModuleNotFoundError:
    pwd = None
```

Then update `invoking_user_home()` to call `pwd.getpwnam` only when `pwd is not None`:

```python
if sudo_user and sudo_user != "root" and pwd is not None:
    try:
        return Path(pwd.getpwnam(sudo_user).pw_dir)
    except KeyError:
        pass
```

- [ ] **Step 4: Run the new test and complete suite**

Run: `python -m unittest tests.test_windows_compatibility -v`, then `python -m unittest discover -s tests -v`.

Expected: the import regression passes and all test modules load on Windows.

- [ ] **Step 5: Commit the Windows test-suite compatibility deliverable**

Run `git add patch_chatgpt_providers.py tests/test_windows_compatibility.py`, then `git commit -m "fix: allow patch tests to import on Windows"`.

Expected: a commit containing only the optional-POSIX-dependency fix and its regression test.

### Task 2: Add platform-aware Windows credential authentication

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

Expected: a commit containing only Task 2 code and test changes.

### Task 3: Document Windows provider setup

**Files:**

- Modify: `README.md`
- Modify: `tests/test_setup_custom_provider.py`

**Interfaces:**

- Consumes: platform-specific method labels added in Task 2.
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

Expected: a commit containing only Task 3 documentation and test changes.

### Task 1: Complete Windows suite compatibility

**Files:**

- Modify: `tests/test_windows_compatibility.py`
- Modify: `tests/test_sync_codex_models.py`
- Modify: `patch_chatgpt_providers.py`
- Modify: `sync_codex_models.py`

**Interfaces:**

- Consumes: terminal helpers that write status details to streams with an arbitrary `encoding`, and `update_codex_toml(contents, catalog_path, base_url)`.
- Produces: status output that does not raise `UnicodeEncodeError` on cp1252 streams and TOML catalog paths using forward slashes on every platform.

- [ ] **Step 1: Write failing tests for both Windows-specific failures**

Add this test to `tests/test_windows_compatibility.py`:

```python
import io

def test_terminal_status_uses_ascii_detail_marker_for_cp1252_stream(self):
    buffer = io.BytesIO()
    stream = io.TextIOWrapper(buffer, encoding="cp1252", errors="strict")

    patcher.terminal_status("CONFIG", "Configured", "36", detail="C:\\config.toml", stream=stream)
    stream.flush()

    self.assertIn(b"-> C:\\config.toml", buffer.getvalue())
```

Add this test to `TomlTests` in `tests/test_sync_codex_models.py`:

```python
def test_update_codex_toml_serializes_catalog_path_with_forward_slashes(self):
    updated = sync.update_codex_toml(
        "", Path("/tmp/custom.json"), "http://127.0.0.1:20128/v1"
    )

    self.assertIn('model_catalog_json = "/tmp/custom.json"', updated)
```

- [ ] **Step 2: Run the two focused tests to verify they fail**

Run: `python -m unittest tests.test_windows_compatibility.WindowsCompatibilityTests.test_terminal_status_uses_ascii_detail_marker_for_cp1252_stream -v`, then `python -m unittest tests.test_sync_codex_models.TomlTests.test_update_codex_toml_serializes_catalog_path_with_forward_slashes -v`.

Expected: the terminal test raises `UnicodeEncodeError` and the TOML test finds `\\tmp\\custom.json` instead of `/tmp/custom.json` on Windows.

- [ ] **Step 3: Implement encoding-safe terminal markers and portable TOML serialization**

Add a helper in `patch_chatgpt_providers.py` that returns the Unicode glyph when `stream.encoding` can encode it and an ASCII fallback otherwise. Use it for the `terminal_status` detail marker, returning `"-> "` when the arrow cannot be encoded. Keep existing Unicode output on UTF-8 terminals.

In `sync_codex_models.py`, change the catalog value passed to `update_root_setting` from `str(catalog_path)` to `catalog_path.as_posix()`. This writes a portable TOML path and preserves normal Windows drive paths as `C:/Users/...`.

- [ ] **Step 4: Run focused tests and the full suite**

Run: `python -m unittest tests.test_windows_compatibility -v`, `python -m unittest tests.test_sync_codex_models.TomlTests -v`, then `python -m unittest discover -s tests -v`.

Expected: the focused tests and all 63 discovery tests pass with no failures or errors.

- [ ] **Step 5: Commit the compatibility deliverable**

Run `git add patch_chatgpt_providers.py sync_codex_models.py tests/test_windows_compatibility.py tests/test_sync_codex_models.py`, then `git commit -m "fix: make Windows test suite portable"`.

Expected: a commit containing only Task 1 Windows compatibility changes and tests.
