# Demo Projects

## UEEyesTest

A Third Person template project for testing and demonstrating UE Eyes with UE 5.7.

### Setup

1. **Open in UE 5.7** — Open `UEEyesTest/UEEyesTest.uproject`. UE will regenerate the Content/ from the Third Person template.

2. **Link the UEEyes plugin** — Create a junction from the demo project to the plugin source:

   ```cmd
   mklink /J demo_projects\UEEyesTest\Plugins\UEEyes plugin\UEEyes
   ```

   Or on Linux/macOS:
   ```bash
   ln -s ../../plugin/UEEyes demo_projects/UEEyesTest/Plugins/UEEyes
   ```

3. **Verify Python Remote Execution** — The project's `DefaultEditor.ini` has Remote Execution pre-enabled. Verify in Editor Preferences > Python > Remote Execution is checked.

4. **Test the connection:**
   ```bash
   cd <repo-root>
   uv run ue-eyes ping
   ```

### What's pre-configured

- Python Editor Script Plugin enabled in `.uproject`
- UEEyes plugin referenced in `.uproject`
- Remote Execution enabled in `Config/DefaultEditor.ini` (multicast 239.0.0.1:6766)
- Third Person template provides: mannequin (skeletal mesh), level geometry, lighting
