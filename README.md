# Couleuvre

A lightweight Language Server for Vyper. It parses Vyper modules, extracts symbols, and supports basic navigation such as go-to-definition (including across imports), works with any Vyper version, and doesn't require Vyper to be installed.

## Features

| Feature                       | Status       |
| ----------------------------- | ------------ |
| Syntax Highlighting           | ❌ Planned   |
| Go to Definition              | ✅ Supported |
| Go to Modules                 | ✅ Supported |
| Document Symbols              | ✅ Supported |
| Workspace Symbols             | ❌ Planned   |
| References                    | ⚠️ Alpha     |
| Hover Information             | ❌ Planned   |
| Diagnostics (Errors/Warnings) | ✅ Supported |
| Code Completion               | ⚠️ Alpha     |
| Document Formatting           | ❌ Planned   |

- Automatic environment handling:
  - If the current environment already has the requested `vyper` version, use it directly
  - Otherwise, spin up and cache a dedicated `uv`-managed venv with the required `vyper` version

## Architecture

```
couleuvre/
├── server.py              # LSP server (pygls) - handles client requests
├── parser.py              # Module parsing entry point
├── ast/
│   ├── parser.py          # Vyper AST → internal AST conversion
│   ├── nodes.py           # AST node dataclasses
│   ├── visitor.py         # AST visitor for symbol extraction
│   ├── environment.py     # Vyper environment abstraction
│   └── vyper_wrapper.py   # uv-managed Vyper version handling
└── features/
    ├── symbol_table.py    # Unified symbol table with metadata
    ├── symbols.py         # Document symbols (outline view)
    ├── definition.py      # Go-to-definition logic
    ├── references.py      # Find-all-references logic
    ├── resolve.py         # Symbol resolution utilities
    ├── diagnostics.py     # Semantic analysis diagnostics
    └── completion.py      # Code completion (self., module.)
```


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

- Through the [VSCode extension](https://github.com/trocher/vscode-vyper-lsp)

## How Vyper version is selected

- Contracts can specify the compiler version via a pragma in the source (e.g., `#pragma version ^0.4.0`).
- If no version is found, a default can be provided by the server based on the workspace/other files, or a diagnostic error will be shown.

## Environment handling

  - **System Environment**: If the running environment's `vyper` matches the contract's version, it is used directly. This allows for resolving imports by using the current environment's search paths (e.g., snekmate).
  - **Couleuvre Environment**: Otherwise, Couleuvre creates/uses a cached virtualenv (via `uv`) at `~/.couleuvre/venvs/<version>/` for that version and runs Vyper with that interpreter. In this case, external imports that depend on system paths are not resolved.


Your editor should connect to the server via stdio (pygls). Point your client configuration to the above command.

## Testing

```bash
uv run pytest
```

## Alternatives

- The official Vyper Language Server (https://github.com/vyperlang/vyper-lsp) is more feature-complete but only supports Vyper >= 0.4.1 and requires Vyper to be installed in the environment.

## Disclaimer

Couleuvre is in early development, use at your own risk. Couleuvre is not affiliated with the Vyper project.
