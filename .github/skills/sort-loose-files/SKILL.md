---
name: sort-loose-files
description: "Use when: sorting loose files into folders, organizing a workspace, cleaning up cluttered directories, or maintaining project structure without breaking functionality"
---

# Sort loose files into correct folders

## Trigger

Loose files or folders are scattered across a workspace and need to be grouped into a clearer structure without disrupting how the project works.

## Workflow

1. Inventory the loose files and note their type, purpose, and any obvious dependencies.
2. Identify the most appropriate destination folder based on function, lifecycle, and project conventions.
3. Preserve functionality by keeping code, scripts, assets, docs, configs, and runtime data in sensible locations.
4. Create or update folder structure only where it improves clarity; avoid unnecessary nesting.
5. Move files with minimal disruption, then verify that references, imports, and linked paths still make sense.
6. Update any indexes, docs, or references that point to the old location.
7. Review the result for discoverability, maintainability, and long-term organization.

## Decision points

- If a file is executable or project code, place it in a source, script, or tool-related folder.
- If a file is documentation or explanatory content, place it in docs or a related content folder.
- If a file is generated, temporary, or runtime data, place it in logs, temp, cache, or data folders.
- If a file appears to be archival, personal, or unrelated to the active project, place it in an archive or separate storage folder.
- If the destination is uncertain, ask the user whether the file is workspace-specific, personal, or historical.

## Guardrails

- Do not break references, imports, or paths when moving files.
- Keep the structure simple and predictable rather than over-organized.
- Favor existing project conventions over inventing a new layout.
- Avoid mixing unrelated content in the same folder.

## Completion checks

- Every loose file has a clear home.
- The workspace is easier to navigate than before.
- Critical files are not left in the root or an unclear location.
- Related files are grouped logically.
- The folder layout still supports the project’s functionality.

## Output

- A cleaned and organized folder structure
- A list of moved files and their new locations
- Any follow-up notes for references, naming, or future maintenance
