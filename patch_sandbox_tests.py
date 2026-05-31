from unittest.mock import patch, MagicMock

# The tests are failing because we're running in Linux environment and `powershell` / `icacls` are not found.
# Let's see what the original tests do.
