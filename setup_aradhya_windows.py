#!/usr/bin/env python3
"""
Aradhya Project Structure Setup - Windows Edition
Merges with existing structure and adds professional Python project setup
"""

import os
from pathlib import Path
import json

def create_structure():
    """Set up the Aradhya project structure for F:\ARADHYA"""
    
    # Base directory - F:\ARADHYA (your existing location)
    base_dir = Path("F:/ARADHYA")
    
    print(f"Setting up Aradhya project at: {base_dir}")
    print(f"Existing structure will be preserved!\n")
    
    # Define NEW structure to ADD (preserving your existing folders)
    structure = {
        # Your existing folders are kept: audio, core, execution, experiments, models
        
        # Add src structure for organized code
        "src/aradhya": [
            "__init__.py",
            "main.py",
        ],
        "src/aradhya/utils": [
            "__init__.py",
            "helpers.py",
        ],
        "src/aradhya/phase1": [
            "__init__.py",
            "README.md",
        ],
        "src/aradhya/phase2": [
            "__init__.py",
            "README.md",
        ],
        "src/aradhya/phase3": [
            "__init__.py",
            "README.md",
        ],
        
        # Tests directory
        "tests": [
            "__init__.py",
            "conftest.py",
        ],
        "tests/unit": [
            "__init__.py",
            "test_agent.py",
        ],
        "tests/integration": [
            "__init__.py",
        ],
        
        # Documentation
        "docs": [
            "README.md",
            "ARCHITECTURE.md",
        ],
        "docs/phases": [
            "phase1.md",
            "phase2.md",
            "phase3.md",
        ],
        
        # Scripts
        "scripts": [
            "setup.bat",
            "run_tests.bat",
            "activate_env.bat",
        ],
        
        # Data (you might already have some data organization)
        "data/raw": [".gitkeep"],
        "data/processed": [".gitkeep"],
        
        # Config
        "config": [
            "development.yaml",
            "production.yaml",
        ],
        
        # Ensure logs directory has gitkeep
        "core/logs": [".gitkeep"],
    }
    
    # Create directories and files
    for dir_path, files in structure.items():
        full_dir = base_dir / dir_path
        full_dir.mkdir(parents=True, exist_ok=True)
        
        # Skip if directory already exists and has content
        existing_files = list(full_dir.glob("*"))
        if existing_files and dir_path.startswith("core/"):
            print(f"⊙ Skipped (exists): {dir_path}")
            continue
            
        print(f"✓ Created: {dir_path}")
        
        for file in files:
            file_path = full_dir / file
            if not file_path.exists():
                file_path.touch()
                print(f"  ✓ {file}")
    
    # Create root-level files
    root_files = {
        "README.md": create_readme(),
        "requirements.txt": create_requirements(),
        "requirements-dev.txt": create_dev_requirements(),
        ".gitignore": create_gitignore(),
        "pyproject.toml": create_pyproject(),
        ".env.example": create_env_example(),
    }
    
    for filename, content in root_files.items():
        file_path = base_dir / filename
        if file_path.exists() and filename == "README.md":
            # Backup existing README
            backup_path = base_dir / "README.old.md"
            if not backup_path.exists():
                file_path.rename(backup_path)
                print(f"✓ Backed up existing README to README.old.md")
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✓ Created: {filename}")
    
    # Create .vscode settings for Windows
    vscode_dir = base_dir / ".vscode"
    vscode_dir.mkdir(exist_ok=True)
    
    vscode_files = {
        "settings.json": create_vscode_settings_windows(),
        "launch.json": create_vscode_launch_windows(),
        "extensions.json": create_vscode_extensions(),
    }
    
    for filename, content in vscode_files.items():
        file_path = vscode_dir / filename
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✓ Created: .vscode/{filename}")
    
    # Create batch files for Windows
    create_batch_files(base_dir)
    
    # Create initial main.py that uses existing agent
    create_main_integration(base_dir)
    
    print(f"\n{'='*70}")
    print(f"✨ Aradhya project structure updated successfully!")
    print(f"{'='*70}")
    print(f"\nExisting structure preserved:")
    print(f"  ✓ core/agent/aradhya.py")
    print(f"  ✓ core/agent/open_target.py")
    print(f"  ✓ core/memory/")
    print(f"  ✓ execution/")
    print(f"  ✓ experiments/")
    print(f"  ✓ models/")
    print(f"  ✓ audio/")
    print(f"\nNext steps:")
    print(f"1. Open Windows Command Prompt or PowerShell")
    print(f"2. cd F:\\ARADHYA")
    print(f"3. Run: python -m venv venv")
    print(f"4. Run: venv\\Scripts\\activate")
    print(f"5. Run: pip install -r requirements.txt")
    print(f"6. Run: code .  (to open in VSCode)")
    print(f"\nOr use the quick setup:")
    print(f"   F:\\ARADHYA\\scripts\\setup.bat")
    print(f"\nHappy coding! 🚀\n")


