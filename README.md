# Flatcut

A Blender extension that prepares wooden/plywood 3D models for 2D fabrication
on laser cutters and CNC routers.

- **Slice Face Setup** — define a cutting plane on any mesh object by
  selecting its face(s) in Edit Mode, or let Flatten & Arrange auto-detect
  the largest flat face of plate-like objects
- **Guided export workflow** — flatten and arrange sliced parts into a
  preview scene, pack/nest them within a configurable work area, and preview
  toolpaths with depth-based color coding
- **G-code export** for CNC routers (feed rate, tool diameter, step-down
  depth, multi-pass cutting, retention tabs)
- **SVG export** for laser cutters (top-view outline)
- **Machine profiles** (CNC Mill / Laser Cutter) with sensible per-machine
  defaults, plus save/load/delete named settings presets

Requires Blender 5.0+.

## Installation

- From [extensions.blender.org](https://extensions.blender.org) (once
  published): search for "Flatcut" in Blender's Get Extensions.
- Manually: download a release zip and install it via
  Preferences > Add-ons > install from disk, or `blender --command extension
  install-file <zip>`.

## Usage

1. Enable the extension; a "Flatcut" tab appears in the 3D Viewport sidebar
   (N-panel).
2. Select a mesh, enter Edit Mode, select the face(s) that define the cutting
   plane, and click **Save Slice Face**. This step is optional for plate-like
   objects: **1. Flatten & Arrange** detects and saves the largest flat face
   of any selected object that has no slice face yet (turn this off with
   **Auto-Detect Slice Face** in Settings). The slice face is stored in the
   object's custom properties and leaves the mesh untouched — click **Select
   Slice Face** to enter Edit Mode with the saved faces selected and see
   which ones are in use.
3. Back in Object Mode, open **Settings** to configure machine type (CNC/
   Laser), feed rate, tool diameter, etc.
4. Run the export workflow in order: **1. Flatten & Arrange** → **2. Pack
   Objects** → **3. Add Toolpaths** → **4. Download G-code** (or **Export
   SVG**).
5. **Cancel and Return** discards the preview scene and returns you to the
   original scene.

## Releasing

extensions.blender.org does not track this repository — a version goes live
only when its `.zip` is uploaded there. Publishing a GitHub Release runs
`.github/workflows/publish-extension.yml`, which validates the manifest
against the tag, builds the package, attaches it to the release and uploads
it to the platform. It needs a repository secret `BLENDER_EXTENSIONS_TOKEN`,
generated at https://extensions.blender.org/settings/tokens/.

The listing icon is platform metadata rather than part of the package, so it
is uploaded on the listing page and needs no new version. Its source is
`design/icon/flatcut-icon.svg`; re-export with
`inkscape design/icon/flatcut-icon.svg -o out.png -w 256 -h 256`.

To release: bump `version` in `blender_manifest.toml`, then create a GitHub
Release tagged `v<version>`. To build the package locally instead:

```
blender --command extension validate .
blender --command extension build --source-dir . --output-dir dist
```

## Development

This repo's root *is* the installable extension package (it contains
`blender_manifest.toml` directly).

To develop with live reload in Blender, without zipping/installing:

1. Clone this repo somewhere, e.g. `~/projects/flatcut`.
2. In Blender, add a **Local (Custom Directory)** Extensions repo pointing at
   the *parent* directory of the clone (e.g. `~/projects`) — Blender
   discovers `flatcut/` inside it as a package.
3. Enable "Flatcut" from that repo.
4. For live reload on save, install [`watch_reload.py`](watch_reload.py) as
   its own separate add-on (Preferences > Add-ons > Install...) and enable
   it — it watches Flatcut's files and auto-reloads on change, so edits show
   up without disabling/re-enabling the extension or restarting Blender.

To build a release zip:

```
blender --command extension validate .
blender --command extension build --source-dir . --output-dir dist
```

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
