# Brutal security review: battle.py QEMU digital twin

## Repository and branch

- **Repo:** `owner/repo`
- **Branch:** `main`
- **Paths of interest:**
  - `.pi/skills/battle/battle.py`

## Summary

Review the battle skill implementation for security vulnerabilities. This is a Red vs Blue firmware security competition tool that runs QEMU inside Docker containers, manages AFL++ fuzzing, handles user-controlled paths, and executes subprocess commands.

## Objectives

### 1. Find command injection vulnerabilities

Find command injection vulnerabilities

### 2. Identify Docker escape risks

Identify Docker escape risks

### 3. Check for path traversal vulnerabilities

Check for path traversal vulnerabilities

### 4. Review subprocess handling for shell injection

Review subprocess handling for shell injection

### 5. Identify architectural security issues

Identify architectural security issues

### 6. Find race conditions in multi-process code

Find race conditions in multi-process code

## Constraints for the patch

- **Output format:** Unified diff only, inline inside a single fenced code block.
- Include a one-line commit subject on the first line of the patch.
- Hunk headers must be numeric only (`@@ -old,+new @@`); no symbolic headers.
- Patch must apply cleanly on branch `main`.
- No destructive defaults; retain existing behavior unless explicitly required by this change.
- No extra commentary, hosted links, or PR creation in the output.

## Acceptance criteria

- All subprocess calls use proper argument lists (no shell=True with user input)
- All file paths are validated and sandboxed
- Docker containers cannot escape to host
- No command injection vectors

## Test plan

**Before change** (optional): (Describe how to reproduce the issue)

**After change:**

1. (Specify test steps)

## Implementation notes

(Add implementation hints here)

## Known touch points

- (List files/functions to modify)

## Clarifying questions

*Answer inline here or authorize assumptions:*

1. (Add any clarifying questions here)

## Deliverable

- Reply with a single fenced code block containing a unified diff that meets the constraints above (no prose before/after the fence)
- In the chat, provide answers to each clarifying question explicitly so reviewers do not need to guess
- Do not mark the request complete if either piece is missing; the review will be considered incomplete without both the diff block and the clarifying-answers section
