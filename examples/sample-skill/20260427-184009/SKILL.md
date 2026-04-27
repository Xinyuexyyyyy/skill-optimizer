---
name: sample-skill
description: A sample skill demonstrating the SKILL.md format. Use when: user asks for a sample or example skill.
status: stable
---

# Sample Skill

## Overview

This is a sample skill for testing the skill-optimizer.

## Workflow

1. **Parse input** → Extract user intent
   - Input: user message
   - Output: parsed intent

2. **Execute action** → Run the appropriate handler
   - Input: parsed intent
   - Output: action result

3. **Format output** → Return response to user
   - Input: action result
   - Output: formatted message

## Actions

| Action | Description |
|--------|-------------|
| `hello` | Say hello |
| `help` | Show help |

## Boundary Conditions

### File Not Found
**Condition**: SKILL.md missing
**Handling**: Return error "Skill not found"

### Invalid Action
**Condition**: Unknown action requested
**Handling**: Return available actions list

## Checkpoints

1. Before executing destructive actions → Ask user confirmation
2. Before external API calls → Show request details

## Resources

| File | Purpose |
|------|---------|
| `skill.py` | Main implementation |
| `config.yaml` | Configuration |

## Examples

```bash
# Say hello
skill-optimizer hello

# Show help
skill-optimizer help
```
