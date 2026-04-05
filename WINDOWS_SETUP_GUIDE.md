# Aradhya Setup Guide - Windows Edition (F: Drive)

## 🎯 Your Current Situation

**Existing Structure:**
```
F:\ARADHYA\
├── audio\
├── core\
│   ├── agent\
│   │   ├── aradhya.py          ← Your existing agent!
│   │   └── open_target.py
│   ├── config\
│   ├── logs\
│   └── memory\
│       ├── preferences.json
│       └── profile.json
├── execution\
├── experiments\
└── models\
```

**What We'll Add:** Professional Python project structure while **keeping everything you have**!

## 📍 Why F: Drive is Perfect

Your thinking is actually **correct**! Using F: drive is smart because:

✅ **Safety**: C: drive (system) stays clean and protected
✅ **Backups**: Easy to backup entire F:\ARADHYA folder
✅ **Experiments**: Can try anything without affecting system
✅ **Organization**: All project files in one place
✅ **Portability**: If F: is external drive, take it anywhere
✅ **No Permissions**: No Windows permission headaches

## 🚀 Quick Setup (5 minutes)

### Step 1: Download the Setup Script

1. Save `setup_aradhya_windows.py` to **F:\ARADHYA**
2. Open Command Prompt or PowerShell
3. Navigate to your project:
   ```cmd
   F:
   cd ARADHYA
   ```

### Step 2: Run the Setup Script

```cmd
python setup_aradhya_windows.py
```

This will:
- ✅ Keep all your existing files (core/, audio/, execution/, etc.)
- ✅ Add professional Python structure (src/, tests/, docs/)
- ✅ Create VSCode configuration
- ✅ Create Windows batch files for automation
- ✅ Set up requirements files
- ✅ Configure testing framework

### Step 3: Create Virtual Environment

```cmd
python -m venv venv
```

### Step 4: Activate Environment

```cmd
venv\Scripts\activate
```

You'll see `(venv)` in your prompt:
```
(venv) F:\ARADHYA>
```

### Step 5: Install Dependencies

