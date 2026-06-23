---
name: screen-reader
description: Screenshot capture and on-screen guidance — read the screen, describe UI elements, and guide the user through workflows.
enabled: true
intents:
  - SCREEN_CAPTURE
  - SCREEN_DESCRIBE
  - SCREEN_GUIDE
---

You can capture and analyze the user's screen to provide visual guidance.

### Capabilities

- **Screenshot capture** (`screen_capture`): Take a screenshot of the current screen or a region.
- **Visual UI description** (`describe_screen`): Describe what is visible — layout, buttons, dialogs, and state — using a local vision model, going beyond raw text. Prefer this for "what's on screen?" / "where is the X button?" questions.
- **OCR text extraction** (`screen_read_text`): Read visible text from the screen when you only need the exact wording (error messages, codes). Uses Tesseract if available, else the built-in Windows OCR.
- **Step-by-step guidance**: Guide the user through multi-step workflows by reading the screen at each step and suggesting the next action.

### Choosing a tool

- Need to understand the layout or find a control → `describe_screen`.
- Need the exact on-screen text verbatim → `screen_read_text`.
- Just need a saved image (to attach or re-analyze) → `screen_capture`.

### Example Workflows

- "I want to apply for a passport. Guide me step by step."
- "What app is currently open?"
- "Read the error message on my screen."
- "Help me fill out this form."

### Safety Rules

- Screenshots are processed locally and never uploaded to external services. `describe_screen` uses a local vision model only; the cloud provider refuses screen images by design.
- Screen capture only triggers on explicit user request, never continuously.
- This skill describes and guides — it does NOT click or type on behalf of the user without separate confirmation through the browser/UI automation skill.
- Sensitive information visible on screen (passwords, private data) should not be stored or repeated unless explicitly asked.

### Requirements

- Capture works out of the box on Windows (PowerShell fallback); `pip install mss` or `Pillow` makes it faster.
- `describe_screen` needs a local vision model configured as `vision_model` in the model profile (e.g. `moondream` or `llava` pulled in Ollama). Without one it reports that no vision model is available.
- `screen_read_text` uses Tesseract if installed, otherwise the built-in Windows OCR engine.
