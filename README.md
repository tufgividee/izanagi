# Izanagi

**Project context snapshots for AI-assisted software development.**

Izanagi performs one command captures of a software project's relevant files, directory structure, configuration, and recorded state in a portable Markdown document. The document can be shared with an AI assistant to establish project context without repeatedly explaining the codebase or manually selecting files.

The snapshot can be directly copied into the clipboard, and then user can use segclip to split the content into a sequence of text segments for AI-assitance with specified text input length.

The goal is to make AI-assisted development more continuous, reproducible, and efficient—even across separate conversations.

## Why Izanagi?

AI-assisted development often requires repeatedly providing the same context:

- What the project does and how it is organized
- Which source files and configuration matter
- What design decisions and working conventions should be respected
- What changed since the previous collaboration session

Izanagi packages this information into a snapshot that can be handed to an AI assistant.

A snapshot represents the project at a particular point in time. It is a portable record of context, not a live connection to the repository.

## Features

- **Project initialization:** Create project-local Izanagi configuration.
- **File inventory:** Inspect discovered files and understand why they are included or excluded.
- **Base snapshots:** Capture a full project-context baseline.
- **Incremental snapshots:** Record updates relative to a base snapshot.
- **Current context:** Maintain a consolidated context document for sharing.
- **Clipboard integration:** Copy the generated context for direct use in an AI conversation.
- **Configurable inclusion rules:** Control which files become part of the snapshot.
- **AI-oriented documentation:** Include project instructions and design documentation alongside source code.

## Getting started

Install Izanagi as an editable tool from the repository root:

```bash
uv tool install -e .
```

You can now run `izanagi` directly from any directory.

Initialize a project and create its base snapshot:

```bash
izanagi init --project /path/to/project
izanagi manifest --project /path/to/project
izanagi base --project /path/to/project
izanagi copy --project /path/to/project
```
When working inside a project directory simply run

```bash
izanagi init
izanagi base
izanagi delta
izanagi base --copy <- saves project snapshot directly to clipboard
```

or also with uv

Use `izanagi --help` or `izanagi <command> --help` to see available commands and options.

Izanagi uses Python and `uv` for development.

From the Izanagi repository, run the CLI through `uv`:

```bash
uv run izanagi --help
```

Initialize a project:

```bash
uv run izanagi init --project /path/to/project
```

Inspect the project's file inventory:

```bash
uv run izanagi manifest --project /path/to/project
```

Create a base snapshot:

```bash
uv run izanagi base --project /path/to/project
```

Copy the current context to the clipboard:

```bash
uv run izanagi copy --project /path/to/project
```

For the exact options supported by a command, use its help output. For example:

```bash
uv run izanagi base --help
```

## Configuration

Izanagi uses a project-local `.izanagi/config.toml` file to control project settings, file discovery, inclusion and exclusion rules, and snapshot preambles.

Initialize a project to create its configuration:

```bash
izanagi init
```

The main settings are:

| Setting | Purpose |
|---|---|
| `[project]` | Project name, root directory, and output directory |
| `[scan]` | File discovery options, including hidden files |
| `[scan.inclusions]` | Rules for files and directories to include |
| `[scan.exclusions]` | Rules for files and directories to exclude |
| `[preamble]` | Introductory text for base and incremental snapshots |

### Project settings

```toml
[project]
name = ""
root = "."
output_dir = ".izanagi"

[scan]
include_hidden_files = true
```

The project root defaults to the current directory, and generated context is stored in `.izanagi/` by default.

### Choosing which files to include

Use `scan.inclusions.rules` to specify which project files should be captured. For example:

```toml
[scan.inclusions]
rules = [
    "*.py",
    "*.rs",
    "*.md",
    "*.toml",
    "pyproject.toml",
    "README.md",
]
```

This example selects common source files, Markdown documentation, and TOML configuration files. Adapt the rules to your project's languages and structure.

### Excluding files

Use `scan.exclusions.rules` to omit files and directories that should not be included in the snapshot.

```toml
[scan.exclusions]
rules = [
    ".git/",
    ".venv/",
    "__pycache__/",
    "*.pyc",
    "*.log",
    ".pytest_cache/",
]
```

