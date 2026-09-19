"""
Settings Presets

Save and load settings as named presets (JSON files).
"""

import json
from pathlib import Path

# Bundled read-only presets shipped alongside this file.
BUNDLED_PRESETS_DIR = Path(__file__).parent

# Properties to save/load
PRESET_PROPERTIES = [
    'machine_type',
    'feed_rate_cut',
    'feed_rate_plunge',
    'safe_height',
    'step_down',
    'tool_diameter',
    'spindle_speed',
    'laser_power',
    'laser_speed',
    'depth_extra',
    'retract_between_passes',
    'tab_enabled',
    'tab_height',
    'tab_width',
    'tab_count',
    'pack_area_width',
    'pack_area_height',
]


def get_user_presets_dir():
    """
    Get the user-writable presets directory, create if needed.

    Prefers Blender's per-extension user data location (works when
    distributed as an extension, whose install directory may be read-only
    or wiped on update); falls back to the bundled folder for dev installs.
    """
    try:
        import bpy
        path = Path(bpy.utils.extension_path_user(__package__, path="presets", create=True))
        return path
    except Exception:
        BUNDLED_PRESETS_DIR.mkdir(exist_ok=True)
        return BUNDLED_PRESETS_DIR


def list_presets():
    """Return sorted list of preset names (without .json extension), merging
    bundled defaults with user-saved presets (user entries take precedence)."""
    names = {p.stem for p in BUNDLED_PRESETS_DIR.glob("*.json")}
    names.update(p.stem for p in get_user_presets_dir().glob("*.json"))
    return sorted(names)


def _find_preset_file(name):
    """Look up a preset by name, preferring the user directory over bundled."""
    user_path = get_user_presets_dir() / f"{name}.json"
    if user_path.exists():
        return user_path
    bundled_path = BUNDLED_PRESETS_DIR / f"{name}.json"
    if bundled_path.exists():
        return bundled_path
    return None


def save_preset(name, gcode_props):
    """
    Save current gcode_properties to a named preset in the user directory.

    Args:
        name: Preset name
        gcode_props: GcodeProperties PropertyGroup
    """
    data = {}
    for prop_name in PRESET_PROPERTIES:
        try:
            data[prop_name] = getattr(gcode_props, prop_name)
        except AttributeError:
            pass

    filepath = get_user_presets_dir() / f"{name}.json"
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)

    return str(filepath)


def load_preset(name, gcode_props):
    """
    Load a named preset into gcode_properties.

    Args:
        name: Preset name
        gcode_props: GcodeProperties PropertyGroup

    Returns:
        True if loaded successfully
    """
    filepath = _find_preset_file(name)
    if filepath is None:
        return False

    with open(filepath, 'r') as f:
        data = json.load(f)

    for prop_name, value in data.items():
        if prop_name in PRESET_PROPERTIES:
            try:
                setattr(gcode_props, prop_name, value)
            except (AttributeError, TypeError):
                pass

    return True


def delete_preset(name):
    """
    Delete a named preset from the user directory. Bundled presets cannot
    be deleted.

    Args:
        name: Preset name

    Returns:
        True if deleted
    """
    filepath = get_user_presets_dir() / f"{name}.json"
    if filepath.exists():
        filepath.unlink()
        return True
    return False
