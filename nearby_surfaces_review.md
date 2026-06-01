# Subprocess Surface Review

1. **`src/aradhya/scheduler.py`**
   - **Usage**: `subprocess.run(shlex.split(task.payload), shell=False, ...)`
   - **Status**: SAFE. Uses `shlex.split()` and `shell=False`.

2. **`src/aradhya/sandbox_manager.py`**
   - **Usage 1**: `subprocess.run(["powershell", "-NoProfile", "-Command", command], ...)`
   - **Status**: POTENTIAL RISK. `command` is passed directly to PowerShell `-Command`, which might interpret PowerShell injections. Follow-up needed if `command` comes from untrusted source.
   - **Usage 2**: `subprocess.run(cmd, ...)` inside `_icacls_grant`
   - **Status**: SAFE. `cmd` is `["icacls", str(path), "/grant:r", f"{username}:{permissions}", "/T"]` built internally.

3. **`src/aradhya/tools/power_tools.py`**
   - **Usage**: Several calls to `subprocess.run(["powershell", "-Command", f"..."], ...)`
   - **Status**: POTENTIAL RISK for injections depending on the interpolated variables. E.g., `f"Get-Process -Name '{name_filter}' ..."` could be manipulated if `name_filter` contains single quotes, like `''; Remove-Item -Recurse C:\; ''`. Follow-up needed to escape parameters properly.

4. **`src/aradhya/tools/system_tools.py`**
   - **Usage 1**: `subprocess.run(["xdg-open", str(target)], check=True)`
   - **Status**: SAFE. The argument is passed directly to the binary.
   - **Usage 2**: `subprocess.run(["powershell", "-Command", "Get-Clipboard"], ...)`
   - **Status**: SAFE. No user input interpolation.
   - **Usage 3**: `subprocess.run(["powershell", "-Command", f"Set-Clipboard -Value '{text}'"], ...)`
   - **Status**: POTENTIAL RISK. Single quotes in `text` could break out of the string literal and execute arbitrary powershell. Follow-up needed.

5. **`src/aradhya/tools/vision_tools.py`**
   - **Usage**: `subprocess.run(["powershell", "-Command", ps_script], ...)`
   - **Status**: RELATIVELY SAFE if `ps_script` doesn't contain unescaped user input. From a quick glance, it's mostly hardcoded scripts with paths. Needs deeper check if paths come from user input, but it's internal tooling.
