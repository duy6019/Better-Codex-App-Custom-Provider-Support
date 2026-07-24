#!/usr/bin/env python3
"""Install the custom model-provider picker patch into ChatGPT.app on macOS.

The patch is intentionally version-sensitive: it only edits JavaScript bundles
whose expected source hunks match exactly. App updates that change those bundles
cause a clean failure before the installed app is modified.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import plistlib
try:
    import pwd
except ModuleNotFoundError:
    pwd = None
import re
import shlex
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import textwrap
import time
from typing import Any, NoReturn, Sequence
import xml.etree.ElementTree as ET
import zipfile


PATCH_MARKER = b"__codexDesktopModelProvidersPatchV2"
ASAR_PACKAGE = "@electron/asar@3.2.10"
PRETTIER_PACKAGE = "prettier@3.6.2"
WINDOWS_STORE_PACKAGE_NAME = "OpenAI.ChatGPT"
BUILD_5828_BUNDLE_MARKERS = (
    "async prewarmThreadStart(",
    "async sendConfigReadRequest(",
    "composer.intelligenceDropdown.tooltip",
    "data-model-picker-model-row",
    "vertical-scroll-fade-mask flex max-h-[250px] flex-col overflow-y-auto",
    "function p9t(e)",
    "function Qjs(e)",
    "async function rp(...e)",
)

DEFAULT_PROVIDER_CONFIG: dict[str, Any] = {
    "version": 1,
    "default_provider": "openai",
    "providers": [
        {
            "id": "openai",
            "label": "ChatGPT / OpenAI",
            "description": (
                "Built-in provider; uses your signed-in ChatGPT account"
            ),
        },
    ],
    "model_providers": {},
}


CENTRAL_DIFF = r"""@@ -137534,6 +137678,131 @@
 function p9t(e) {
   if (`data` in e) return e;
   let t = fbe(e);
   return t == null ? e : { ...e, data: t };
 }
+function codexProviderRoutingFallback() {
+  return {
+    version: 1,
+    defaultProvider: `openai`,
+    providers: [
+      {
+        id: `openai`,
+        label: `ChatGPT / OpenAI`,
+        description: `Uses your signed-in ChatGPT account`,
+      },
+    ],
+    modelProviders: {},
+  };
+}
+function codexNormalizeProviderRoutingConfig(e) {
+  if (e == null || typeof e !== `object` || Array.isArray(e))
+    throw Error(`Expected a JSON object`);
+  if (e.version !== 1) throw Error(`Unsupported version`);
+  if (!Array.isArray(e.providers) || e.providers.length === 0)
+    throw Error(`providers must be a non-empty array`);
+  let t = [],
+    n = new Set();
+  for (let r of e.providers) {
+    if (r == null || typeof r !== `object` || Array.isArray(r))
+      throw Error(`Every provider must be an object`);
+    let e = typeof r.id === `string` ? r.id.trim() : ``;
+    if (e.length === 0 || n.has(e))
+      throw Error(`Provider ids must be unique non-empty strings`);
+    n.add(e);
+    let i = typeof r.label === `string` ? r.label.trim() : ``;
+    t.push({
+      id: e,
+      label: i.length > 0 ? i : e,
+      description:
+        typeof r.description === `string` ? r.description.trim() : ``,
+    });
+  }
+  let r =
+    typeof e.default_provider === `string` ? e.default_provider.trim() : ``;
+  if (!n.has(r))
+    throw Error(`default_provider must reference a configured provider`);
+  let i = {};
+  if (
+    e.model_providers == null ||
+    typeof e.model_providers !== `object` ||
+    Array.isArray(e.model_providers)
+  )
+    throw Error(`model_providers must be an object`);
+  for (let [t, r] of Object.entries(e.model_providers)) {
+    let e = t.trim();
+    if (e.length === 0 || typeof r !== `string` || !n.has(r))
+      throw Error(`Every model mapping must reference a configured provider`);
+    i[e] = r;
+  }
+  return {
+    version: 1,
+    defaultProvider: r,
+    providers: t,
+    modelProviders: i,
+  };
+}
+function codexProviderRoutingState() {
+  return (window.__codexDesktopModelProvidersPatchV2 ??= {
+    config: codexProviderRoutingFallback(),
+    configPath: null,
+    error: null,
+    loaded: !1,
+    promise: null,
+  });
+}
+async function codexLoadProviderRoutingConfig(e = !1) {
+  let t = codexProviderRoutingState();
+  if (!e && t.loaded) return t.config;
+  if (t.promise != null) return t.promise;
+  return (
+    (t.promise = (async () => {
+      try {
+        let { codexHome: e } = await rp(`codex-home`, {
+            params: { hostId: `local` },
+          }),
+          n = e.includes(`\\`) && !e.includes(`/`) ? `\\` : `/`,
+          r = `${e.replace(/[\\/]+$/u, ``)}${n}desktop-model-providers.json`,
+          { contents: i } = await rp(`read-file`, {
+            params: { hostId: `local`, path: r },
+          }),
+          a = codexNormalizeProviderRoutingConfig(JSON.parse(i));
+        return (
+          (t.config = a),
+          (t.configPath = r),
+          (t.error = null),
+          (t.loaded = !0),
+          a
+        );
+      } catch (e) {
+        return (
+          (t.config = codexProviderRoutingFallback()),
+          (t.error = e instanceof Error ? e.message : String(e)),
+          (t.loaded = !0),
+          t.config
+        );
+      } finally {
+        t.promise = null;
+      }
+    })()),
+    t.promise
+  );
+}
+function codexCustomProviderChoice(e) {
+  try {
+    let t = window.localStorage.getItem(`codex.customProviderSelection.v1`);
+    return e.providers.some((e) => e.id === t) ? t : e.defaultProvider;
+  } catch {
+    return e.defaultProvider;
+  }
+}
+async function codexSelectedProvider() {
+  let e = await codexLoadProviderRoutingConfig(!0);
+  return codexCustomProviderChoice(e);
+}
+async function codexPatchAppServerParams(e, t) {
+  if (e === `thread/list`) {
+    let e = t != null && typeof t === `object` ? t : {};
+    return e.modelProviders == null ? { ...e, modelProviders: [] } : e;
+  }
+  if (
+    (e === `thread/start` || e === `thread/fork`) &&
+    t != null &&
+    typeof t === `object`
+  )
+    return { ...t, modelProvider: await codexSelectedProvider() };
+  return t;
+}
 var m9t,
