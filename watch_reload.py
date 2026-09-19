# -*- coding: utf-8 -*-
# Based on "Watch Reload" by Addam Dominec <adominec@gmail.com> (Copyright 2022, Free software)
# from https://github.com/addam/Export-Paper-Model-from-Blender

# Development-only helper: reloads the Flatcut extension whenever one of its
# source files changes on disk, so edits are picked up immediately instead of
# requiring you to disable/re-enable the extension or restart Blender.
#
# NOTE: This is a standalone add-on, independent of Flatcut itself. Install
# it separately (Edit > Preferences > Add-ons > Install...) and enable it.
#
# Matches by module name ("bl_ext.<repo>.<extension id>"), not file path, so
# it works regardless of which Extensions repo Flatcut was loaded from --
# e.g. a Local (Custom Directory) repo pointed at a live-edit clone (see
# README.md).

bl_info = {
    "name": "Watch Reload",
    "author": "Addam Dominec",
    "version": (0, 2),
    "blender": (5, 0, 0),
    "location": "",
    "warning": "",
    "description": "Watch for script update and reload automatically",
    "doc_url": "",
    "category": "Development",
}


import bpy
import sys
import importlib
import types
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Pair:
    module: types.ModuleType
    stamp: int
    def __repr__(self):
        return self.module.__name__
    __str__ = __repr__


def timestamp(filename):
    return Path(filename).stat().st_mtime


watchers = list()


def extension_target(extension_id):
    """
    Match modules of a Blender Extension package, identified by module name
    (e.g. "bl_ext.<repo>.<extension_id>[.submodule...]") rather than file
    path, since the on-disk location depends on which Extensions repo it was
    loaded from.
    """
    def parts_match(name):
        parts = name.split(".")
        return len(parts) >= 3 and parts[0] == "bl_ext" and parts[2] == extension_id

    def belongs(name, filename):
        return parts_match(name)

    def is_init(name, filename):
        return parts_match(name) and name.count(".") == 2

    return belongs, is_init


def watcher_factory(belongs, is_init, interval=1.0):
    modules = list()
    init = None
    for name, module in list(sys.modules.items()):
        filename = getattr(module, "__file__", None)
        if not filename:
            continue
        if belongs(name, filename):
            pair = Pair(module, timestamp(filename))
            modules.append(pair)
            if is_init(name, filename):
                init = pair
    print("Watching", modules)
    def watch_script():
        touched = list()
        for pair in modules:
            now = timestamp(pair.module.__file__)
            if now != pair.stamp:
                pair.stamp = now
                touched.append(pair)
        if touched:
            if init:
                init.module.unregister()
            for pair in touched:
                print("Auto-reload", pair)
                pair.module = importlib.reload(pair.module)
            if init:
                if init not in touched:
                    init.module = importlib.reload(init.module)
                init.module.register()
            # Registering/unregistering classes doesn't itself mark already-drawn
            # UI regions dirty, so already-visible panels won't reflect the
            # reload until something else triggers a redraw. Force one.
            for window in bpy.context.window_manager.windows:
                for area in window.screen.areas:
                    area.tag_redraw()
        return interval
    return watch_script


def start():
    prefs = bpy.context.preferences.addons[__name__].preferences
    if prefs.extension_id:
        belongs, is_init = extension_target(prefs.extension_id)
        watcher = watcher_factory(belongs, is_init, interval=prefs.interval or 1.0)
        watchers.append(watcher)
        bpy.app.timers.register(watcher, first_interval=prefs.interval, persistent=True)


def stop():
    for fn in watchers:
        try:
            bpy.app.timers.unregister(fn)
        except ValueError:
            pass
    watchers.clear()


def restart(self, context):
    stop()
    start()


class WatchPreferences(bpy.types.AddonPreferences):
    bl_idname = __name__
    extension_id: bpy.props.StringProperty(
        name="Extension ID", description="Package id of the Blender Extension to watch",
        default="flatcut", update=restart)
    interval: bpy.props.FloatProperty(
        name="Interval", description="Number of seconds between subsequent checks for updates",
        default=1, soft_min=0.1, soft_max=60, subtype="UNSIGNED", unit="TIME")

    def draw(self, context):
        self.layout.prop(self, "extension_id")
        self.layout.prop(self, "interval")


def register():
    bpy.utils.register_class(WatchPreferences)
    # Wait three seconds for all addons to be loaded. persistent=True is
    # required here: without it, Blender unregisters the timer the moment
    # the startup .blend finishes loading (which happens right after addon
    # registration at launch), so it would never actually fire.
    bpy.app.timers.register(start, first_interval=3.0, persistent=True)


def unregister():
    stop()
    bpy.utils.unregister_class(WatchPreferences)
