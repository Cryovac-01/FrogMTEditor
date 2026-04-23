# Frog Mod Editor

Frog Mod Editor is an open-source Windows desktop tool for inspecting and editing selected Motor Town part assets. Engine creation/editing works completely, tire creation/editing is incomplete.


## Start the app

1. Extract `Frog_Mod_Editor_Complete_Source_Release.zip`.
2. Double-click `FrogModEditor.cmd`.

## Optional: Build a standalone EXE

If you prefer an `.exe` launcher instead of the `.cmd` file:

1. Open a Command Prompt in the extracted folder.
2. Run: `FrogModEditor.cmd /build`
3. A `FrogModEditor.exe` will be created in the same folder.
4. You can then double-click the `.exe` to launch the editor.

Note: The `.cmd` and `.exe` launchers do the exact same thing. The `.cmd` is
recommended since some antivirus tools may flag the locally-compiled `.exe`
(false positive — the source is in `source\build_launcher.ps1` if you want
to verify).

## Basic workflow

- Browse vanilla parts from the app's part list to inspect current values.
- Open a generated mod part to edit supported fields.
- Use the create-engine screen to pick a template, adjust values, choose shop text/price/weight, and create a new engine.
- Use the create-tire screen to clone a vanilla tire layout and edit supported tire fields.
- Use the pack action to write a game-ready `_P.pak` file.
- Use the template pack action to export every curated engine template into one `_P.pak`.

## Where files are written

- Generated engines and tires are written under `source\data\mod\MotorTown\Content\Cars\Parts`.
- Generated DataTable entries are written under `source\data\mod\MotorTown\Content\DataAsset\VehicleParts`.
- Template definitions are under `source\data\templates\Engine`.
- Vanilla reference data is under `source\data\vanilla`.

## Notes

- Names for new parts should use letters and numbers only.
- The app normalizes pak names so output files end in `_P.pak`.
- Keep a backup of any pak you replace in your Motor Town install.

## License

Frog Mod Editor is released under the Creative Commons Attribution-NonCommercial 4.0 International license, `CC BY-NC 4.0`.

Plain-language summary: you may inspect, modify, share, and learn from this project for free. You may not sell it, monetize it, bundle it into paid products, or use it to provide paid services without separate written permission.

Motor Town game names, game paths, and referenced asset formats belong to their respective owners. Those game-specific references are separate from this project's license.