@@ -137749,6 +137750,8 @@
         async sendRequest(e, t, n) {
           if (this.dispatchMessage == null)
             throw Error(
               `AppServerRequestClient is missing a message dispatcher`,
             );
+          t = await codexPatchAppServerParams(e, t);
           return e === `config/read`
             ? this.sendConfigReadRequest(t, n)
             : this.enqueueRequest(e, t, n);
@@ -137758,6 +137761,12 @@
           try {
+            e = await codexPatchAppServerParams(`thread/start`, e);
             let a = await this.enqueueRequest(
               `thread/start`,
               e,
               { ...t, priority: n, trace: t?.trace ?? i?.trace ?? null },
               (e) => {
"""


PICKER_DIFF = r"""@@ -520216,8 +520216,13 @@
   t[43] === r.model
     ? (ie = t[44])
-    : ((ie = r.model == null ? null : (0, $X.jsx)($ss, { submenu: r.model })),
+    : ((ie =
+        r.model == null
+          ? null
+          : (0, $X.jsx)($ss, {
+              submenu: r.model,
+              providerPicker: !0,
+            })),
       (t[43] = r.model),
       (t[44] = ie));
@@ -520323,10 +520328,17 @@
       ? ((u = (0, $X.jsx)(Cos, {
           ariaLabel: r,
           contentClassName: i,
           disabled: a,
           flyoutHeader: o,
           label: s,
           value: c,
-          children: l,
+          children: e.providerPicker
+            ? (0, $X.jsxs)($X.Fragment, {
+                children: [
+                  (0, $X.jsx)(CodexCustomProviderPickerSection, {}),
+                  l,
+                ],
+              })
+            : l,
         })),
@@ -548655,6 +548655,189 @@
 var Xjs,
   Zjs = e(() => {
     (Ho(),
       ed(),
       DD(),
       (Xjs = Oa(Q, (e, { get: t }) =>
         Yjs({
           conversationId: e,
           resumeState: t(hD, e) ?? void 0,
           turnCount: t(vD, e),
         }),
       )));
   });
+function codexPickerProviderRoutingFallback() {
+  return {
+    version: 1,
+    defaultProvider: `openai`,
+    providers: [
+      {
+        id: `openai`,
+        label: `ChatGPT / OpenAI`,
+        description: `Uses your signed-in ChatGPT account`,
+      },
+    ],
+    modelProviders: {},
+  };
+}
+function codexPickerNormalizeProviderRoutingConfig(e) {
+  if (e == null || typeof e !== `object` || Array.isArray(e))
+    throw Error(`Expected a JSON object`);
+  if (e.version !== 1) throw Error(`Unsupported version`);
+  if (!Array.isArray(e.providers) || e.providers.length === 0)
+    throw Error(`providers must be a non-empty array`);
+  let t = [],
+    n = new Set();
+  for (let r of e.providers) {
+    if (r == null || typeof r !== `object` || Array.isArray(r))
+      throw Error(`Every provider must be an object`);
+    let e = typeof r.id === `string` ? r.id.trim() : ``;
+    if (e.length === 0 || n.has(e))
+      throw Error(`Provider ids must be unique non-empty strings`);
+    n.add(e);
+    let i = typeof r.label === `string` ? r.label.trim() : ``;
+    t.push({
+      id: e,
+      label: i.length > 0 ? i : e,
+      description:
+        typeof r.description === `string` ? r.description.trim() : ``,
+    });
+  }
+  let r =
+    typeof e.default_provider === `string` ? e.default_provider.trim() : ``;
+  if (!n.has(r))
+    throw Error(`default_provider must reference a configured provider`);
+  let i = {};
+  if (
+    e.model_providers == null ||
+    typeof e.model_providers !== `object` ||
+    Array.isArray(e.model_providers)
+  )
+    throw Error(`model_providers must be an object`);
+  for (let [t, r] of Object.entries(e.model_providers)) {
+    let e = t.trim();
+    if (e.length === 0 || typeof r !== `string` || !n.has(r))
+      throw Error(`Every model mapping must reference a configured provider`);
+    i[e] = r;
+  }
+  return {
+    version: 1,
+    defaultProvider: r,
+    providers: t,
+    modelProviders: i,
+  };
+}
+function codexPickerProviderRoutingState() {
+  return (window.__codexDesktopModelProvidersPatchV2 ??= {
+    config: codexPickerProviderRoutingFallback(),
+    configPath: null,
+    error: null,
+    loaded: !1,
+    promise: null,
+  });
+}
+async function codexPickerLoadProviderRoutingConfig(e = !1) {
+  let t = codexPickerProviderRoutingState();
+  if (!e && t.loaded) return t.config;
+  if (t.promise != null) return t.promise;
+  return (
+    (t.promise = (async () => {
+      try {
+        let { codexHome: e } = await rp(`codex-home`, {
+            params: { hostId: `local` },
+          }),
+          n = e.includes(`\\`) && !e.includes(`/`) ? `\\` : `/`,
+          r = `${e.replace(/[\\/]+$/u, ``)}${n}desktop-model-providers.json`;
+        t.configPath = r;
+        let { contents: i } = await rp(`read-file`, {
+            params: { hostId: `local`, path: r },
+          }),
+          a = codexPickerNormalizeProviderRoutingConfig(JSON.parse(i));
+        return ((t.config = a), (t.error = null), (t.loaded = !0), a);
+      } catch (e) {
+        return (
+          (t.config = codexPickerProviderRoutingFallback()),
+          (t.error = e instanceof Error ? e.message : String(e)),
+          (t.loaded = !0),
+          t.config
+        );
+      } finally {
+        t.promise = null;
+      }
+    })()),
+    t.promise
+  );
+}
+function codexReadCustomProviderChoice(e) {
+  try {
+    let t = window.localStorage.getItem(`codex.customProviderSelection.v1`);
+    return e.providers.some((e) => e.id === t) ? t : e.defaultProvider;
+  } catch {
+    return e.defaultProvider;
+  }
+}
+function codexWriteCustomProviderChoice(e) {
+  try {
+    window.localStorage.setItem(`codex.customProviderSelection.v1`, e);
+  } catch {}
+}
+function CodexCustomProviderPickerSection() {
+  let r = codexPickerProviderRoutingState(),
+    [e, t] = CodexProviderPatchReact.useState(r.config),
+    [n, i] = CodexProviderPatchReact.useState(r.error),
+    [a, o] = CodexProviderPatchReact.useState(() =>
+      codexReadCustomProviderChoice(r.config),
+    );
+  CodexProviderPatchReact.useEffect(() => {
+    let e = !0;
+    return (
+      codexPickerLoadProviderRoutingConfig(!0).then((n) => {
+        if (e) {
+          let e = codexReadCustomProviderChoice(n);
+          (t(n),
+            i(codexPickerProviderRoutingState().error),
+            codexWriteCustomProviderChoice(e),
+            o(e));
+        }
+      }),
+      () => {
+        e = !1;
+      }
+    );
+  }, []);
+  let s = (e) => (t) => {
+      (t?.preventDefault(), codexWriteCustomProviderChoice(e), o(e));
+    },
+    c = e.providers.map((e) =>
+      (0, TQ.jsx)(
+        KR.Item,
+        {
+          RightIcon: a === e.id ? Bm : void 0,
+          SubText:
+            e.description.length === 0
+              ? null
+              : (0, TQ.jsx)(`span`, {
+                  className: `text-token-description-foreground`,
+                  children: e.description,
+                }),
+          onSelect: s(e.id),
+          children: e.label,
+        },
+        e.id,
+      ),
+    );
+  return (0, TQ.jsxs)(TQ.Fragment, {
+    children: [
+      (0, TQ.jsx)(KR.Title, { children: `Provider for new tasks` }),
+      n == null
+        ? null
+        : (0, TQ.jsx)(KR.Item, {
+            disabled: !0,
+            SubText: (0, TQ.jsx)(`span`, {
+              className: `text-token-description-foreground`,
+              children: n,
+            }),
+            children: `Provider config error — using fallback`,
+          }),
+      c,
+      (0, TQ.jsx)(KR.Separator, {}),
+    ],
+  });
+}
 function Qjs(e) {
   let t = (0, eMs.c)(164),
     {
@@ -548925,6 +549036,7 @@
       : ((g = (0, TQ.jsxs)(TQ.Fragment, {
           children: [
+            (0, TQ.jsx)(CodexCustomProviderPickerSection, {}),
             m,
             (0, TQ.jsx)(`div`, {
               className: `vertical-scroll-fade-mask flex max-h-[250px] flex-col overflow-y-auto`,
@@ -549575,6 +549577,8 @@
 }
 var eMs,
   TQ,
+  CodexProviderPatchReact,
   tMs = e(() => {
     ((eMs = c()),
+      (CodexProviderPatchReact = r(o(), 1)),
       sd(),
"""


class PatchError(RuntimeError):
    """A safe, expected patch failure."""


def colors_enabled(stream: Any = sys.stdout) -> bool:
    return "NO_COLOR" not in os.environ and (
        getattr(stream, "isatty", lambda: False)()
        or os.environ.get("FORCE_COLOR") not in (None, "", "0")
    )


def color(text: object, *codes: str, stream: Any = sys.stdout) -> str:
    rendered = str(text)
    if not colors_enabled(stream) or not codes:
        return rendered
    return f"\033[{';'.join(codes)}m{rendered}\033[0m"


def terminal_width() -> int:
    return max(64, min(shutil.get_terminal_size((96, 24)).columns, 110))


def terminal_detail_marker(stream: Any) -> str:
    marker = "\u21b3 "
    encoding = getattr(stream, "encoding", None)
    if encoding is None:
        return marker
    try:
        marker.encode(encoding)
    except (LookupError, UnicodeEncodeError):
        return "-> "
    return marker


def terminal_box_characters(stream: Any) -> tuple[str, str, str, str]:
    characters = ("\u256d", "\u2570", "\u2500", "\u2502")
    encoding = getattr(stream, "encoding", None)
    if encoding is None:
        return characters
    try:
        "".join(characters).encode(encoding)
    except (LookupError, UnicodeEncodeError):
        return ("+", "+", "-", "|")
    return characters


def terminal_status(
    label: str,
    message: object,
    code: str,
    *,
    detail: object | None = None,
    stream: Any = sys.stdout,
) -> None:
    badge_width = 10
    plain_badge = f"[{label}]"
    badge = color(plain_badge, "1", code, stream=stream)
    badge_padding = " " * max(1, badge_width - len(plain_badge))
    available = max(30, terminal_width() - badge_width)
    lines = textwrap.wrap(
        str(message),
        width=available,
        break_long_words=False,
        break_on_hyphens=False,
    ) or [""]
    print(f"{badge}{badge_padding}{lines[0]}", file=stream)
    for line in lines[1:]:
        print(f"{'':{badge_width}}{line}", file=stream)
    if detail is not None:
        detail_lines = textwrap.wrap(
            str(detail),
            width=max(30, terminal_width() - badge_width - 2),
            break_long_words=False,
            break_on_hyphens=False,
        ) or [""]
        for index, line in enumerate(detail_lines):
            marker = terminal_detail_marker(stream) if index == 0 else "  "
            print(
                f"{'':{badge_width}}{color(marker + line, '2', stream=stream)}",
                file=stream,
            )
    stream.flush()


def terminal_heading(title: str, code: str = "36") -> None:
    visible_title = f" {title.upper()} "
    rule_length = max(2, terminal_width() - len(visible_title))
    print()
    print(
        color(f"{visible_title}{'━' * rule_length}", "1", code),
    )
    sys.stdout.flush()


def terminal_panel(
    title: str,
    message: object,
    code: str,
    *,
    stream: Any = sys.stderr,
) -> None:
    width = terminal_width()
    title_text = f" {title.upper()} "
    top = f"╭─{title_text}{'─' * max(1, width - len(title_text) - 2)}"
    bottom = f"╰{'─' * (width - 1)}"
    print(file=stream)
    print(color(top, "1", code, stream=stream), file=stream)
    paragraphs = str(message).splitlines() or [""]
    for paragraph in paragraphs:
        wrapped = textwrap.wrap(
            paragraph,
            width=max(30, width - 4),
            break_long_words=False,
            break_on_hyphens=False,
        ) or [""]
        for line in wrapped:
            border = color("│", code, stream=stream)
            print(f"{border} {color(line, '1', stream=stream)}", file=stream)
    print(color(bottom, "1", code, stream=stream), file=stream)
    print(file=stream)
    stream.flush()


def terminal_bullet(label: str, description: str) -> None:
    bullet = color("◆", "1", "36")
    key = color(label, "1", "33")
    prefix_width = 29
    prefix = f"  {bullet} {key}"
    padding = " " * max(1, prefix_width - 4 - len(label))
    available = max(30, terminal_width() - prefix_width)
    lines = textwrap.wrap(
        description,
        width=available,
        break_long_words=False,
        break_on_hyphens=False,
    ) or [""]
    print(f"{prefix}{padding}{lines[0]}")
    for line in lines[1:]:
        print(f"{'':{prefix_width}}{line}")
    sys.stdout.flush()


def print_completion_summary(
    config: Path,
    *,
    backup: Path | None = None,
    already_installed: bool = False,
) -> None:
    codex_config = config.parent / "config.toml"
    if already_installed:
        terminal_status(
            "READY",
            "Patch already installed; no app files were changed.",
            "32",
        )
    else:
        terminal_status("SUCCESS", "Patch installed successfully.", "32")

    terminal_heading("Custom provider config")
    terminal_status("CONFIG", "Edit this file to customize provider selection:", "36", detail=config)
    terminal_bullet(
        "providers",
        "Providers displayed in the app menu. Select one before starting or forking a task.",
    )
    terminal_bullet(
        "model_providers",
        "Retained for generated-config compatibility; model IDs do not choose a provider.",
    )
    terminal_bullet(
        "default_provider",
        "Provider selected when the saved choice is missing or no longer valid.",
    )
    terminal_status(
        "LINK",
        "Custom provider IDs must match a [model_providers.<id>] section.",
        "35",
        detail=codex_config,
    )
    terminal_status(
        "KEYS",
        "Do not put API keys in the provider-routing JSON file.",
        "33",
        detail="Keep credentials in the provider authentication configuration or environment.",
    )

    terminal_heading("After editing", "35")
    terminal_status(
        "RELOAD",
        "Save valid JSON, then close and reopen the model/provider menu.",
        "35",
        detail="No repatching or app restart is needed.",
    )

    if backup is not None:
        terminal_heading("Recovery", "34")
        terminal_status("BACKUP", "Clean original app backup:", "34", detail=backup)

    terminal_heading("Important", "33")
    terminal_status(
        "NOTICE",
        "The app now has an ad-hoc signature. A ChatGPT update may replace this patch.",
        "33",
    )
    print()


def fail(message: str, exit_code: int = 1) -> NoReturn:
    terminal_panel("Error", message, "31", stream=sys.stderr)
    raise SystemExit(exit_code)


def run(
    command: list[str],
    *,
    cwd: Path | None = None,
    label: str | None = None,
) -> subprocess.CompletedProcess[str]:
    terminal_status(
        "STEP",
        label or f"Running {Path(command[0]).name}",
        "36",
        detail=shlex.join(command),
    )
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
    except subprocess.CalledProcessError as exc:
        output = exc.stdout.strip() if exc.stdout else ""
        if output:
            terminal_panel("Command output", output, "31", stream=sys.stderr)
        raise PatchError(f"Command failed with exit status {exc.returncode}") from exc


class FancyArgumentParser(argparse.ArgumentParser):
    def _print_message(self, message: str, file: Any = None) -> None:
        if not message:
            return
        stream = file or sys.stdout
        width = terminal_width()
        title = " COMMAND HELP "
        top_left, bottom_left, horizontal, vertical = terminal_box_characters(stream)
        top = f"{top_left}{horizontal}{title}{horizontal * max(1, width - len(title) - 2)}"
        bottom = f"{bottom_left}{horizontal * (width - 1)}"
        print(file=stream)
        print(color(top, "1", "36", stream=stream), file=stream)
        for raw_line in message.rstrip().splitlines():
            stripped = raw_line.strip()
            border = color(vertical, "36", stream=stream)
            if not stripped:
                print(border, file=stream)
                continue
            if raw_line.startswith("usage:"):
                label, remainder = raw_line.split(":", 1)
                rendered = (
                    color(label.upper(), "1", "35", stream=stream)
                    + color(":", "35", stream=stream)
                    + color(remainder, "1", stream=stream)
                )
            elif stripped in {"options:", "optional arguments:"}:
                rendered = color(stripped.upper(), "1", "36", stream=stream)
            elif raw_line.startswith("  -"):
                option_and_help = re.split(r"(\s{2,})", stripped, maxsplit=1)
                option = option_and_help[0]
                remainder = "".join(option_and_help[1:])
                rendered = (
                    "  "
                    + color(option, "1", "33", stream=stream)
                    + color(remainder, stream=stream)
                )
            else:
                rendered = color(raw_line, stream=stream)
            print(f"{border} {rendered}", file=stream)
        print(color(bottom, "1", "36", stream=stream), file=stream)
        print(file=stream)
        stream.flush()

    def error(self, message: str) -> NoReturn:
        terminal_panel("Argument error", message, "31", stream=sys.stderr)
        terminal_status(
            "HELP",
            "Show all installer options with:",
            "33",
            detail=f"{self.prog} --help",
            stream=sys.stderr,
        )
        self.exit(2)


def invoking_user_home() -> Path:
    sudo_user = os.environ.get("SUDO_USER")
    if sudo_user and sudo_user != "root" and pwd is not None:
        try:
            return Path(pwd.getpwnam(sudo_user).pw_dir)
        except KeyError:
            pass
    return Path.home()


def effective_codex_home() -> Path:
    configured_codex_home = os.environ.get("CODEX_HOME")
    if configured_codex_home:
        return Path(configured_codex_home).expanduser()
    return invoking_user_home() / ".codex"


def managed_backup_paths(app: Path) -> tuple[Path, Path]:
    return (
        app.with_name(f"{app.stem}-original.backup"),
        app.with_name(f"{app.stem}-previous.backup"),
    )


@dataclasses.dataclass(frozen=True)
class WindowsStorePackage:
    name: str
    package_full_name: str
    package_family_name: str
    version: str
    architecture: str
    install_location: Path
    manifest_path: Path
    asar_path: Path


@dataclasses.dataclass(frozen=True)
class WindowsToolPaths:
    makeappx: Path
    signtool: Path


@dataclasses.dataclass(frozen=True)
class WindowsPackageIdentity:
    name: str
    publisher: str
    version: str


@dataclasses.dataclass(frozen=True)
class WindowsSigningCertificate:
    subject: str
    thumbprint: str


@dataclasses.dataclass(frozen=True)
class WindowsPatchPaths:
    root: Path
    original: Path
    active: Path
    previous: Path


def windows_patch_paths(local_app_data: Path) -> WindowsPatchPaths:
    root = local_app_data / "Codex" / "ChatGPTProviderPatch"
    return WindowsPatchPaths(
        root=root,
        original=root / "original",
        active=root / "active",
        previous=root / "previous",
    )


def discover_windows_store_package(command_runner: Any) -> WindowsStorePackage:
    command = [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        (
            f"Get-AppxPackage -Name '{WINDOWS_STORE_PACKAGE_NAME}' | "
            "Select-Object Name, PackageFullName, PackageFamilyName, Version, "
            "Architecture, InstallLocation | ConvertTo-Json -Compress"
        ),
    ]
    result = command_runner(command)
    output = result.stdout.strip()
    if not output:
        raise PatchError("Expected exactly one Windows Store ChatGPT package")
    try:
        package = json.loads(output)
    except json.JSONDecodeError as exc:
        raise PatchError("Could not parse the Windows Store package details") from exc
    if not isinstance(package, dict):
        raise PatchError("Expected exactly one Windows Store ChatGPT package")

    fields = {
        "name": "Name",
        "package_full_name": "PackageFullName",
        "package_family_name": "PackageFamilyName",
        "version": "Version",
        "architecture": "Architecture",
        "install_location": "InstallLocation",
    }
    values: dict[str, str] = {}
    for attribute, field in fields.items():
        value = package.get(field)
        if not isinstance(value, str) or not value.strip():
            raise PatchError(f"Windows Store package is missing {field}")
        values[attribute] = value.strip()

    install_location = Path(values["install_location"])
    manifest_path = install_location / "AppxManifest.xml"
    asar_candidates = tuple(install_location.glob("resources/app.asar"))
    if not install_location.is_dir():
        raise PatchError(f"Windows Store package layout is unreadable: {install_location}")
    if not manifest_path.is_file():
        raise PatchError(f"Windows Store package is missing manifest: {manifest_path}")
    if len(asar_candidates) != 1 or not asar_candidates[0].is_file():
        raise PatchError("Windows Store package must contain exactly one resources/app.asar")

    return WindowsStorePackage(
        name=values["name"],
        package_full_name=values["package_full_name"],
        package_family_name=values["package_family_name"],
        version=values["version"],
        architecture=values["architecture"],
        install_location=install_location,
        manifest_path=manifest_path,
        asar_path=asar_candidates[0],
    )


def find_windows_sdk_tools(search_roots: Sequence[Path]) -> WindowsToolPaths:
    missing_tool_error: PatchError | None = None
    for root in search_roots:
        for makeappx in sorted(root.rglob("MakeAppx.exe")):
            if not makeappx.is_file():
                continue
            signtool = makeappx.with_name("SignTool.exe")
            if signtool.is_file():
                return WindowsToolPaths(makeappx=makeappx, signtool=signtool)
        if any(candidate.is_file() for candidate in root.rglob("MakeAppx.exe")):
            missing_tool_error = PatchError(
                f"Windows SDK tool not found: SignTool.exe under {root}"
            )
        elif (
            any(candidate.is_file() for candidate in root.rglob("SignTool.exe"))
            and missing_tool_error is None
        ):
            missing_tool_error = PatchError(
                f"Windows SDK tool not found: MakeAppx.exe under {root}"
            )
    if missing_tool_error is not None:
        raise missing_tool_error
    raise PatchError("Windows SDK tools not found: MakeAppx.exe and SignTool.exe")


def windows_package_identity(
    store_package_name: str, version: str, publisher: str
) -> WindowsPackageIdentity:
    return WindowsPackageIdentity(
        name=f"{store_package_name}.CodexPatch",
        publisher=publisher,
        version=version,
    )


def windows_signing_certificate(command_runner: Any) -> WindowsSigningCertificate:
    script = textwrap.dedent(
        """\
        $ErrorActionPreference = 'Stop'
        $subject = 'CN=Codex Provider Patch'
        $codeSigningOid = '1.3.6.1.5.5.7.3.3'
        $certificate = Get-ChildItem -Path Cert:\\CurrentUser\\My |
            Where-Object {
                $_.Subject -eq $subject -and $_.HasPrivateKey -and
                $_.EnhancedKeyUsageList.ObjectId -contains $codeSigningOid
            } |
            Select-Object -First 1
        if ($null -eq $certificate) {
            $certificate = New-SelfSignedCertificate -Type CodeSigningCert `
                -Subject $subject -CertStoreLocation Cert:\\CurrentUser\\My
        }
        $trusted = Get-ChildItem -Path Cert:\\LocalMachine\\TrustedPeople |
            Where-Object { $_.Thumbprint -eq $certificate.Thumbprint } |
            Select-Object -First 1
        if ($null -eq $trusted) {
            $publicCertificate = Join-Path ([System.IO.Path]::GetTempPath()) `
                ("CodexProviderPatch-" + [System.Guid]::NewGuid().ToString() + ".cer")
            try {
                Export-Certificate -Cert $certificate -FilePath $publicCertificate |
                    Out-Null
                Import-Certificate -FilePath $publicCertificate `
                    -CertStoreLocation Cert:\\LocalMachine\\TrustedPeople | Out-Null
            }
            finally {
                Remove-Item -LiteralPath $publicCertificate -Force -ErrorAction SilentlyContinue
            }
        }
        [pscustomobject]@{
            Subject = $certificate.Subject
            Thumbprint = $certificate.Thumbprint
        } | ConvertTo-Json -Compress
        """
    )
    command = [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        script,
    ]
    try:
        result = command_runner(command)
        if getattr(result, "returncode", 0) != 0:
            raise PatchError("Could not create or trust the Windows signing certificate")
        payload = json.loads(result.stdout.strip())
    except PatchError:
        raise
    except Exception as exc:
        raise PatchError("Could not create or trust the Windows signing certificate") from exc

    if not isinstance(payload, dict):
        raise PatchError("Windows signing certificate command returned invalid JSON")
    subject = payload.get("Subject")
    thumbprint = payload.get("Thumbprint")
    if not isinstance(subject, str) or not subject.strip():
        raise PatchError("Windows signing certificate command omitted Subject")
    if not isinstance(thumbprint, str) or not thumbprint.strip():
        raise PatchError("Windows signing certificate command omitted Thumbprint")
    return WindowsSigningCertificate(subject.strip(), thumbprint.strip())


def rewrite_windows_manifest_identity(
    contents: str, identity: WindowsPackageIdentity
) -> str:
    try:
        root = ET.fromstring(contents)
    except ET.ParseError as exc:
        raise PatchError("Windows package manifest is malformed XML") from exc

    identity_element = next(
        (
            element
            for element in root
            if element.tag.rsplit("}", 1)[-1] == "Identity"
        ),
        None,
    )
    if identity_element is None:
        raise PatchError("Windows package manifest has no Identity element")
    identity_element.set("Name", identity.name)
    identity_element.set("Publisher", identity.publisher)
    identity_element.set("Version", identity.version)

    if root.tag.startswith("{"):
        ET.register_namespace("", root.tag[1:].split("}", 1)[0])
    return ET.tostring(root, encoding="unicode")


def _run_windows_package_command(command_runner: Any, command: list[str]) -> None:
    try:
        result = command_runner(command)
    except PatchError:
        raise
    except Exception as exc:
        raise PatchError(f"Windows package command failed: {command[0]}") from exc
    if getattr(result, "returncode", 0) != 0:
        raise PatchError(f"Windows package command failed: {command[0]}")


def update_windows_asar_integrity(layout: Path, asar_path: Path) -> None:
    integrity_path = layout / "resources" / "asar-integrity.json"
    if not integrity_path.is_file():
        return
    try:
        integrity = json.loads(integrity_path.read_text(encoding="utf-8"))
        asar_entry = integrity["resources/app.asar"]
        if not isinstance(asar_entry, dict):
            raise TypeError("ASAR entry is not an object")
        asar_entry["hash"] = asar_header_hash(asar_path)
    except (OSError, json.JSONDecodeError, KeyError, TypeError, PatchError) as exc:
        raise PatchError("Windows ASAR integrity manifest is invalid") from exc
    try:
        integrity_path.write_text(
            json.dumps(integrity, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise PatchError("Could not update Windows ASAR integrity manifest") from exc


def build_windows_patched_msix(
    package: WindowsStorePackage,
    original_layout: Path,
    work: Path,
    tools: WindowsToolPaths,
    certificate: WindowsSigningCertificate,
    command_runner: Any,
) -> Path:
    source_asar = original_layout / "resources" / "app.asar"
    if contains_marker(source_asar):
        raise PatchError("The clean original Windows payload is already patched")

    layout = work / "layout"
    extracted = work / "app"
    output = work / "ChatGPT-CodexPatch.msix"
    try:
        work.mkdir(parents=True, exist_ok=True)
        shutil.copytree(original_layout, layout)
    except OSError as exc:
        raise PatchError("Could not copy the clean Windows package layout") from exc

    copied_asar = layout / "resources" / "app.asar"
    _run_windows_package_command(
        command_runner,
        ["npx", "--yes", ASAR_PACKAGE, "extract", str(copied_asar), str(extracted)],
    )
    bundle = current_patch_bundle(extracted / "webview" / "assets")
    patch_current_bundle(bundle)
    _run_windows_package_command(
        command_runner,
        ["npx", "--yes", ASAR_PACKAGE, "pack", str(extracted), str(copied_asar)],
    )
    if not contains_marker(copied_asar):
        raise PatchError("Packed Windows ASAR does not contain the patch marker")

    update_windows_asar_integrity(layout, copied_asar)
    manifest_path = layout / "AppxManifest.xml"
    try:
        manifest_path.write_text(
            rewrite_windows_manifest_identity(
                manifest_path.read_text(encoding="utf-8"),
                windows_package_identity(
                    package.name,
                    package.version,
                    certificate.subject,
                ),
            ),
            encoding="utf-8",
        )
    except OSError as exc:
        raise PatchError("Could not rewrite the Windows package manifest") from exc

    _run_windows_package_command(
        command_runner,
        [str(tools.makeappx), "pack", "/d", str(layout), "/p", str(output)],
    )
    _run_windows_package_command(
        command_runner,
        [
            str(tools.signtool),
            "sign",
            "/fd",
            "SHA256",
            "/sha1",
            certificate.thumbprint,
            "/s",
            "My",
            str(output),
        ],
    )
    _run_windows_package_command(
        command_runner,
        [str(tools.signtool), "verify", "/pa", "/v", str(output)],
    )
    return output


def parse_args() -> argparse.Namespace:
    codex_home = effective_codex_home()
    parser = FancyArgumentParser(
        description=(
            "Add an explicit provider selector to the macOS ChatGPT/Codex desktop app. "
            "Supports ChatGPT 26.721.31836 build 5828."
        )
    )
    parser.add_argument(
        "--app",
        type=Path,
        default=Path("/Applications/ChatGPT.app"),
        help="ChatGPT.app to patch (default: /Applications/ChatGPT.app)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=codex_home / "desktop-model-providers.json",
        help="Provider-routing JSON file in the effective Codex home",
    )
    parser.add_argument(
        "--reapply-from",
        type=Path,
        help="Seed the sibling original from this matching clean app backup",
    )
    parser.add_argument(
        "--overwrite-config",
        action="store_true",
        help="Replace the provider-routing JSON with the built-in template",
    )
    parser.add_argument(
        "--allow-running",
        action="store_true",
        help="Do not close target-app processes before patching (unsafe)",
    )
    return parser.parse_args()


def validate_provider_config(data: Any) -> None:
    if not isinstance(data, dict):
        raise PatchError("Provider config must be a JSON object")
    if data.get("version") != 1:
        raise PatchError("Provider config version must be 1")
    providers = data.get("providers")
    if not isinstance(providers, list) or not providers:
        raise PatchError("Provider config 'providers' must be a non-empty array")

    provider_ids: set[str] = set()
    for provider in providers:
        if not isinstance(provider, dict):
            raise PatchError("Every provider must be an object")
        provider_id = provider.get("id")
        if not isinstance(provider_id, str) or not provider_id.strip():
            raise PatchError("Every provider id must be a non-empty string")
        provider_id = provider_id.strip()
        if provider_id in provider_ids:
            raise PatchError(f"Duplicate provider id: {provider_id}")
        provider_ids.add(provider_id)
        label = provider.get("label")
        if not isinstance(label, str) or not label.strip():
            raise PatchError(f"Provider '{provider_id}' needs a non-empty label")
        description = provider.get("description", "")
        if not isinstance(description, str):
            raise PatchError(f"Provider '{provider_id}' description must be a string")

    default_provider = data.get("default_provider")
    if default_provider not in provider_ids:
        raise PatchError("default_provider must reference a configured provider")

    mappings = data.get("model_providers")
    if not isinstance(mappings, dict):
        raise PatchError("model_providers must be an object")
    for model, provider_id in mappings.items():
        if not isinstance(model, str) or not model.strip():
            raise PatchError("Every model mapping key must be a non-empty string")
        if provider_id not in provider_ids:
            raise PatchError(
                f"Model '{model}' references unknown provider '{provider_id}'"
            )


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _windows_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(4 * 1024 * 1024):
                digest.update(chunk)
    except OSError as exc:
        raise PatchError(f"Could not read Windows package artifact: {path}") from exc
    return digest.hexdigest()


def _remove_windows_path(path: Path) -> None:
    if not path.exists():
        return
    try:
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()
    except OSError as exc:
        raise PatchError(f"Could not remove Windows patch artifact: {path}") from exc


def _windows_identity_element(manifest_path: Path) -> tuple[ET.Element, ET.Element]:
    try:
        root = ET.fromstring(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ET.ParseError) as exc:
        raise PatchError(f"Windows package manifest is invalid: {manifest_path}") from exc
    identity = next(
        (
            element
            for element in root.iter()
            if element.tag.rsplit("}", 1)[-1] == "Identity"
        ),
        None,
    )
    if identity is None:
        raise PatchError(f"Windows package manifest has no Identity element: {manifest_path}")
    return root, identity


def _validate_windows_store_layout(
    layout: Path, package: WindowsStorePackage
) -> tuple[Path, dict[str, str]]:
    manifest_path = layout / "AppxManifest.xml"
    if not layout.is_dir() or not manifest_path.is_file():
        raise PatchError(f"Windows Store package layout is unreadable: {layout}")

    _root, identity = _windows_identity_element(manifest_path)
    identity_name = identity.get("Name")
    identity_version = identity.get("Version")
    if identity_name != package.name:
        raise PatchError(
            "Windows Store package manifest identity does not match the package name"
        )
    if identity_version != package.version:
        raise PatchError(
            "Windows Store package manifest identity does not match the package version"
        )

    expected_prefix = f"{package.name}_{package.version}_".lower()
    full_name = package.package_full_name.strip()
    if not full_name.lower().startswith(expected_prefix):
        raise PatchError(
            "Windows Store package full name does not match its manifest identity"
        )
    architecture = package.architecture.strip().lower()
    full_name_parts = full_name.split("_")
    if len(full_name_parts) < 4 or architecture not in full_name_parts[2].lower():
        raise PatchError(
            "Windows Store package full name does not match its architecture"
        )

    asar_candidates = tuple(
        candidate
        for candidate in (layout / "resources").glob("app.asar")
        if candidate.is_file()
    ) if (layout / "resources").is_dir() else ()
    if len(asar_candidates) != 1:
        raise PatchError(
            "Windows Store package must contain exactly one resources/app.asar"
        )
    asar_path = asar_candidates[0]
    try:
        marked = contains_marker(asar_path)
    except OSError as exc:
        raise PatchError(f"Could not inspect Windows ASAR: {asar_path}") from exc
    if marked:
        raise PatchError("The clean original Windows payload is already patched")

    # A Store layout keeps the JavaScript bundle inside app.asar.  When a
    # fixture or future package exposes the extracted assets, validate its
    # exact build markers now; otherwise build_windows_patched_msix performs
    # the same validation immediately before mutation.
    assets = layout / "webview" / "assets"
    if assets.is_dir():
        try:
            current_patch_bundle(assets)
        except PatchError:
            raise
        except Exception as exc:
            raise PatchError("Windows Store source bundle markers are unsupported") from exc

    return asar_path, {
        "name": package.name,
        "package_full_name": full_name,
        "package_family_name": package.package_family_name,
        "version": package.version,
        "architecture": package.architecture,
        "manifest_name": identity_name or "",
        "manifest_version": identity_version or "",
    }


def ensure_windows_original(
    package: WindowsStorePackage,
    paths: WindowsPatchPaths,
    *,
    command_runner: Any | None = None,
) -> Path:
    """Create a verified clean copy without touching active deployment state."""

    paths.root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".original-", dir=paths.root))
    candidate = staging / paths.original.name
    displaced = staging / "displaced-original"
    preserve_staging = False
    try:
        try:
            shutil.copytree(package.install_location, candidate)
        except OSError as exc:
            raise PatchError(
                f"Could not copy the Windows Store payload into staging: "
                f"{package.install_location}"
            ) from exc

        asar_path, metadata = _validate_windows_store_layout(candidate, package)
        if command_runner is None:
            command_runner = run_windows_command
        extracted = staging / "source-validation"
        _run_windows_package_command(
            command_runner,
            [
                "npx",
                "--yes",
                ASAR_PACKAGE,
                "extract",
                str(asar_path),
                str(extracted),
            ],
        )
        current_patch_bundle(extracted / "webview" / "assets")
        metadata.update(
            {
                "kind": "windows-store-original",
                "source_version": package.version,
                "store_package_full_name": package.package_full_name,
            }
        )
        # Identity metadata is written only after the staged payload has
        # passed every clean-source check.
        atomic_write_json(candidate / "package.json", metadata)

        if paths.original.exists():
            os.replace(paths.original, displaced)
        try:
            os.replace(candidate, paths.original)
        except Exception as promotion_exc:
            if displaced.exists() and not paths.original.exists():
                try:
                    os.replace(displaced, paths.original)
                except Exception as restore_exc:
                    preserve_staging = True
                    raise PatchError(
                        "Could not restore the displaced Windows original; "
                        f"recovery data remains at: {displaced.resolve()}"
                    ) from restore_exc
            raise promotion_exc
        if displaced.exists():
            _remove_windows_path(displaced)
        return paths.original
    finally:
        if not preserve_staging:
            shutil.rmtree(staging, ignore_errors=True)


def _windows_metadata(path: Path) -> dict[str, Any]:
    metadata_path = path / "package.json"
    if not metadata_path.is_file():
        return {}
    try:
        value = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PatchError(f"Windows patch metadata is invalid: {metadata_path}") from exc
    if not isinstance(value, dict):
        raise PatchError(f"Windows patch metadata must be a JSON object: {metadata_path}")
    return value


def _windows_active_msix(path: Path) -> Path:
    if not path.is_dir():
        raise PatchError(f"Windows active artifact is not a directory: {path}")
    candidates = tuple(
        candidate for candidate in path.glob("*.msix") if candidate.is_file()
    )
    if len(candidates) != 1:
        raise PatchError(
            "Windows active artifact must contain exactly one signed .msix package"
        )
    return candidates[0]


def snapshot_windows_active(paths: WindowsPatchPaths) -> Path | None:
    """Atomically preserve the current active package for a replacement."""

    paths.root.mkdir(parents=True, exist_ok=True)
    if paths.previous.exists():
        raise PatchError(
            f"A previous Windows package snapshot already exists; recover or "
            f"remove it first: {paths.previous}"
        )
    if not paths.active.exists():
        return None

    source_msix = _windows_active_msix(paths.active)
    staging = Path(tempfile.mkdtemp(prefix=".previous-", dir=paths.root))
    candidate = staging / paths.previous.name
    try:
        try:
            shutil.copytree(paths.active, candidate)
        except OSError as exc:
            raise PatchError("Could not stage the active Windows package snapshot") from exc
        copied_msix = candidate / source_msix.name
        if _windows_sha256(source_msix) != _windows_sha256(copied_msix):
            raise PatchError("Windows active package snapshot digest verification failed")
        os.replace(candidate, paths.previous)
        return paths.previous
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _windows_default_metadata(paths: WindowsPatchPaths) -> dict[str, Any]:
    original = _windows_metadata(paths.original) if paths.original.exists() else {}
    store_name = str(
        original.get("name") or original.get("store_package_name") or WINDOWS_STORE_PACKAGE_NAME
    )
    store_full_name = str(
        original.get("store_package_full_name")
        or original.get("package_full_name")
        or ""
    )
    source_version = str(
        original.get("source_version") or original.get("version") or ""
    )
    custom_name = str(original.get("custom_package_name") or f"{store_name}.CodexPatch")
    return {
        "kind": "windows-store-active",
        "custom_package_name": custom_name,
        "custom_package_full_name": custom_name,
        "store_package_full_name": store_full_name,
        "source_version": source_version,
    }


def promote_windows_active(
    candidate_msix: Path,
    paths: WindowsPatchPaths,
    *,
    metadata: dict[str, Any] | None = None,
) -> Path:
    """Promote a verified MSIX by swapping staged directories atomically."""

    candidate_msix = Path(candidate_msix)
    if not candidate_msix.is_file():
        raise PatchError(f"Windows candidate MSIX is missing: {candidate_msix}")
    paths.root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".active-", dir=paths.root))
    candidate_dir = staging / paths.active.name
    displaced = staging / "displaced-active"
    preserve_staging = False
    try:
        candidate_dir.mkdir()
        staged_msix = candidate_dir / candidate_msix.name
        shutil.copyfile(candidate_msix, staged_msix)
        candidate_hash = _windows_sha256(candidate_msix)
        if _windows_sha256(staged_msix) != candidate_hash:
            raise PatchError("Windows candidate package digest verification failed")
        active_metadata = _windows_default_metadata(paths)
        if metadata:
            active_metadata.update(metadata)
        active_metadata["candidate_sha256"] = candidate_hash
        active_metadata["sha256"] = candidate_hash
        active_metadata["candidate_name"] = candidate_msix.name
        atomic_write_json(candidate_dir / "package.json", active_metadata)

        if paths.active.exists():
            os.replace(paths.active, displaced)
        try:
            os.replace(candidate_dir, paths.active)
        except Exception as promotion_exc:
            if displaced.exists() and not paths.active.exists():
                try:
                    os.replace(displaced, paths.active)
                except Exception as restore_exc:
                    preserve_staging = True
                    raise PatchError(
                        "Could not restore the displaced Windows active artifact; "
                        f"recovery data remains at: {displaced.resolve()}"
                    ) from restore_exc
            raise promotion_exc
        if displaced.exists():
            _remove_windows_path(displaced)
        return paths.active
    finally:
        if not preserve_staging:
            shutil.rmtree(staging, ignore_errors=True)


def restore_windows_previous(paths: WindowsPatchPaths) -> Path:
    """Restore the on-disk active artifact while retaining previous evidence."""

    if not paths.previous.exists():
        raise PatchError(f"Windows previous snapshot is missing: {paths.previous}")
    source_msix = _windows_active_msix(paths.previous)
    staging = Path(tempfile.mkdtemp(prefix=".active-rollback-", dir=paths.root))
    candidate = staging / paths.active.name
    displaced = staging / "displaced-active"
    preserve_staging = False
    try:
        shutil.copytree(paths.previous, candidate)
        copied_msix = candidate / source_msix.name
        if _windows_sha256(source_msix) != _windows_sha256(copied_msix):
            raise PatchError("Windows rollback package digest verification failed")
        if paths.active.exists():
            os.replace(paths.active, displaced)
        try:
            os.replace(candidate, paths.active)
        except Exception as promotion_exc:
            if displaced.exists() and not paths.active.exists():
                try:
                    os.replace(displaced, paths.active)
                except Exception as restore_exc:
                    preserve_staging = True
                    raise PatchError(
                        "Could not restore the displaced Windows active artifact; "
                        f"recovery data remains at: {displaced.resolve()}"
                    ) from restore_exc
            raise promotion_exc
        if displaced.exists():
            _remove_windows_path(displaced)
        return paths.active
    finally:
        if not preserve_staging:
            shutil.rmtree(staging, ignore_errors=True)


def _windows_powershell_command(script: str) -> list[str]:
    return [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        script,
    ]


def run_windows_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _windows_custom_name(paths: WindowsPatchPaths) -> str:
    return str(_windows_default_metadata(paths)["custom_package_name"])


def _windows_store_full_name(paths: WindowsPatchPaths) -> str:
    return str(_windows_default_metadata(paths)["store_package_full_name"])


def _windows_active_identity(
    metadata: dict[str, Any], custom_name: str
) -> tuple[str, str, str, str]:
    """Return validated immutable registration selectors for an active artifact."""

    package_full_name = metadata.get("custom_package_full_name")
    if not isinstance(package_full_name, str) or not package_full_name.strip():
        raise PatchError(
            "Windows active package metadata omitted a valid PackageFullName"
        )
    package_full_name = package_full_name.strip()
    full_name_prefix = f"{custom_name}_"
    if not package_full_name.startswith(full_name_prefix):
        raise PatchError(
            "Windows active package metadata omitted a valid PackageFullName"
        )
    full_name_parts = package_full_name[len(full_name_prefix):].split("_")
    if (
        len(full_name_parts) != 4
        or full_name_parts[1].lower()
        not in {"x86", "x64", "arm", "arm64", "neutral"}
        or re.fullmatch(r"[A-Za-z0-9.-]*", full_name_parts[2]) is None
        or re.fullmatch(
            r"[0-9a-hj-km-np-tv-z]{13}", full_name_parts[3]
        ) is None
    ):
        raise PatchError(
            "Windows active package metadata omitted a valid PackageFullName"
        )
    fields = {
        "PackageFamilyName": metadata.get("custom_package_family_name"),
        "Publisher": metadata.get("custom_package_publisher"),
        "source version": metadata.get("source_version"),
    }
    for label, value in fields.items():
        if not isinstance(value, str) or not value.strip():
            raise PatchError(
                f"Windows active package metadata omitted a valid {label}"
            )
    package_family_name = str(fields["PackageFamilyName"]).strip()
    publisher = str(fields["Publisher"]).strip()
    source_version = str(fields["source version"]).strip()
    version_parts = source_version.split(".")
    if (
        len(version_parts) != 4
        or any(re.fullmatch(r"[0-9]+", part) is None for part in version_parts)
        or any(int(part) > 65535 for part in version_parts)
    ):
        raise PatchError(
            "Windows active package metadata omitted a valid source version"
        )
    if full_name_parts[0] != source_version:
        raise PatchError(
            "Windows active package metadata omitted a valid PackageFullName"
        )
    if package_family_name != f"{custom_name}_{full_name_parts[3]}":
        raise PatchError(
            "Windows active package metadata omitted a valid PackageFamilyName"
        )
    return package_full_name, package_family_name, publisher, source_version


def _windows_candidate_identity(candidate_msix: Path, custom_name: str) -> dict[str, str]:
    """Read the custom identity from a packaged MSIX when it is available.

    Unit tests use byte placeholders for candidates, so an unreadable ZIP is
    treated as an unknown identity. Real MakeAppx output is a ZIP package and
    must carry the expected custom name; its publisher/version become
    verification filters before accepting a same-name registration.
    """

    try:
        with zipfile.ZipFile(candidate_msix) as package:
            manifest_name = next(
                (
                    name
                    for name in package.namelist()
                    if name.replace("\\", "/").lower() == "appxmanifest.xml"
                ),
                None,
            )
            if manifest_name is None:
                return {}
            contents = package.read(manifest_name).decode("utf-8")
    except (
        OSError,
        KeyError,
        UnicodeDecodeError,
        zipfile.BadZipFile,
    ):
        return {}
    _root, identity = _windows_identity_element_from_text(contents)
    name = identity.get("Name") or ""
    publisher = identity.get("Publisher") or ""
    version = identity.get("Version") or ""
    if name != custom_name:
        raise PatchError(
            "Windows candidate MSIX manifest has the wrong custom package identity"
        )
    return {
        "custom_package_name": name,
        "custom_package_publisher": publisher,
        "source_version": version,
    }


def _windows_identity_element_from_text(contents: str) -> tuple[ET.Element, ET.Element]:
    try:
        root = ET.fromstring(contents)
    except ET.ParseError as exc:
        raise PatchError("Windows package manifest is malformed XML") from exc
    identity = next(
        (
            element
            for element in root.iter()
            if element.tag.rsplit("}", 1)[-1] == "Identity"
        ),
        None,
    )
    if identity is None:
        raise PatchError("Windows package manifest has no Identity element")
    return root, identity


def _windows_registration_match_lines(
    custom_name: str,
    *,
    expected_full_name: str = "",
    expected_family_name: str = "",
    expected_publisher: str = "",
    expected_version: str = "",
) -> list[str]:
    escaped_name = custom_name.replace("'", "''")
    conditions = [f"$_.Name -eq '{escaped_name}'"]
    if expected_full_name:
        conditions.append(
            f"$_.PackageFullName -eq '{expected_full_name.replace(chr(39), chr(39) * 2)}'"
        )
    if expected_family_name:
        conditions.append(
            f"$_.PackageFamilyName -eq "
            f"'{expected_family_name.replace(chr(39), chr(39) * 2)}'"
        )
    if expected_publisher:
        conditions.append(
            f"$_.Publisher -eq "
            f"'{expected_publisher.replace(chr(39), chr(39) * 2)}'"
        )
    if expected_version:
        conditions.append(
            f"$_.Version.ToString() -eq "
            f"'{expected_version.replace(chr(39), chr(39) * 2)}'"
        )
    return [
        f"$packages = @(Get-AppxPackage -Name '{escaped_name}')",
        "$customMatches = @($packages | Where-Object {",
        "  " + " -and ".join(conditions),
        "})",
        "if ($customMatches.Count -ne 1) { "
        "throw 'Expected exactly one matching custom package registration' }",
        "$custom = $customMatches[0]",
    ]


def _windows_add_script(
    candidate_msix: Path,
    custom_name: str,
    *,
    allow_running: bool,
    allow_existing: bool,
    expected_full_name: str = "",
    expected_family_name: str = "",
    expected_publisher: str = "",
    expected_version: str = "",
) -> str:
    escaped_path = str(candidate_msix).replace("'", "''")
    escaped_name = custom_name.replace("'", "''")
    lines = ["$ErrorActionPreference = 'Stop'"]
    if not allow_existing:
        lines.extend(
            [
                f"$existing = @(Get-AppxPackage -Name '{escaped_name}')",
                "if ($existing.Count -ne 0) { "
                "throw 'An unmanaged custom package is already registered' }",
            ]
        )
    else:
        lines.extend(
            _windows_registration_match_lines(
                custom_name,
                expected_full_name=expected_full_name,
                expected_family_name=expected_family_name,
                expected_publisher=expected_publisher,
                expected_version=expected_version,
            )
        )
        lines.append(
            "if ($packages.Count -ne 1) { "
            "throw 'Unexpected additional custom package registration' }"
        )
    if not allow_running:
        lines.extend(
            [
                "if ($null -ne $custom) {",
                "  $prefix = [System.IO.Path]::GetFullPath($custom.InstallLocation).TrimEnd('\\') + '\\'",
                "  Get-CimInstance Win32_Process | ForEach-Object {",
                "    if ($_.ExecutablePath -and $_.ExecutablePath.StartsWith("
                "$prefix, [System.StringComparison]::OrdinalIgnoreCase)) {",
                "      Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop",
                "    }",
                "  }",
                "}",
            ]
        )
    lines.append(
        f"Add-AppxPackage -Path '{escaped_path}' -ForceApplicationShutdown"
    )
    return "\n".join(lines)


def _windows_query_script(custom_name: str) -> str:
    return _windows_query_script_for_identity(custom_name)


def _windows_query_script_for_identity(
    custom_name: str,
    *,
    expected_full_name: str = "",
    expected_family_name: str = "",
    expected_publisher: str = "",
    expected_version: str = "",
) -> str:
    marker = PATCH_MARKER.decode().replace("'", "''")
    lines = ["$ErrorActionPreference = 'Stop'"]
    lines.extend(
        _windows_registration_match_lines(
            custom_name,
            expected_full_name=expected_full_name,
            expected_family_name=expected_family_name,
            expected_publisher=expected_publisher,
            expected_version=expected_version,
        )
    )
    lines.extend(
        [
            "$asar = Join-Path $custom.InstallLocation 'resources\\app.asar'",
            "if (-not (Test-Path -LiteralPath $asar -PathType Leaf)) { "
            "throw 'Custom package ASAR is missing' }",
            f"$marker = '{marker}'",
            "$bytes = [System.IO.File]::ReadAllBytes($asar)",
            "$text = [System.Text.Encoding]::GetEncoding(28591).GetString($bytes)",
            "if (-not $text.Contains($marker)) { "
            "throw 'Custom package ASAR marker is missing' }",
            "$custom | Select-Object Name, PackageFullName, PackageFamilyName, "
            "Publisher, Version, InstallLocation | ConvertTo-Json -Compress",
        ]
    )
    return "\n".join(lines)


def _windows_registration_query_script(
    custom_name: str,
    *,
    expected_full_name: str = "",
    expected_family_name: str = "",
    expected_publisher: str = "",
    expected_version: str = "",
) -> str:
    lines = ["$ErrorActionPreference = 'Stop'"]
    lines.extend(
        _windows_registration_match_lines(
            custom_name,
            expected_full_name=expected_full_name,
            expected_family_name=expected_family_name,
            expected_publisher=expected_publisher,
            expected_version=expected_version,
        )
    )
    lines.append(
        "$custom | Select-Object Name, PackageFullName, PackageFamilyName, "
        "Publisher, Version, InstallLocation | ConvertTo-Json -Compress"
    )
    return "\n".join(lines)


def _windows_candidate_registration_snapshot_script(
    custom_name: str,
    *,
    expected_full_name: str = "",
    expected_family_name: str = "",
    expected_publisher: str = "",
    expected_version: str = "",
) -> str:
    """Return full names of every registration matching a candidate identity."""

    lines = ["$ErrorActionPreference = 'Stop'"]
    escaped_name = custom_name.replace("'", "''")
    conditions = [f"$_.Name -eq '{escaped_name}'"]
    if expected_full_name:
        conditions.append(
            f"$_.PackageFullName -eq "
            f"'{expected_full_name.replace(chr(39), chr(39) * 2)}'"
        )
    if expected_family_name:
        conditions.append(
            f"$_.PackageFamilyName -eq "
            f"'{expected_family_name.replace(chr(39), chr(39) * 2)}'"
        )
    if expected_publisher:
        conditions.append(
            f"$_.Publisher -eq "
            f"'{expected_publisher.replace(chr(39), chr(39) * 2)}'"
        )
    if expected_version:
        conditions.append(
            f"$_.Version.ToString() -eq "
            f"'{expected_version.replace(chr(39), chr(39) * 2)}'"
        )
    lines.extend(
        [
            f"$packages = @(Get-AppxPackage -Name '{escaped_name}')",
            "$candidateMatches = @($packages | Where-Object {",
            "  " + " -and ".join(conditions),
            "})",
            "@($candidateMatches | Select-Object -ExpandProperty PackageFullName) | "
            "ConvertTo-Json -Compress",
        ]
    )
    return "\n".join(lines)


def _snapshot_windows_candidate_registrations(
    command_runner: Any,
    custom_name: str,
    *,
    expected_full_name: str = "",
    expected_family_name: str = "",
    expected_publisher: str = "",
    expected_version: str = "",
) -> set[str]:
    """Capture candidate-matching registrations before Add-AppxPackage runs."""

    command = _windows_powershell_command(
        _windows_candidate_registration_snapshot_script(
            custom_name,
            expected_full_name=expected_full_name,
            expected_family_name=expected_family_name,
            expected_publisher=expected_publisher,
            expected_version=expected_version,
        )
    )
    try:
        result = command_runner(command)
    except PatchError:
        raise
    except Exception as exc:
        raise PatchError(
            "Could not snapshot matching custom Windows package registrations"
        ) from exc
    if getattr(result, "returncode", 0) != 0:
        raise PatchError("Could not snapshot matching custom Windows package registrations")
    output = getattr(result, "stdout", "") or ""
    try:
        payload = json.loads(output.strip()) if output.strip() else []
    except json.JSONDecodeError as exc:
        raise PatchError(
            "Custom Windows package registration snapshot returned invalid JSON"
        ) from exc
    if isinstance(payload, str):
        values = [payload]
    elif isinstance(payload, list) and all(isinstance(value, str) for value in payload):
        values = payload
    else:
        raise PatchError(
            "Custom Windows package registration snapshot returned invalid JSON"
        )
    if any(not value.strip() for value in values):
        raise PatchError(
            "Custom Windows package registration snapshot omitted PackageFullName"
        )
    return set(values)


def _windows_remove_script(custom_name: str, package_full_name: str) -> str:
    escaped_name = custom_name.replace("'", "''")
    escaped_full_name = package_full_name.replace("'", "''")
    package_expression = (
        f"Get-AppxPackage -Name '{escaped_name}' | "
        f"Where-Object {{ $_.PackageFullName -eq '{escaped_full_name}' }}"
    )
    return (
        "$ErrorActionPreference = 'Stop'; "
        f"$exactMatches = @({package_expression}); "
        "if ($exactMatches.Count -gt 1) { "
        "throw 'Multiple custom packages matched the exact package identity' }; "
        "if ($exactMatches.Count -eq 1) { Remove-AppxPackage -Package "
        "$exactMatches[0].PackageFullName }"
    )


def _query_windows_custom_package(
    command_runner: Any,
    custom_name: str,
    *,
    expected_full_name: str = "",
    expected_family_name: str = "",
    expected_publisher: str = "",
    expected_version: str = "",
) -> dict[str, Any]:
    command = _windows_powershell_command(
        _windows_query_script_for_identity(
            custom_name,
            expected_full_name=expected_full_name,
            expected_family_name=expected_family_name,
            expected_publisher=expected_publisher,
            expected_version=expected_version,
        )
    )
    try:
        result = command_runner(command)
    except PatchError:
        raise
    except Exception as exc:
        raise PatchError("Could not query the custom Windows package") from exc
    if getattr(result, "returncode", 0) != 0:
        raise PatchError("Could not query the custom Windows package")
    output = getattr(result, "stdout", "") or ""
    if not output.strip():
        raise PatchError("The custom Windows package is not registered")
    try:
        payload = json.loads(output.strip())
    except json.JSONDecodeError as exc:
        raise PatchError("Custom Windows package query returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise PatchError("Custom Windows package query returned invalid JSON")
    return payload


def _query_windows_custom_registration(
    command_runner: Any,
    custom_name: str,
    *,
    expected_full_name: str = "",
    expected_family_name: str = "",
    expected_publisher: str = "",
    expected_version: str = "",
) -> dict[str, Any]:
    """Query registration identity without touching installed package content."""

    command = _windows_powershell_command(
        _windows_registration_query_script(
            custom_name,
            expected_full_name=expected_full_name,
            expected_family_name=expected_family_name,
            expected_publisher=expected_publisher,
            expected_version=expected_version,
        )
    )
    try:
        result = command_runner(command)
    except PatchError:
        raise
    except Exception as exc:
        raise PatchError("Could not query the custom Windows package registration") from exc
    if getattr(result, "returncode", 0) != 0:
        raise PatchError("Could not query the custom Windows package registration")
    output = getattr(result, "stdout", "") or ""
    if not output.strip():
        raise PatchError("The custom Windows package registration was not found")
    try:
        payload = json.loads(output.strip())
    except json.JSONDecodeError as exc:
        raise PatchError(
            "Custom Windows package registration query returned invalid JSON"
        ) from exc
    if not isinstance(payload, dict):
        raise PatchError(
            "Custom Windows package registration query returned invalid JSON"
        )
    if payload.get("Name") != custom_name:
        raise PatchError(
            "Custom Windows package registration has the wrong package name"
        )
    if expected_full_name and payload.get("PackageFullName") != expected_full_name:
        raise PatchError(
            "Custom Windows package registration has the wrong package full name"
        )
    if expected_family_name and payload.get("PackageFamilyName") != expected_family_name:
        raise PatchError(
            "Custom Windows package registration has the wrong package family name"
        )
    if expected_publisher and payload.get("Publisher") != expected_publisher:
        raise PatchError(
            "Custom Windows package registration has the wrong publisher"
        )
    if expected_version and str(payload.get("Version", "")) != str(expected_version):
        raise PatchError(
            "Custom Windows package registration has the wrong version"
        )
    package_full_name = payload.get("PackageFullName")
    if not isinstance(package_full_name, str) or not package_full_name.strip():
        raise PatchError(
            "Custom Windows package registration omitted PackageFullName"
        )
    return payload


def _verify_windows_custom_package(
    payload: dict[str, Any],
    paths: WindowsPatchPaths,
    *,
    expected_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not payload:
        raise PatchError("The custom Windows package is not registered")
    for field in ("PackageFullName", "PackageFamilyName", "Publisher", "Version"):
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            raise PatchError(
                f"Custom Windows package registration omitted {field}"
            )
    expected = expected_metadata or _windows_default_metadata(paths)
    custom_name = str(expected.get("custom_package_name") or _windows_custom_name(paths))
    expected_full_name = str(expected.get("custom_package_full_name") or "")
    if expected_full_name == custom_name:
        expected_full_name = ""
    expected_family_name = str(expected.get("custom_package_family_name") or "")
    expected_publisher = str(expected.get("custom_package_publisher") or "")
    if payload.get("Name") != custom_name:
        raise PatchError("The custom Windows package registration has the wrong identity")
    if expected_full_name and payload.get("PackageFullName") != expected_full_name:
        raise PatchError(
            "The custom Windows package registration has the wrong package full name"
        )
    if expected_family_name and payload.get("PackageFamilyName") != expected_family_name:
        raise PatchError(
            "The custom Windows package registration has the wrong package family name"
        )
    if expected_publisher and payload.get("Publisher") != expected_publisher:
        raise PatchError(
            "The custom Windows package registration has the wrong publisher"
        )
    expected_version = expected.get("source_version")
    if expected_version and str(payload.get("Version", "")) != str(expected_version):
        raise PatchError("The custom Windows package registration has the wrong version")
    install_location = payload.get("InstallLocation")
    if not isinstance(install_location, str) or not install_location.strip():
        raise PatchError("The custom Windows package registration omitted InstallLocation")
    install = Path(install_location)
    asar_candidates = tuple(
        candidate
        for candidate in (install / "resources").glob("app.asar")
        if candidate.is_file()
    ) if (install / "resources").is_dir() else ()
    if len(asar_candidates) != 1:
        raise PatchError("The installed custom Windows package has no unique ASAR")
    try:
        if not contains_marker(asar_candidates[0]):
            raise PatchError("The installed custom Windows ASAR is missing the patch marker")
    except OSError as exc:
        raise PatchError("Could not inspect the installed custom Windows ASAR") from exc
    return payload


def _recover_windows_deployment(
    paths: WindowsPatchPaths,
    command_runner: Any,
    *,
    custom_name: str,
    custom_full_name: str,
    had_previous: bool,
    expected_metadata: dict[str, Any] | None = None,
    preexisting_candidate_full_names: set[str] | None = None,
    registration_attempted: bool = False,
    registration_succeeded: bool = False,
) -> list[str]:
    failures: list[str] = []
    candidate_expected = dict(expected_metadata or {})
    previous_metadata: dict[str, Any] = {}
    if had_previous and paths.previous.exists():
        try:
            previous_metadata = _windows_metadata(paths.previous)
        except Exception as exc:
            failures.append(f"read previous metadata: {exc}")
    candidate_expected_full_name = str(
        candidate_expected.get("candidate_package_full_name") or ""
    )
    candidate_expected_family_name = str(
        candidate_expected.get("candidate_package_family_name")
        or candidate_expected.get("custom_package_family_name")
        or ""
    )
    candidate_expected_publisher = str(
        candidate_expected.get("candidate_package_publisher")
        or candidate_expected.get("custom_package_publisher")
        or ""
    )
    candidate_expected_version = str(
        candidate_expected.get("candidate_source_version")
        or candidate_expected.get("source_version")
        or ""
    )
    candidate_identity_proven = any(
        (
            candidate_expected_full_name,
            candidate_expected_family_name,
            candidate_expected_publisher,
            candidate_expected_version,
        )
    )
    if (
        not custom_full_name
        and registration_attempted
        and (registration_succeeded or candidate_identity_proven)
    ):
        try:
            registered = _query_windows_custom_registration(
                command_runner,
                custom_name,
                expected_full_name=candidate_expected_full_name,
                expected_family_name=candidate_expected_family_name,
                expected_publisher=candidate_expected_publisher,
                expected_version=candidate_expected_version,
            )
            custom_full_name = str(registered.get("PackageFullName") or "")
        except Exception as exc:
            failures.append(f"establish candidate package identity: {exc}")
    if custom_full_name and custom_full_name not in (preexisting_candidate_full_names or set()):
        try:
            _run_windows_package_command(
                command_runner,
                _windows_powershell_command(
                    _windows_remove_script(custom_name, custom_full_name)
                ),
            )
        except Exception as exc:
            failures.append(f"remove custom package: {exc}")

    if had_previous:
        previous_msix: Path | None = None
        try:
            previous_msix = _windows_active_msix(paths.previous)
        except Exception as exc:
            failures.append(f"inspect previous package: {exc}")
        if previous_msix is not None:
            try:
                _run_windows_package_command(
                    command_runner,
                    _windows_powershell_command(
                        _windows_add_script(
                            previous_msix,
                            custom_name,
                            allow_running=True,
                            allow_existing=False,
                        )
                    ),
                )
            except Exception as exc:
                failures.append(f"reinstall previous package: {exc}")
            try:
                rollback_expected = dict(previous_metadata)
                # The rollback package can legitimately be re-registered with
                # a platform-generated full name after Add-AppxPackage. The
                # immutable active full name remains the removal/process
                # selector, while rollback verification checks the package
                # family/name/version and marker.
                rollback_expected.pop("custom_package_full_name", None)
                payload = _query_windows_custom_package(
                    command_runner,
                    custom_name,
                    expected_family_name=str(
                        rollback_expected.get("custom_package_family_name") or ""
                    ),
                    expected_publisher=str(
                        rollback_expected.get("custom_package_publisher") or ""
                    ),
                    expected_version=str(
                        rollback_expected.get("source_version") or ""
                    ),
                )
                _verify_windows_custom_package(
                    payload,
                    paths,
                    expected_metadata=rollback_expected,
                )
            except Exception as exc:
                failures.append(f"verify previous package: {exc}")
        try:
            restore_windows_previous(paths)
        except Exception as exc:
            failures.append(f"restore active artifact: {exc}")
        if not failures:
            try:
                _remove_windows_path(paths.previous)
            except Exception as exc:
                failures.append(f"remove previous snapshot: {exc}")
    else:
        # A first install must not leave a failed candidate as an active
        # artifact.  The official Store app is never touched here.
        try:
            _remove_windows_path(paths.active)
        except Exception as exc:
            failures.append(f"remove failed active artifact: {exc}")
    return failures


def deploy_windows_msix(
    candidate_msix: Path,
    paths: WindowsPatchPaths,
    command_runner: Any,
    *,
    allow_running: bool = False,
) -> Path:
    """Install a signed custom package and transactionally promote its artifact."""

    if paths.previous.exists():
        raise PatchError(
            f"A previous Windows package snapshot requires recovery or removal: "
            f"{paths.previous.resolve()}"
        )
    candidate_msix = Path(candidate_msix)
    if not candidate_msix.is_file():
        raise PatchError(f"Windows candidate MSIX is missing: {candidate_msix}")
    had_previous = paths.active.exists()
    snapshot_created = False
    registration_attempted = False
    registration_succeeded = False
    preexisting_candidate_full_names: set[str] = set()
    custom_name = _windows_custom_name(paths)
    custom_full_name = ""
    expected_metadata: dict[str, Any] = {}
    candidate_identity = _windows_candidate_identity(candidate_msix, custom_name)
    previous_metadata: dict[str, Any] = {}
    if had_previous:
        previous_metadata = _windows_metadata(paths.active)
        expected_metadata.update(previous_metadata)
        (
            pre_add_full_name,
            pre_add_family_name,
            pre_add_publisher,
            pre_add_version,
        ) = _windows_active_identity(
            previous_metadata, custom_name
        )
    else:
        expected_metadata["custom_package_name"] = custom_name
        pre_add_full_name = ""
        pre_add_family_name = ""
        pre_add_publisher = ""
        pre_add_version = ""
    # Add-AppxPackage process shutdown and existing-package checks remain bound
    # to the immutable active identity.  Verification after registration must
    # instead use the candidate manifest's identity/version.
    candidate_name = str(candidate_identity.get("custom_package_name") or custom_name)
    candidate_publisher = str(
        candidate_identity.get("custom_package_publisher") or ""
    )
    candidate_version = str(candidate_identity.get("source_version") or "")
    candidate_full_name = str(
        candidate_identity.get("custom_package_full_name") or ""
    )
    candidate_family_name = str(
        candidate_identity.get("custom_package_family_name") or ""
    )
    post_expected_metadata = dict(expected_metadata)
    post_expected_metadata.update(
        {
            "custom_package_name": candidate_name,
            "custom_package_full_name": candidate_full_name,
            "custom_package_family_name": candidate_family_name,
            "custom_package_publisher": candidate_publisher,
            "source_version": candidate_version,
            "candidate_package_full_name": candidate_full_name,
            "candidate_package_family_name": candidate_family_name,
            "candidate_package_publisher": candidate_publisher,
            "candidate_source_version": candidate_version,
        }
    )
    if not candidate_identity:
        post_expected_metadata = dict(expected_metadata)
    post_expected_full_name = str(
        post_expected_metadata.get("custom_package_full_name") or ""
    )
    if post_expected_full_name == custom_name:
        post_expected_full_name = ""
    post_expected_family_name = str(
        post_expected_metadata.get("custom_package_family_name") or ""
    )
    post_expected_publisher = str(
        post_expected_metadata.get("custom_package_publisher") or ""
    )
    post_expected_version = str(
        post_expected_metadata.get("source_version") or ""
    )
    expected_full_name = pre_add_full_name
    expected_family_name = pre_add_family_name
    expected_publisher = pre_add_publisher
    expected_version = pre_add_version
    try:
        if had_previous:
            snapshot_windows_active(paths)
            snapshot_created = True

        preexisting_candidate_full_names = _snapshot_windows_candidate_registrations(
            command_runner,
            custom_name,
            expected_full_name=post_expected_full_name,
            expected_family_name=post_expected_family_name,
            expected_publisher=post_expected_publisher,
            expected_version=post_expected_version,
        )

        add_command = _windows_powershell_command(
            _windows_add_script(
                candidate_msix,
                custom_name,
                allow_running=allow_running,
                allow_existing=had_previous,
                expected_full_name=expected_full_name,
                expected_family_name=expected_family_name,
                expected_publisher=expected_publisher,
                expected_version=expected_version,
            )
        )
        registration_attempted = True
        _run_windows_package_command(command_runner, add_command)
        registration_succeeded = True

        installed = _query_windows_custom_package(
            command_runner,
            custom_name,
            expected_full_name=post_expected_full_name,
            expected_family_name=post_expected_family_name,
            expected_publisher=post_expected_publisher,
            expected_version=post_expected_version,
        )
        custom_full_name = str(installed.get("PackageFullName") or "")
        # The query is identity-bound in PowerShell; retain the explicit
        # Python checks as a second boundary before mutating active state.
        _verify_windows_custom_package(
            installed,
            paths,
            expected_metadata=post_expected_metadata,
        )
        active_metadata = {
            "custom_package_name": custom_name,
            "custom_package_full_name": custom_full_name,
            "custom_package_family_name": str(
                installed.get("PackageFamilyName") or expected_family_name
            ),
            "custom_package_publisher": str(
                installed.get("Publisher") or expected_publisher
            ),
            "store_package_full_name": _windows_store_full_name(paths),
            "source_version": str(installed.get("Version") or ""),
        }
        promote_windows_active(candidate_msix, paths, metadata=active_metadata)
        if paths.previous.exists():
            _remove_windows_path(paths.previous)
        return paths.active
    except Exception as exc:
        if not registration_attempted:
            if snapshot_created:
                try:
                    _remove_windows_path(paths.previous)
                except Exception as cleanup_exc:
                    previous_location = paths.previous.resolve()
                    raise PatchError(
                        f"{exc}\nWindows deployment recovery failed: "
                        f"remove unused previous snapshot: {cleanup_exc}\n"
                        f"The previous Windows package snapshot remains at: "
                        f"{previous_location}"
                    ) from exc
            raise
        recovery_failures = _recover_windows_deployment(
            paths,
            command_runner,
            custom_name=custom_name,
            custom_full_name=custom_full_name,
            had_previous=snapshot_created,
            expected_metadata=post_expected_metadata,
            preexisting_candidate_full_names=preexisting_candidate_full_names,
            registration_attempted=registration_attempted,
            registration_succeeded=registration_succeeded,
        )
        if recovery_failures:
            previous_location = paths.previous.resolve()
            raise PatchError(
                f"{exc}\nWindows deployment recovery failed: "
                f"{'; '.join(recovery_failures)}\n"
                f"The previous Windows package snapshot remains at: "
                f"{previous_location}"
            ) from exc
        raise


def _windows_sdk_search_roots() -> tuple[Path, ...]:
    roots: list[Path] = []
    for variable in ("PROGRAMFILES(X86)", "PROGRAMFILES", "ProgramFiles(x86)", "ProgramFiles"):
        value = os.environ.get(variable)
        if value:
            roots.append(Path(value) / "Windows Kits" / "10" / "bin")
    return tuple(dict.fromkeys(roots))


def patch_windows_store_app(
    config: Path,
    overwrite_config: bool,
    allow_running: bool,
    local_app_data: Path,
    command_runner: Any | None = None,
) -> None:
    """Run all Windows preflight/build work before transactional deployment."""

    if command_runner is None:
        command_runner = run_windows_command
    package = discover_windows_store_package(command_runner)
    paths = windows_patch_paths(Path(local_app_data))
    if paths.previous.exists():
        raise PatchError(
            f"A previous Windows package snapshot requires recovery or removal: "
            f"{paths.previous}"
        )
    tools = find_windows_sdk_tools(_windows_sdk_search_roots())
    certificate = windows_signing_certificate(command_runner)
    ensure_windows_original(package, paths, command_runner=command_runner)
    paths.root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="windows-package-", dir=paths.root) as temporary:
        candidate = build_windows_patched_msix(
            package,
            paths.original,
            Path(temporary),
            tools,
            certificate,
            command_runner,
        )
        deploy_windows_msix(
            candidate,
            paths,
            command_runner,
            allow_running=allow_running,
        )
    # Config is deliberately the final operation: a failed Windows preflight
    # or deployment never creates a new JSON file.
    ensure_provider_config(Path(config), overwrite_config)


def ensure_provider_config(path: Path, overwrite: bool) -> str:
    if overwrite or not path.exists() or path.stat().st_size == 0:
        validate_provider_config(DEFAULT_PROVIDER_CONFIG)
        atomic_write_json(path, DEFAULT_PROVIDER_CONFIG)
        return "written"
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise PatchError(f"Cannot read valid JSON from {path}: {exc}") from exc
    validate_provider_config(data)
    return "kept"


def asar_header_hash(path: Path) -> str:
    try:
        with path.open("rb") as handle:
            size_pickle = handle.read(8)
            if len(size_pickle) != 8:
                raise PatchError("ASAR archive is too short to contain a header")
            size_payload, header_pickle_size = struct.unpack("<II", size_pickle)
            if size_payload != 4 or header_pickle_size < 8:
                raise PatchError("ASAR archive has an invalid header-size pickle")

            header_pickle = handle.read(header_pickle_size)
            if len(header_pickle) != header_pickle_size:
                raise PatchError("ASAR archive contains a truncated header")
    except OSError as exc:
        raise PatchError(f"Cannot read ASAR header from {path}: {exc}") from exc

    header_payload_size, header_string_size = struct.unpack("<II", header_pickle[:8])
    if header_payload_size > header_pickle_size - 4:
        raise PatchError("ASAR header payload size is invalid")
    header_start = 8
    header_end = header_start + header_string_size
    if header_end > len(header_pickle):
        raise PatchError("ASAR header string is truncated")

    header_json = header_pickle[header_start:header_end]
    try:
        json.loads(header_json.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PatchError("ASAR header does not contain valid UTF-8 JSON") from exc
    return hashlib.sha256(header_json).hexdigest()


def contains_marker(path: Path) -> bool:
    overlap = len(PATCH_MARKER) - 1
    previous = b""
    with path.open("rb") as handle:
        while chunk := handle.read(4 * 1024 * 1024):
            data = previous + chunk
            if PATCH_MARKER in data:
                return True
            previous = data[-overlap:] if overlap else b""
    return False


def load_plist(path: Path) -> tuple[dict[str, Any], plistlib.PlistFormat]:
    raw = path.read_bytes()
    plist_format = plistlib.FMT_BINARY if raw.startswith(b"bplist00") else plistlib.FMT_XML
    try:
        data = plistlib.loads(raw)
    except Exception as exc:
        raise PatchError(f"Cannot parse {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise PatchError(f"Unexpected plist root in {path}")
    return data, plist_format


def asar_integrity_hash(plist: dict[str, Any]) -> str:
    try:
        value = plist["ElectronAsarIntegrity"]["Resources/app.asar"]["hash"]
    except (KeyError, TypeError) as exc:
        raise PatchError("Info.plist has no Electron ASAR integrity entry") from exc
    if not isinstance(value, str):
        raise PatchError("Electron ASAR integrity hash is not a string")
    return value.lower()


def validated_bundle_identity(
    bundle: Path, label: str
) -> tuple[tuple[str, str], str]:
    info_path = bundle / "Contents" / "Info.plist"
    asar_path = bundle / "Contents" / "Resources" / "app.asar"
    if not bundle.is_dir() or not info_path.is_file() or not asar_path.is_file():
        raise PatchError(f"Not a supported {label}: {bundle}")

    info, _ = load_plist(info_path)
    header_hash = asar_header_hash(asar_path)
    if header_hash != asar_integrity_hash(info):
        raise PatchError(f"The {label} ASAR integrity verification failed")

    version = (
        str(info.get("CFBundleShortVersionString", "unknown")),
        str(info.get("CFBundleVersion", "unknown")),
    )
    return version, header_hash


def app_path_variants(app: Path) -> set[str]:
    variants = {str(app), str(app.resolve())}
    for value in tuple(variants):
        if value.startswith("/private/tmp/") or value.startswith("/private/var/"):
            variants.add(value[len("/private") :])
        elif value.startswith("/tmp/") or value.startswith("/var/"):
            variants.add(f"/private{value}")
    return variants


def find_target_app_processes(app: Path) -> list[tuple[int, str]]:
    prefixes = tuple(f"{variant.rstrip('/')}/" for variant in app_path_variants(app))
    try:
        result = subprocess.run(
            ["/bin/ps", "-ww", "-axo", "pid=,command="],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise PatchError(f"Could not inspect running processes: {exc}") from exc

    matches: list[tuple[int, str]] = []
    for line in result.stdout.splitlines():
        parsed = re.match(r"\s*(\d+)\s+(.+)", line)
        if parsed is None:
            continue
        pid = int(parsed.group(1))
        command = parsed.group(2)
        if pid != os.getpid() and command.startswith(prefixes):
            matches.append((pid, command))
    return matches


def signal_processes(processes: list[tuple[int, str]], signal_number: int) -> None:
    for pid, _command in processes:
        try:
            os.kill(pid, signal_number)
        except ProcessLookupError:
            continue
        except PermissionError as exc:
            raise PatchError(f"Permission denied while stopping process {pid}") from exc


def wait_for_app_processes_to_exit(app: Path, timeout: float) -> list[tuple[int, str]]:
    deadline = time.monotonic() + timeout
    remaining = find_target_app_processes(app)
    while remaining and time.monotonic() < deadline:
        time.sleep(0.2)
        remaining = find_target_app_processes(app)
    return remaining


def stop_target_app_processes(app: Path, allow_running: bool) -> None:
    executable = app / "Contents" / "MacOS" / "ChatGPT"
    if not executable.is_file():
        raise PatchError(f"Cannot identify the target ChatGPT app executable: {executable}")

    processes = find_target_app_processes(app)
    if not processes:
        terminal_status(
            "PROCESS",
            "The target ChatGPT app is not running.",
            "32",
            detail=app,
        )
        return

    pid_summary = ", ".join(str(pid) for pid, _command in processes)
    if allow_running:
        terminal_status(
            "WARNING",
            "Target-app processes are running, but automatic closing was disabled.",
            "33",
            detail=f"PIDs: {pid_summary}",
        )
        return

    terminal_status(
        "CLOSE",
        f"Closing {len(processes)} process(es) launched from the target app bundle.",
        "35",
        detail=f"PIDs: {pid_summary}",
    )
    signal_processes(processes, signal.SIGTERM)
    remaining = wait_for_app_processes_to_exit(app, 5.0)

    if remaining:
        remaining_pids = ", ".join(str(pid) for pid, _command in remaining)
        terminal_status(
            "FORCE",
            "Some target-app processes ignored the close request; force-closing them.",
            "33",
            detail=f"PIDs: {remaining_pids}",
        )
        signal_processes(remaining, signal.SIGKILL)
        remaining = wait_for_app_processes_to_exit(app, 3.0)

    if remaining:
        details = "\n".join(f"PID {pid}: {command}" for pid, command in remaining)
        raise PatchError(
            "Could not stop every process belonging to the target app bundle.\n\n"
            f"{details}"
        )

    terminal_status(
        "CLOSED",
        "All processes belonging to the target app bundle have stopped.",
        "32",
    )


def unique_candidate(
    assets: Path,
    filename_glob: str,
    content_needles: tuple[str, ...],
    role: str,
) -> Path:
    filename_matches = sorted(
        path
        for path in assets.glob(filename_glob)
        if not path.name.endswith(".map.js")
    )
    matches = []
    for path in filename_matches:
        source = path.read_text(encoding="utf-8")
        if all(needle in source for needle in content_needles):
            matches.append(path)
    if len(matches) != 1:
        raise PatchError(
            f"Expected exactly one {role} JavaScript bundle containing "
            f"'{filename_glob}' and its source markers, found {len(matches)} "
            f"out of {len(filename_matches)} filename matches"
        )
    return matches[0]


def current_patch_bundle(assets: Path) -> Path:
    return unique_candidate(
        assets,
        "app-initial-*.js",
        BUILD_5828_BUNDLE_MARKERS,
        "ChatGPT 26.721.31836 build 5828 application",
    )


def parse_hunks(unified_diff: str) -> list[list[str]]:
    lines = unified_diff.splitlines()
    hunks: list[list[str]] = []
    current: list[str] | None = None
    for line in lines:
        if line.startswith("@@ "):
            current = []
            hunks.append(current)
        elif current is not None:
            if not line or line[0] not in " +-":
                raise PatchError(f"Malformed embedded diff line: {line!r}")
            current.append(line)
    if not hunks:
        raise PatchError("Embedded patch contains no hunks")
    return hunks


def apply_unified_diff(path: Path, unified_diff: str) -> None:
    source = path.read_text(encoding="utf-8")
    had_trailing_newline = source.endswith("\n")
    source_lines = source.splitlines()
    search_start = 0

    for hunk_number, hunk in enumerate(parse_hunks(unified_diff), start=1):
        old_lines = [line[1:] for line in hunk if line[0] in " -"]
        new_lines = [line[1:] for line in hunk if line[0] in " +"]
        matches = [
            index
            for index in range(search_start, len(source_lines) - len(old_lines) + 1)
            if source_lines[index : index + len(old_lines)] == old_lines
        ]
        if len(matches) != 1:
            raise PatchError(
                f"{path.name}: hunk {hunk_number} matched {len(matches)} times; "
                "the app build is unsupported or already modified"
            )
        index = matches[0]
        source_lines[index : index + len(old_lines)] = new_lines
        search_start = index + len(new_lines)

    result = "\n".join(source_lines) + ("\n" if had_trailing_newline else "")
    path.write_text(result, encoding="utf-8")


def patch_current_bundle(bundle: Path) -> None:
    run(
        ["npx", "--yes", PRETTIER_PACKAGE, "--write", str(bundle)],
        label="Preparing the JavaScript bundle",
    )
    apply_unified_diff(bundle, CENTRAL_DIFF)
    apply_unified_diff(bundle, PICKER_DIFF)

    source = bundle.read_text(encoding="utf-8")
    if PATCH_MARKER.decode() not in source:
        raise PatchError("Routing marker missing after patch")
    if "CodexCustomProviderPickerSection" not in source:
        raise PatchError("Provider picker missing after patch")

    run(
        ["npx", "--yes", PRETTIER_PACKAGE, "--write", str(bundle)],
        label="Formatting the patched JavaScript",
    )
    run(
        ["node", "--check", str(bundle)],
        label="Validating the patched JavaScript",
    )


def validate_original_source(app: Path, original: Path) -> Path:
    app_version, _ = validated_bundle_identity(app, "target app")
    original_version, _ = validated_bundle_identity(
        original, "clean original backup"
    )
    original_asar = original / "Contents" / "Resources" / "app.asar"
    if contains_marker(original_asar):
        raise PatchError("The clean original backup is already patched")
    if app_version != original_version:
        raise PatchError(
            "The clean original backup does not match the target app version and build"
        )
    return original


def make_original_backup(source: Path, original: Path) -> Path:
    if source.resolve() == original.resolve():
        validate_original_source(source, original)
        return original

    validate_original_source(source, source)
    original.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{original.stem}.", dir=original.parent)
    )
    candidate = staging / original.name
    displaced = staging / "displaced.backup"
    try:
        run(
            ["/usr/bin/ditto", str(source), str(candidate)],
            label="Creating the clean sibling original",
        )
        validate_original_source(source, candidate)
        if original.exists():
            os.replace(original, displaced)
        try:
            os.replace(candidate, original)
        except Exception:
            if displaced.exists():
                os.replace(displaced, original)
            raise
        return original
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def ensure_original_backup(
    app: Path,
    original: Path,
    *,
    reapply_from: Path | None,
    legacy_backups: tuple[Path, ...],
) -> Path:
    app_asar = app / "Contents" / "Resources" / "app.asar"
    app_is_patched = contains_marker(app_asar)
    original_resolved = original.resolve()
    reapply_source_resolved = (
        reapply_from.expanduser().resolve() if reapply_from is not None else None
    )
    distinct_legacy = tuple(
        dict.fromkeys(
            path.expanduser().resolve()
            for path in legacy_backups
            if path.expanduser().resolve()
            not in {original_resolved, reapply_source_resolved}
        )
    )

    if reapply_from is not None:
        source = reapply_from.expanduser().resolve()
        validate_original_source(app, source)
        make_original_backup(source, original)
    elif original.exists():
        try:
            validate_original_source(app, original)
        except PatchError:
            if app_is_patched:
                raise
            make_original_backup(app, original)
    elif app_is_patched:
        source = None
        last_error = None
        for candidate in distinct_legacy:
            if not candidate.exists():
                continue
            try:
                validate_original_source(app, candidate)
            except PatchError as exc:
                last_error = exc
                continue
            source = candidate
            break
        if source is None and last_error is not None:
            raise PatchError(
                "No legacy original backup matches the patched target app"
            ) from last_error
        if source is None:
            raise PatchError(
                f"Missing clean original backup beside the patched app: {original}"
            )
        make_original_backup(source, original)
    else:
        make_original_backup(app, original)

    validate_original_source(app, original)
    migrated = []
    for legacy in distinct_legacy:
        if not legacy.exists():
            continue
        try:
            shutil.rmtree(legacy)
        except OSError as exc:
            raise PatchError(
                "The sibling original is verified, but the legacy original backup "
                f"could not be removed: {legacy}"
            ) from exc
        migrated.append(legacy)

    for legacy in migrated:
        terminal_status(
            "MIGRATED",
            "Legacy original backup moved beside the target app.",
            "32",
            detail=f"{legacy} -> {original}",
        )
    return original


def atomic_replace_file(source: Path, target: Path) -> None:
    original_stat = target.stat()
    fd, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.patch-", dir=target.parent)
    os.close(fd)
    temporary_path = Path(temporary_name)
    try:
        shutil.copyfile(source, temporary_path)
        os.chmod(temporary_path, original_stat.st_mode)
        if os.geteuid() == 0:
            os.chown(temporary_path, original_stat.st_uid, original_stat.st_gid)
        os.replace(temporary_path, target)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def make_previous_snapshot(app: Path, previous: Path) -> Path:
    if previous.exists():
        raise PatchError(
            f"A previous app snapshot already exists; recover or remove it first: {previous}"
        )

    source_identity = validated_bundle_identity(app, "target app")
    staging = Path(
        tempfile.mkdtemp(prefix=f".{previous.stem}.", dir=previous.parent)
    )
    candidate = staging / previous.name
    try:
        run(
            ["/usr/bin/ditto", str(app), str(candidate)],
            label="Creating the previous app snapshot",
        )
        if (
            validated_bundle_identity(candidate, "previous app snapshot")
            != source_identity
        ):
            raise PatchError("The previous app snapshot does not match the target app")
        os.replace(candidate, previous)
        return previous
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def restore_previous_snapshot(app: Path, previous: Path) -> Path:
    previous_identity = validated_bundle_identity(previous, "previous app snapshot")
    staging = Path(
        tempfile.mkdtemp(prefix=f".{app.stem}.rollback-", dir=app.parent)
    )
    restored = staging / app.name
    displaced = staging / "mutated.app"
    rejected = staging / "rejected.app"
    try:
        run(
            ["/usr/bin/ditto", str(previous), str(restored)],
            label="Restoring the previous app snapshot",
        )
        if (
            validated_bundle_identity(restored, "rollback candidate")
            != previous_identity
        ):
            raise PatchError(
                "The rollback candidate does not match the previous snapshot"
            )

        os.replace(app, displaced)
        try:
            os.replace(restored, app)
            if validated_bundle_identity(app, "restored app") != previous_identity:
                raise PatchError(
                    "The restored app does not match the previous snapshot"
                )
        except Exception:
            if app.exists():
                os.replace(app, rejected)
            os.replace(displaced, app)
            raise
        return app
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def remove_previous_snapshot(previous: Path) -> None:
    if not previous.exists():
        return
    try:
        shutil.rmtree(previous)
    except OSError as exc:
        raise PatchError(
            f"Could not remove the previous app snapshot: {previous}"
        ) from exc


def build_patched_artifacts(
    original: Path, work: Path
) -> tuple[Path, Path]:
    info_path = original / "Contents" / "Info.plist"
    asar_path = original / "Contents" / "Resources" / "app.asar"
    info, plist_format = load_plist(info_path)
    extracted = work / "app"
    patched_asar = work / "app.asar"
    patched_plist = work / "Info.plist"

    run(
        ["npx", "--yes", ASAR_PACKAGE, "extract", str(asar_path), str(extracted)],
        label="Extracting application resources",
    )
    assets = extracted / "webview" / "assets"
    if not assets.is_dir():
        raise PatchError("Extracted app has no webview/assets directory")

    bundle = current_patch_bundle(assets)
    patch_current_bundle(bundle)
    run(
        ["npx", "--yes", ASAR_PACKAGE, "pack", str(extracted), str(patched_asar)],
        label="Packing patched application resources",
    )

    if not contains_marker(patched_asar):
        raise PatchError("Packed ASAR does not contain the patch marker")
    patched_header_hash = asar_header_hash(patched_asar)
    info["ElectronAsarIntegrity"]["Resources/app.asar"]["hash"] = patched_header_hash
    with patched_plist.open("wb") as handle:
        plistlib.dump(info, handle, fmt=plist_format, sort_keys=False)

    return patched_asar, patched_plist


def install_patched_artifacts(
    app: Path,
    previous: Path,
    patched_asar: Path,
    patched_plist: Path,
) -> None:
    info_path = app / "Contents" / "Info.plist"
    asar_path = app / "Contents" / "Resources" / "app.asar"
    make_previous_snapshot(app, previous)
    try:
        atomic_replace_file(patched_asar, asar_path)
        atomic_replace_file(patched_plist, info_path)
        run(
            ["/usr/bin/codesign", "--deep", "--force", "--sign", "-", str(app)],
            label="Applying the ad-hoc app signature",
        )
        run(
            [
                "/usr/bin/codesign",
                "--verify",
                "--deep",
                "--strict",
                "--verbose=2",
                str(app),
            ],
            label="Verifying the app signature",
        )
        final_info, _ = load_plist(info_path)
        if asar_header_hash(asar_path) != asar_integrity_hash(final_info):
            raise PatchError("Installed ASAR integrity verification failed")
        if not contains_marker(asar_path):
            raise PatchError("Installed ASAR is missing the patch marker")
    except Exception:
        terminal_status(
            "RECOVERY",
            "Installation failed after app files changed. Restoring the previous app.",
            "33",
            stream=sys.stderr,
        )
        try:
            restore_previous_snapshot(app, previous)
        except Exception as restore_exc:
            terminal_panel(
                "Recovery failed",
                f"Automatic rollback failed: {restore_exc}\n"
                f"The previous app snapshot remains at: {previous}",
                "31",
                stream=sys.stderr,
            )
        else:
            try:
                remove_previous_snapshot(previous)
            except PatchError as cleanup_exc:
                terminal_status(
                    "CLEANUP",
                    "The previous app was restored, but its snapshot remains.",
                    "33",
                    detail=f"{previous}: {cleanup_exc}",
                    stream=sys.stderr,
                )
            terminal_status(
                "RESTORED",
                "The previous app state was restored.",
                "32",
                detail=app,
                stream=sys.stderr,
            )
        raise

    remove_previous_snapshot(previous)


def patch_app(
    app: Path,
    config: Path,
    original: Path,
    previous: Path,
    overwrite_config: bool,
) -> None:
    info_path = app / "Contents" / "Info.plist"
    resources = app / "Contents" / "Resources"
    asar_path = resources / "app.asar"
    unpacked_path = resources / "app.asar.unpacked"

    if sys.platform != "darwin":
        raise PatchError("This installer only supports macOS")
    if not app.is_dir() or not info_path.is_file() or not asar_path.is_file():
        raise PatchError(f"Not a supported ChatGPT app bundle: {app}")
    if not unpacked_path.is_dir():
        raise PatchError(f"Missing ASAR companion directory: {unpacked_path}")
    if shutil.which("npx") is None:
        raise PatchError("npx is required. Install Node.js, then run this installer again")

    config_action = ensure_provider_config(config, overwrite_config)
    terminal_status(
        "CONFIG",
        "Provider-routing config created."
        if config_action == "written"
        else "Existing provider-routing config validated.",
        "36",
        detail=config,
    )
    validate_original_source(app, original)
    version, _ = validated_bundle_identity(original, "clean original backup")

    terminal_heading("Installation", "35")
    terminal_status(
        "APP",
        f"Preparing ChatGPT {version[0]}, build {version[1]}.",
        "34",
        detail=app,
    )
    with tempfile.TemporaryDirectory(prefix="chatgpt-provider-patch-") as temporary:
        patched_asar, patched_plist = build_patched_artifacts(
            original, Path(temporary)
        )
        install_patched_artifacts(app, previous, patched_asar, patched_plist)

    print_completion_summary(config, backup=original)


def main() -> int:
    args = parse_args()
    try:
        app = args.app.expanduser().resolve()
        config = args.config.expanduser().resolve()
        original, previous = managed_backup_paths(app)
        legacy_backups = tuple(
            dict.fromkeys(
                (
                    effective_codex_home().resolve() / "ChatGPT-original.app",
                    config.parent / "ChatGPT-original.app",
                )
            )
        )
        if previous.exists():
            raise PatchError(
                f"A previous app snapshot requires recovery or removal: {previous}"
            )

        stop_target_app_processes(app, args.allow_running)
        original = ensure_original_backup(
            app,
            original,
            reapply_from=args.reapply_from,
            legacy_backups=legacy_backups,
        )
        patch_app(
            app,
            config,
            original,
            previous,
            args.overwrite_config,
        )
    except PatchError as exc:
        fail(str(exc))
    except PermissionError as exc:
        fail(f"Permission denied: {exc}")
    except KeyboardInterrupt:
        fail("Interrupted", 130)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