def create_readme():
    return """# Aradhya - AI Assistant Project

A multi-phase Python project for building an intelligent assistant.

## Project Structure

```
F:\\ARADHYA/
├── core/                   # Core functionality (EXISTING)
│   ├── agent/             # Agent logic
│   │   ├── aradhya.py    # Main agent
│   │   └── open_target.py
│   ├── config/            # Configuration
│   ├── logs/              # Application logs
│   └── memory/            # Memory & preferences
│       ├── preferences.json
│       └── profile.json
│
├── src/aradhya/           # Organized source code (NEW)
│   ├── phase1/           # Phase 1 learning
│   ├── phase2/           # Phase 2 features
│   └── phase3/           # Phase 3 advanced
│
├── execution/             # Execution environments (EXISTING)
│   ├── containers/
│   ├── linux_vm/
│   └── windows/
│
├── experiments/           # Experimental features (EXISTING)
├── models/                # AI models (EXISTING)
├── audio/                 # Audio processing (EXISTING)
│
├── tests/                 # Test suite (NEW)
├── docs/                  # Documentation (NEW)
├── scripts/               # Utility scripts (NEW)
└── data/                  # Data files (NEW)
```

## Setup

### Quick Setup (Windows)

```cmd
cd F:\\ARADHYA
scripts\\setup.bat
```

### Manual Setup

1. **Create virtual environment:**
   ```cmd
   python -m venv venv
   venv\\Scripts\\activate
   ```

2. **Install dependencies:**
   ```cmd
   pip install -r requirements.txt
   pip install -r requirements-dev.txt
   ```

3. **Configure environment:**
   ```cmd
   copy .env.example .env
   notepad .env
   ```

## Running the Project

### Activate environment first:
```cmd
venv\\Scripts\\activate
```

### Run the agent:
```cmd
python -m core.agent.aradhya
```

### Run new modular code:
```cmd
python -m src.aradhya.main
```

## Development Phases

- **Phase 1**: Python fundamentals & basic features
- **Phase 2**: Advanced agent capabilities
- **Phase 3**: Production deployment

## Testing

```cmd
pytest tests/
```

## Why F: Drive?

✓ Keeps system drive (C:) clean
✓ Easy to backup entire project
✓ Safe for experiments
✓ No permission issues
✓ Can be an external drive for portability

## Contributing

See `docs/` for detailed documentation.

## License

[Your License]
"""


def create_requirements():
    return """# Core dependencies
requests>=2.31.0
python-dotenv>=1.0.0
pyyaml>=6.0

# Logging
loguru>=0.7.0
colorama>=0.4.6  # For colored terminal output on Windows

# Data processing
pandas>=2.0.0
numpy>=1.24.0

# Audio (if needed for your audio/ folder)
# pyaudio>=0.2.13
# pydub>=0.25.1
# speech-recognition>=3.10.0

# AI/ML (if needed for models/)
# openai>=1.0.0
# anthropic>=0.7.0
# transformers>=4.30.0
# torch>=2.0.0

# Database (uncomment as needed)
# sqlalchemy>=2.0.0
"""


def create_dev_requirements():
    return """# Testing
pytest>=7.4.0
pytest-cov>=4.1.0
pytest-mock>=3.11.0

# Code quality
black>=23.7.0
flake8>=6.1.0
mypy>=1.5.0
isort>=5.12.0

# Development
ipython>=8.14.0
jupyter>=1.0.0
"""


def create_gitignore():
    return """# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
dist/
*.egg-info/
.eggs/
*.egg

# Virtual Environment
venv/
env/
ENV/

# IDE
.vscode/
.idea/
*.swp
.DS_Store

# Testing
.pytest_cache/
.coverage
htmlcov/

# Logs
*.log
core/logs/*.log
!core/logs/.gitkeep

# Environment
.env
.env.local

# Data
data/raw/*
data/processed/*
!data/raw/.gitkeep
!data/processed/.gitkeep

# Models
models/*.pkl
models/*.h5
models/*.pt
models/*.pth

# Windows
Thumbs.db
desktop.ini

# Experiments
experiments/*.tmp
experiments/*.cache
"""


def create_pyproject():
    return """[build-system]
requires = ["setuptools>=68.0.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "aradhya"
version = "0.1.0"
description = "AI Assistant Project"
readme = "README.md"
requires-python = ">=3.8"

[tool.black]
line-length = 100
target-version = ['py38', 'py39', 'py310', 'py311']

[tool.isort]
profile = "black"
line_length = 100

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
addopts = "-v --cov=src --cov=core --cov-report=html"
"""


def create_env_example():
    return """# Aradhya Configuration

# Application
APP_NAME=Aradhya
ENV=development
DEBUG=True

# Paths (Windows paths use double backslashes or forward slashes)
PROJECT_ROOT=F:/ARADHYA
LOGS_DIR=F:/ARADHYA/core/logs
DATA_DIR=F:/ARADHYA/data

# API Keys (add your keys here)
# OPENAI_API_KEY=sk-...
# ANTHROPIC_API_KEY=...

# Logging
LOG_LEVEL=INFO
"""