Exclusions are useful for keeping generated files, caches, virtual environments, and irrelevant content out of the context.

A file may match both inclusion and exclusion rules. Review the generated inventory to verify how Izanagi resolves those matches:

```bash
izanagi manifest
```

The inventory reports which entries are included or excluded and the associated reason.

### Customizing snapshot preambles

The `[preamble]` section controls the introductory text placed in generated snapshots.

- `base_preamble` introduces the full project snapshot.
- `incremental_preamble` introduces an incremental snapshot. The `{base_snapshot_id}` placeholder identifies the referenced base snapshot.

Customize these messages to provide project-specific context or instructions for AI assistants. Keep reusable project guidance in documentation and use the preambles for concise introductory information.

### Configuration tips

- Start with the generated configuration and adjust it incrementally.
- Include documentation that explains architecture, conventions, and important design decisions.
- Exclude secrets, credentials, private data, and unnecessary generated files.
- Run `izanagi manifest` after changing rules to inspect the results.
- Create a new base snapshot after confirming that the inventory captures the context you want to share.

Configuration behavior and available options may evolve as Izanagi develops.

## Typical collaboration workflow

### 1. Initialize the project

Run `izanagi init` to establish project-local configuration.

### 2. Review the inventory

Run `izanagi manifest` to inspect file discovery and inclusion decisions. Adjust the configuration if important files are missing or irrelevant files are included.

### 3. Create the base snapshot

Run `izanagi base` to capture the project's initial context.

By default, generated context is stored in the configured output directory, which defaults to `.izanagi/`.

The main artifact is:

```text
.izanagi/
├── config.toml
├── current.md
├── manifest.json
├── bases/
└── deltas/
```

The exact contents of the output directory depend on the operations performed.

### 4. Start an AI collaboration session

Copy the current context:

```bash
izanagi copy
```

Provide the resulting context to an AI assistant. Ask it to reconstruct the architecture, identify relevant files, and distinguish documented facts from assumptions before proposing changes.

### 5. Continue with incremental updates

After making changes to the project, use `izanagi delta` to capture updates relative to the base snapshot.

Provide the relevant base context and incremental update to the AI assistant so it can continue from the recorded project state.

Consult `izanagi delta --help` for the supported options.

## Configuration

Izanagi uses a project-local `config.toml` to control project settings, file discovery, inclusion and exclusion rules, and snapshot preambles.

The default output directory is `.izanagi`.

Inclusion rules allow relevant source code, documentation, and configuration to be captured. Exclusion rules keep generated files, virtual environments, caches, and other unwanted content out of the context.

Review the generated configuration and inventory before relying on a snapshot for important work.

## Snapshot contents

A generated context document can include:

- Snapshot metadata and identifiers
- An inventory summary and inclusion decisions
- Project documentation
- Directory structure
- Relevant source and configuration file contents

The base snapshot establishes the reference context. Incremental snapshots describe updates relative to that base and should be interpreted together with it.

Snapshots are point-in-time records. They do not prove that the working tree still matches the captured state.

See [`snapshot_structure.md`](snapshot_structure.md) for details about the snapshot format and organization.

## Development and testing

Run the test suite with:

```bash
uv run pytest -q
```

The tests cover configuration, manifest generation, snapshot generation, and incremental snapshots.

## Design principles

Izanagi is designed around a few principles:

- **Context before code:** Understand the existing project before proposing changes.
- **Explicit evidence:** Distinguish captured facts from assumptions and missing information.
- **Incremental collaboration:** Reuse established context and communicate updates rather than repeatedly starting from scratch.
- **Configurable scope:** Let developers choose which project information belongs in the handoff.
- **Portable artifacts:** Use readable files that can be inspected, versioned, and shared.
- **Honest state representation:** Treat snapshots as records of a particular point in time, not as live repository state.

## Project status

Izanagi is under active development. Its commands, configuration format, and snapshot behavior may evolve.

The intended outcome is a reliable context-transfer workflow that helps developers and AI assistants collaborate across sessions with less repetition and better continuity.
