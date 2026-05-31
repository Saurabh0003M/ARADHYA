# The tests that fail on Linux for SandboxManager are Windows specific as they run powershell or expect OS to be Windows.
# The code itself does not use platform.system() but assumes "powershell" exists.
# We will patch the tests to either skip on non-windows or mock out the subprocess calls.