def create_vscode_settings_windows():
    return """{
    "python.defaultInterpreterPath": "${workspaceFolder}\\\\venv\\\\Scripts\\\\python.exe",
    "python.linting.enabled": true,
    "python.linting.pylintEnabled": true,
    "python.linting.flake8Enabled": true,
    "python.formatting.provider": "black",
    "python.testing.pytestEnabled": true,
    "python.testing.unittestEnabled": false,
    "python.testing.pytestArgs": ["tests"],
    "editor.formatOnSave": true,
    "editor.codeActionsOnSave": {
        "source.organizeImports": true
    },
    "files.exclude": {
        "**/__pycache__": true,
        "**/*.pyc": true,
        "**/.pytest_cache": true
    },
    "terminal.integrated.defaultProfile.windows": "Command Prompt",
    "python.analysis.typeCheckingMode": "basic"
}
"""


def create_vscode_launch_windows():
    return """{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Python: Aradhya Agent",
            "type": "python",
            "request": "launch",
            "module": "core.agent.aradhya",
            "console": "integratedTerminal",
            "justMyCode": true,
            "cwd": "${workspaceFolder}"
        },
        {
            "name": "Python: Main Module",
            "type": "python",
            "request": "launch",
            "module": "src.aradhya.main",
            "console": "integratedTerminal",
            "justMyCode": true
        },
        {
            "name": "Python: Current File",
            "type": "python",
            "request": "launch",
            "program": "${file}",
            "console": "integratedTerminal"
        },
        {
            "name": "Python: Pytest",
            "type": "python",
            "request": "launch",
            "module": "pytest",
            "args": ["tests/", "-v"],
            "console": "integratedTerminal"
        }
    ]
}
"""


def create_vscode_extensions():
    return """{
    "recommendations": [
        "ms-python.python",
        "ms-python.vscode-pylance",
        "ms-python.black-formatter",
        "ms-python.flake8",
        "ms-toolsai.jupyter",
        "github.copilot",
        "eamodio.gitlens"
    ]
}
"""


def create_batch_files(base_dir):
    """Create Windows batch files for common tasks"""
    
    scripts_dir = base_dir / "scripts"
    
    # Setup script
    setup_bat = """@echo off
echo ========================================
echo Aradhya Project Setup
echo ========================================
echo.

echo Creating virtual environment...
python -m venv venv
if errorlevel 1 (
    echo ERROR: Failed to create virtual environment
    pause
    exit /b 1
)

echo.
echo Activating virtual environment...
call venv\\Scripts\\activate.bat

echo.
echo Installing dependencies...
pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-dev.txt

echo.
echo ========================================
echo Setup complete!
echo ========================================
echo.
echo To activate the environment, run:
echo   venv\\Scripts\\activate
echo.
echo To start coding:
echo   code .
echo.
pause
"""
    
    # Activate environment script
    activate_bat = """@echo off
echo Activating Aradhya virtual environment...
call venv\\Scripts\\activate.bat
echo.
echo Environment activated!
echo Python: 
python --version
echo.
cmd /k
"""
    
    # Run tests script
    run_tests_bat = """@echo off
call venv\\Scripts\\activate.bat
echo Running tests...
pytest tests/ -v --cov=src --cov=core
pause
"""
    
    # Run agent script
    run_agent_bat = """@echo off
call venv\\Scripts\\activate.bat
echo Starting Aradhya Agent...
python -m core.agent.aradhya
pause
"""
    
    batch_files = {
        "setup.bat": setup_bat,
        "activate_env.bat": activate_bat,
        "run_tests.bat": run_tests_bat,
        "run_agent.bat": run_agent_bat,
    }
    
    for filename, content in batch_files.items():
        file_path = scripts_dir / filename
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✓ Created batch file: scripts/{filename}")


def create_main_integration(base_dir):
    """Create main.py that integrates with existing agent"""
    
    main_content = '''"""
Aradhya Main Entry Point
Integrates with existing agent structure
"""

import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

def main():
    """Main entry point for Aradhya"""
    print("=" * 60)
    print("Aradhya - AI Assistant")
    print("=" * 60)
    print()
    
    # You can import and use your existing agent here
    # from core.agent.aradhya import AradhyaAgent
    
    print("Phase 1: Setting up...")
    print("Your existing agent is at: core/agent/aradhya.py")
    print("Start building new features in: src/aradhya/phase1/")
    print()
    print("To run your existing agent:")
    print("  python -m core.agent.aradhya")
    print()

if __name__ == "__main__":
    main()
'''
    
    main_path = base_dir / "src" / "aradhya" / "main.py"
    with open(main_path, 'w', encoding='utf-8') as f:
        f.write(main_content)
    print(f"✓ Created integration: src/aradhya/main.py")


if __name__ == "__main__":
    try:
        create_structure()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nMake sure:")
        print("1. F:\\ARADHYA exists")
        print("2. You have write permissions")
        print("3. Python is installed")
        import traceback
        traceback.print_exc()
        input("\nPress Enter to exit...")
