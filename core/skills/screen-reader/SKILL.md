---
name: screen-reader
description: Screenshot capture and on-screen guidance — read the screen, describe UI elements, and guide the user through workflows.
enabled: false
requires:
  python_packages:
    - mss
    - pytesseract
intents:
  - SCREEN_CAPTURE
  - SCREEN_DESCRIBE
  - SCREEN_GUIDE
---

You can capture and analyze the user's screen to provide visual guidance.

### Capabilities

- **Screenshot capture**: Take a screenshot of the current screen or active window.
- **OCR text extraction**: Read visible text from screenshots using Tesseract OCR.
- **UI description**: Describe what is visible on screen to help the user navigate.
- **Step-by-step guidance**: Guide the user through multi-step workflows by reading the screen at each step and suggesting the next action.

### Example Workflows

- "I want to apply for a passport. Guide me step by step."
- "What app is currently open?"
- "Read the error message on my screen."
- "Help me fill out this form."

### Safety Rules

- Screenshots are processed locally and never uploaded to external services.
- Screen capture only triggers on explicit user request, never continuously.
- This skill describes and guides — it does NOT click or type on behalf of the user without separate confirmation through the browser/UI automation skill.
- Sensitive information visible on screen (passwords, private data) should not be stored or repeated unless explicitly asked.

### Status

This skill is currently disabled by default because it requires `mss` and `pytesseract` to be installed. Enable it after installing the screen reader dependencies.