```cmd
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### Step 6: Open in VSCode

```cmd
code .
```

## 🎯 Even Quicker Setup (Use Batch File!)

After running `setup_aradhya_windows.py`, just double-click:

**`F:\ARADHYA\scripts\setup.bat`**

This automatically does steps 3-5 for you!

## 📁 Your New Structure (Merged)

```
F:\ARADHYA\
│
├── core/                      ← EXISTING (PRESERVED)
│   ├── agent/
│   │   ├── aradhya.py        ← Your main agent
│   │   └── open_target.py
│   ├── config/
│   ├── logs/
│   └── memory/
│
├── src/aradhya/              ← NEW (ADDED)
│   ├── main.py               ← New entry point
│   ├── utils/                ← Helper functions
│   ├── phase1/               ← Learning phase 1
│   ├── phase2/               ← Learning phase 2
│   └── phase3/               ← Learning phase 3
│
├── execution/                ← EXISTING (PRESERVED)
├── experiments/              ← EXISTING (PRESERVED)
├── models/                   ← EXISTING (PRESERVED)
├── audio/                    ← EXISTING (PRESERVED)
│
├── tests/                    ← NEW (ADDED)
│   ├── unit/                 ← Test individual functions
│   └── integration/          ← Test system integration
│
├── docs/                     ← NEW (ADDED)
│   ├── README.md
│   ├── ARCHITECTURE.md
│   └── phases/               ← Phase documentation
│
├── scripts/                  ← NEW (ADDED)
│   ├── setup.bat            ← One-click setup
│   ├── activate_env.bat     ← Activate environment
│   ├── run_tests.bat        ← Run all tests
│   └── run_agent.bat        ← Run your agent
│
├── data/                     ← NEW (ADDED)
│   ├── raw/                 ← Original data
│   └── processed/           ← Processed data
│
├── config/                   ← NEW (ADDED)
│   ├── development.yaml
│   └── production.yaml
│
├── .vscode/                  ← NEW (ADDED)
│   ├── settings.json        ← VSCode Python config
│   ├── launch.json          ← Debug configurations
│   └── extensions.json      ← Recommended extensions
│
├── venv/                     ← NEW (CREATED)
│   └── Scripts/
│       ├── python.exe
│       ├── activate.bat
│       └── ...
│
├── requirements.txt          ← NEW (ADDED)
├── requirements-dev.txt      ← NEW (ADDED)
├── pyproject.toml           ← NEW (ADDED)
├── .gitignore               ← NEW (ADDED)
├── .env.example             ← NEW (ADDED)
└── README.md                 ← NEW (ADDED, old backed up)
```

## 🎮 Using the Batch Files

### Activate Environment
Double-click: `scripts\activate_env.bat`
Or in Command Prompt:
```cmd
scripts\activate_env.bat
```

### Run Your Existing Agent
Double-click: `scripts\run_agent.bat`
Or:
```cmd
scripts\run_agent.bat
```

### Run Tests
Double-click: `scripts\run_tests.bat`
Or:
```cmd
scripts\run_tests.bat
```

## 🛠️ VSCode Setup

### 1. Open VSCode
```cmd
F:
cd ARADHYA
code .
```

### 2. Select Python Interpreter
- Press `Ctrl+Shift+P`
- Type: "Python: Select Interpreter"
- Choose: `.\venv\Scripts\python.exe`

### 3. Install Recommended Extensions
VSCode will show a popup asking to install recommended extensions. Click **"Install All"**.

Recommended extensions:
- Python
- Pylance
- Black Formatter
- Flake8
- GitLens

### 4. Start Coding!
Everything is configured:
- ✅ Auto-format on save (Black)
- ✅ Linting (Flake8)
- ✅ Debugging
- ✅ Testing
- ✅ IntelliSense

## 🧪 Your First Code in the New Structure

### Example: Create a utility in Phase 1

Create file: `F:\ARADHYA\src\aradhya\phase1\greeting.py`

```python
"""
Phase 1: Learning Python Basics
Simple greeting module
"""

def greet(name: str) -> str:
    """
    Generate a greeting message.
    
    Args:
        name: The name to greet
        
    Returns:
        A greeting message
    """
    return f"Hello, {name}! Welcome to Aradhya!"

def main():
    """Main function"""
    print(greet("World"))
    print(greet("Python Learner"))

if __name__ == "__main__":
    main()
```

### Run it:
```cmd
python src\aradhya\phase1\greeting.py
```

Or in VSCode:
- Right-click the file
- Select "Run Python File in Terminal"
- Or press `Ctrl+F5`

### Write a test:

Create file: `F:\ARADHYA\tests\unit\test_greeting.py`

```python
"""Tests for greeting module"""
from src.aradhya.phase1.greeting import greet

def test_greet():
    """Test greet function"""
    assert greet("Alice") == "Hello, Alice! Welcome to Aradhya!"
    assert greet("Bob") == "Hello, Bob! Welcome to Aradhya!"
```

### Run the test:
```cmd
pytest tests\unit\test_greeting.py -v
```

Or use the batch file:
```cmd
scripts\run_tests.bat
```

## 🔗 Integrating with Your Existing Agent

Your existing agent is at `core\agent\aradhya.py`. Here's how to use it in new code:

### Create a wrapper in Phase 1:

`src\aradhya\phase1\agent_wrapper.py`

```python
"""
Wrapper for existing Aradhya agent
Integrates old and new structure
"""

import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Now you can import your existing agent
# from core.agent.aradhya import AradhyaAgent  # Assuming you have this class

def run_existing_agent():
    """Run the existing agent"""
    # Import and run your existing agent
    import runpy
    runpy.run_path("core/agent/aradhya.py")

if __name__ == "__main__":
    run_existing_agent()
