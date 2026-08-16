---
description: Use this skill when the user wants the project documentation (docs/ folder and README.md) to be audited and harmonized — for example "docs konsistent machen", "Doku abstimmen", "Redundanzen entfernen", "einheitlichen Stil herstellen", "sync-docs". Invoke whenever documentation consistency across the whole project is the goal.
---

# /sync-docs — Audit and Harmonize IB-Tool 3 Documentation

Audit and harmonize all project documentation: **docs/**, **README.md**.

Follow these steps in order. Do not skip any step.

---

## Step 1 — Read all documentation files

Read **every** file in this list completely before making any changes:

```
README.md
docs/plugin-architecture.md
docs/how-it-works.md
docs/error-handling.md
docs/test-strategy.md
docs/contributing.md
docs/parameterization.md
docs/input-data.md
docs/CONFIG_README.md
docs/CHANGELOG.md
```

Also read `CLAUDE.md` to understand which files are listed in the documentation tables there.

---

## Step 2 — Audit: identify all issues

Before touching any file, produce a written audit in your response covering all four issue categories below. Be specific: quote the file name and heading where the issue occurs.

### 2.1 Redundancies

Flag every piece of content that appears in more than one file. Common hotspots:

- Input layer table (appears in both `how-it-works.md` and `input-data.md`)
- Parameter table (appears in both `how-it-works.md` and `parameterization.md`)
- CI/CD pipeline description (appears in both `contributing.md` and `plugin-architecture.md` and `test-strategy.md`)
- Test structure / test file list (may appear in both `contributing.md` and `test-strategy.md`)
- Logging system description (may appear in both `error-handling.md` and `README.md`)

For each redundancy: decide which file is the **canonical home** (where the full content belongs) and which file should only carry a one-line cross-reference.

**Canon assignment rules:**

| Topic | Canonical file |
|---|---|
| Input layer specs, field requirements, filter file format, validation checks | `docs/input-data.md` |
| Processing parameters, defaults, sensitivity | `docs/parameterization.md` |
| CI/CD workflows, Docker environment | `docs/contributing.md` |
| Test taxonomy, coverage targets, module mapping, gap backlog | `docs/test-strategy.md` |
| Logging system, log levels, error categories, debug mode | `docs/error-handling.md` |
| Code structure, entry points, import strategy, package layout | `docs/plugin-architecture.md` |
| Full algorithmic pipeline (pseudocode, step-by-step) | `docs/how-it-works.md` |
| Brief feature overview, installation, usage quick-start | `README.md` |

### 2.2 Style inconsistencies

Check each file against the **unified style standard** (see Step 4). Flag every deviation:

- Numbered section headings (`## 1. Introduction`) — must be changed to unnumbered (`## Introduction`)
- Missing or inconsistent `---` horizontal rules between H2 sections
- Missing introductory paragraph (file starts directly with a table or heading)
- Missing `## Related Files` section at the end
- German text outside UI-label context (UI labels in backticks are allowed; prose must be English)
- Inconsistent log-level descriptions (verify `README.md` matches `error-handling.md` exactly)

### 2.3 Structural gaps

Check that:
- Every file listed in `CLAUDE.md` documentation tables actually exists
- Every cross-reference link in a docs file points to a file that exists
- `CLAUDE.md` table entries match actual filenames (case-sensitive)
- Files removed or renamed as part of this task are updated in `CLAUDE.md`

### 2.4 Documents to split or merge

Assess whether any document is too broad (mixes unrelated topics) or too thin (would be better merged into another):

- `plugin-architecture.md`: check whether it duplicates content that belongs in `input-data.md` or `contributing.md` — extract those sections if present
- `CONFIG_README.md`: assess whether it should remain standalone or be merged into `docs/plugin-architecture.md`; keep standalone if it is referenced from `CLAUDE.md` and has substantial content
- `test-strategy.md` §10 "CI/CD Summary": if it duplicates `contributing.md`, reduce to a cross-reference

---

## Step 3 — Produce change plan

After the audit, list every planned change as a numbered action:

```
1. [FILE] Remove section "X" (redundant with docs/Y.md) → replace with one-line cross-reference
2. [FILE] Convert numbered headings (## 1. Foo, ## 2. Bar) → unnumbered (## Foo, ## Bar)
3. [FILE] Add missing introductory paragraph
4. [FILE] Add missing ## Related Files table
5. [FILE] Add --- separator between H2 sections
6. ...
```

Do not start editing until the change plan is written out in full.

---

## Step 4 — Apply changes: enforce unified style standard

Apply every planned change. Follow the style standard below for every file you touch.

### Unified style standard

#### Document structure (required for all files except README.md and CHANGELOG.md)

```markdown
# Document Title

One introductory paragraph: what this document covers, who should read it,
when to consult it. Must not be omitted.

---

## Section Heading

Content.

---

## Another Section Heading

Content.

---

## Related Files

| File | Content |
|------|---------|
| [`path/to/file.md`](path/to/file.md) | What it covers |
```

#### Heading levels

- `#` — document title (exactly one per file)
- `##` — major sections
- `###` — subsections
- `####` — sub-subsections (use sparingly)
- **Never** number headings: `## 1. Introduction` → `## Introduction`

#### Separators

- Use `---` on its own line to separate every pair of H2 sections
- One blank line before and after `---`

#### Tables

- Use pipe tables for all structured reference data
- Include a header row with `|---|` separators
- Keep column widths reasonable — no excessive padding

#### Code blocks

- Always specify a language: ` ```python `, ` ```bash `, ` ```ini `, ` ```yaml `
- For generic file tree or pseudocode use ` ```text ` or ` ``` `

#### Language rules

- Prose: English throughout
- German allowed only for: direct QGIS UI labels in backticks (e.g. `Plugins → IB-Tool`), direct BauGB citations, direct German author/title quotes
- Log level names in ALL CAPS when used as identifiers: `CRITICAL`, `WARNING`, `INFO`, `SUCCESS`

#### Cross-references instead of duplication

When a topic is covered in detail in another file, use a one-line cross-reference:

```markdown
For full layer specifications and the validation check table,
see [docs/input-data.md](docs/input-data.md).
```

Never reproduce a table that belongs to another document — cross-reference it instead.

#### Related Files section

Every docs file (except `README.md` and `CHANGELOG.md`) must end with a `## Related Files` table. Include only files genuinely related to the topic. Use relative paths with markdown links.

---

## Step 5 — Handle README.md separately

`README.md` is the public entry point (rendered on GitHub). Apply these specific rules:

- Keep badges, description, features list, requirements, installation, and usage — these are entry-point content
- Keep a brief "How It Works" summary (the numbered step list is appropriate here) but it must link to `docs/how-it-works.md` for details
- Keep a brief "Input Data" paragraph but link to `docs/input-data.md` for the full table
- **Remove or drastically shorten** any section that reproduces detail already in a `docs/` file — replace with a one-sentence summary and a link
- Specifically: "Logging System" section in `README.md` should be reduced to 2–3 sentences + link to `docs/error-handling.md`
- Do NOT add a `## Related Files` table to README.md (it is not a reference doc)

---

## Step 6 — Update CLAUDE.md if needed

If files were renamed, split, or merged:

1. Update the documentation table in `CLAUDE.md` under `### docs/ — Project Documentation`
2. Ensure every docs file that exists after this task is listed with a correct description
3. Remove entries for files that no longer exist

---

## Step 7 — Update CHANGELOG.md

Add under `[Unreleased]`:

```
- Docs: Harmonized docs/ folder and README.md — removed redundancies, unified style, added cross-references
```

---

## Step 8 — Output

Report:

1. **Redundancies removed** — list each file + section where duplicate content was replaced by a cross-reference
2. **Style changes** — list files where headings were un-numbered, separators added, intro paragraph added, Related Files added
3. **Splits or merges** — describe any structural changes (e.g. section extracted from `plugin-architecture.md`)
4. **CLAUDE.md updated?** — yes/no, and what changed
5. **Open questions** — any content where the canonical home was ambiguous or content was unclear
