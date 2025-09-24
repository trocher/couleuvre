# Couleuvre

A lightweight Language Server for Vyper. It parses Vyper modules, extracts symbols, and supports basic navigation such as go-to-definition (including across imports), works with any Vyper versions, and doesn't require Vyper to be installed.

## Features


| Feature                       | Status       |
| ----------------------------- | ------------ |
| Syntax Highlighting           | ❌ Planned   |
| Go to Definition              | ⚠️ Alpha     |
| Go to Modules                 | ⚠️ Alpha     |
| Document Symbols              | ✅ Supported |
| Workspace Symbols             | ❌ Planned   |
| References                    | ❌ Planned   |
| Hover Information             | ❌ Planned   |
| Diagnostics (Errors/Warnings) | ❌ Planned   |
| Code Completion               | ❌ Planned   |
| Document Formatting           | ❌ Planned   |

- Automatic environment handling:
  - If the current environment already has the requested `vyper` version, use it directly
  - Otherwise, spin up and cache a dedicated `uv`-managed venv with the required `vyper` version


## Requirements

- Python >= 3.10
- `uv` (https://github.com/astral-sh/uv)

## Installation

```bash
uv sync
```

## Usage

- As an LSP server (from source):

```bash
uv run -m couleuvre
```

- Through the [VScode extension](https://github.com/trocher/vscode-vyper-lsp)

## How Vyper version is selected

- Contracts can specify the compiler version via a pragma or annotation in the source.
- If no version is found, a default can be provided by the server or it will error.
- Environment usage:
  - If the running environment's `vyper` matches the contract's version, it is used directly. This allows for resolving imports by using the current environment's search paths (e.g. snekmate)
  - Otherwise, Couleuvre creates/uses a cached virtualenv (via `uv`) for that version and runs Vyper with that interpreter. In this case, external imports are not resolved.



Your editor should connect to the server via stdio (pygls). Point your client configuration to the above command.

## Testing

```bash
uv run pytest
```

## Alternatives

- The official Vyper Language Server (https://github.com/vyperlang/vyper-lsp) is more feature-complete but only supports Vyper >= 0.4.1 and requires Vyper to be installed in the environment.

## Disclaimer

Couleuvre is in early development, use at your own risk. Couleuvre is not affiliated with the Vyper project.