```

## 📚 Learning Path with New Structure

### Week 1: Get Familiar
- Explore `src\aradhya\phase1\`
- Create simple Python scripts
- Write basic tests in `tests\unit\`
- Use VSCode debugging

### Week 2: Build Features
- Create modules in `src\aradhya\phase2\`
- Integrate with existing agent in `core\agent\`
- Write integration tests
- Use Git for version control

### Week 3: Advanced
- Work in `src\aradhya\phase3\`
- Improve existing agent
- Add new features
- Comprehensive testing

### Week 4: Polish
- Documentation in `docs\`
- Code cleanup
- Performance optimization
- Prepare for deployment

## 🎯 Common Windows Commands

### Navigation
```cmd
F:                          # Switch to F drive
cd ARADHYA                  # Change directory
dir                         # List files
cd ..                       # Go up one directory
```

### Virtual Environment
```cmd
python -m venv venv        # Create venv
venv\Scripts\activate      # Activate
deactivate                 # Deactivate
```

### Python
```cmd
python script.py           # Run a script
python -m module           # Run as module
pip install package        # Install package
pip list                   # List packages
pip freeze                 # Show installed versions
```

### Testing
```cmd
pytest                     # Run all tests
pytest tests\unit         # Run unit tests only
pytest -v                  # Verbose output
pytest --cov              # With coverage
```

## 🐛 Troubleshooting

### "python is not recognized"
1. Install Python from python.org
2. Check "Add Python to PATH" during installation
3. Restart Command Prompt

### "Access Denied" errors
- Run Command Prompt as Administrator
- Or use your user folder instead of F:

### Virtual environment not activating
```cmd
# Use full path
F:\ARADHYA\venv\Scripts\activate.bat

# Or navigate first
cd F:\ARADHYA
venv\Scripts\activate
```

### VSCode not finding Python
1. Install Python extension
2. `Ctrl+Shift+P` → "Python: Select Interpreter"
3. Choose `.\venv\Scripts\python.exe`

### Import errors
Make sure you're in project root and venv is activated:
```cmd
F:
cd ARADHYA
venv\Scripts\activate
python -m src.aradhya.main
```

## 💡 Pro Tips for Windows

1. **Use Windows Terminal**: Better than Command Prompt
   - Install from Microsoft Store
   - Supports tabs and better colors

2. **PowerShell Alternative**: More powerful than cmd
   ```powershell
   # Activate venv in PowerShell
   .\venv\Scripts\Activate.ps1
   ```

3. **Path Shortcuts**: Create desktop shortcuts to batch files
   - Right-click `setup.bat` → Send to → Desktop

4. **Environment Variables**: Set PYTHONPATH in Windows
   - System Properties → Environment Variables
   - Add: `F:\ARADHYA` to PYTHONPATH

5. **Git Bash**: Unix-like terminal on Windows
   - Comes with Git for Windows
   - Use Unix commands on Windows

## ✅ Verification Checklist

After setup, verify everything works:

- [ ] Virtual environment created (`F:\ARADHYA\venv\` exists)
- [ ] Can activate venv (see `(venv)` in prompt)
- [ ] Dependencies installed (`pip list` shows packages)
- [ ] VSCode opens project correctly
- [ ] Python interpreter selected in VSCode
- [ ] Can run existing agent: `python -m core.agent.aradhya`
- [ ] Can run new main: `python -m src.aradhya.main`
- [ ] Tests run: `pytest`
- [ ] Formatting works (try `black .`)
- [ ] Git initialized (optional)

## 🎉 You're All Set!

Your F:\ARADHYA now has:
- ✅ Professional Python project structure
- ✅ All your existing code preserved
- ✅ VSCode fully configured
- ✅ Testing framework ready
- ✅ Batch files for automation
- ✅ Safe, organized, and scalable

**Start coding in `src\aradhya\phase1\` and build amazing things!** 🚀

---

### Quick Reference Card

```
Location:       F:\ARADHYA
Activate:       venv\Scripts\activate
Run Agent:      python -m core.agent.aradhya
Run Tests:      pytest
Format Code:    black .
Open VSCode:    code .
```

Need help? Check `docs\README.md` or create issues in your Git repo!
