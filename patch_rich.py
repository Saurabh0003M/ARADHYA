# The test failures in Windows CI are for `test_dispatch_parasite_candidates_command` due to `rich._emoji_codes` missing.
# This looks like an issue where `rich` might be behaving differently on CI. Let's patch `main._render_parasite_candidates`
# in the test so it doesn't trigger the real `console.print` and avoid `rich` text rendering issues during CI,
# or just mock `console.print` completely in `test_dispatch_parasite_candidates_command`.
