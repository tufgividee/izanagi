# Izanagi Snapshot Format and Structure

## 1. Purpose

Izanagi creates a deterministic, local-first project context snapshot for use with AI assistants.

A snapshot captures the project's relevant files, structure, configuration, and metadata at a particular point in time. It is intended to provide reusable, inspectable project context without requiring the assistant to rediscover the repository in every conversation.

Izanagi does not execute project code or generate AI summaries. Eligible file contents are preserved verbatim.

A snapshot describes the project as captured; it does not guarantee that the project remains unchanged afterward.

## 2. Snapshot Outputs

A snapshot consists of:

- A Markdown context document containing project metadata, inventory, directory structure, and eligible file contents.
- A JSON manifest containing structured inventory and snapshot metadata.

The snapshot output directory is managed by Izanagi and must not be treated as ordinary project input during the same scan.

## 3. Snapshot Metadata

The snapshot header records the metadata available to the implementation, including:

- Project name
- Snapshot ID
- Creation timestamp, including timezone information
- Resolved project root
- Git root, when available
- Snapshot format version
- Izanagi package version, when available

The JSON manifest records the snapshot format version and structured project inventory.

Metadata fields that cannot be determined should be represented as unavailable rather than fabricated.

## 4. Inventory and Inclusion

Izanagi discovers project files without executing project code and records whether each discovered entry is