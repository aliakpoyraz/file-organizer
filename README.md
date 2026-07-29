# file-organizer

A configurable command-line tool that sorts files into folders using rules
based on extension, date, size, regex, or glob. It supports dry-run previews,
log-based undo, a watch mode, atomic verified moves, and conflict strategies.

## Install

The recommended install is a **standalone binary** — it bundles Python and every
dependency, so nothing needs to be installed on the target machine.

### Quick install (curl) — no Python needed

```bash
curl -fsSL https://raw.githubusercontent.com/aliakpoyraz/file-organizer/main/install.sh | bash
```

Downloads the prebuilt `fo` binary for your OS/CPU from the latest
[release](https://github.com/aliakpoyraz/file-organizer/releases) and drops it on
your `PATH`. Falls back to a source install only if no binary matches.

### Manual binary download

Grab the file for your platform from the
[latest release](https://github.com/aliakpoyraz/file-organizer/releases/latest),
then make it runnable:

| Platform | Asset |
| --- | --- |
| macOS (Apple Silicon) | `fo-macos-arm64` |
| macOS (Intel) | `fo-macos-x86_64` |
| Linux (x86_64) | `fo-linux-x86_64` |
| Windows (x86_64) | `fo-windows-x86_64.exe` |

```bash
chmod +x fo-macos-arm64 && mv fo-macos-arm64 /usr/local/bin/fo
```

On Windows, rename the `.exe` to `fo.exe` and put it on your `PATH`.

The binaries are built automatically on each version tag by
[`.github/workflows/release.yml`](.github/workflows/release.yml).

### From source (development)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Build a binary yourself

```bash
pip install . pyinstaller
pyinstaller packaging/fo.spec
./dist/fo --version
```

This produces a single self-contained executable in `dist/` for the machine you
build on.

## Interactive mode (`fo`)

The easiest way to use the tool. Just run:

```bash
fo
```

It opens a menu that asks what you want to do (organize, preview, watch, undo,
generate a config, ...) and walks you through each choice with arrow keys — no
flags to remember. Organizing always shows a preview and asks for confirmation
before moving anything.

## Usage (direct commands)

```bash
# Preview what would happen (no changes)
file-organizer preview ~/Downloads

# Actually organize
file-organizer organize ~/Downloads

# Organize with a custom config
file-organizer organize ~/Downloads -c examples/default-config.yaml

# Undo the last organize run
file-organizer undo

# Watch a folder and organize new files as they arrive
file-organizer watch ~/Downloads

# Write an example config to edit
file-organizer init-config -o my-config.yaml
```

### Common options

| Flag | Meaning |
| --- | --- |
| `-c/--config PATH` | Load rules from a YAML config |
| `-n/--dry-run` | Classify only, never move |
| `--conflict [rename\|skip\|overwrite]` | How to resolve name collisions |
| `--undo-log PATH` | Where to write the undo journal |
| `--follow-symlinks/--no-follow-symlinks` | Follow or skip symlinks |
| `--recursive/--no-recursive` | Descend into subdirectories |
| `--date-basis [created\|modified]` | Which timestamp `{year}`/`{month}` use |
| `--no-verify` | Skip the post-copy hash verification |
| `-v/--verbose` | Show tracebacks / error detail |
| `-q/--quiet` | Suppress the summary |
| `--json` | Emit a machine-readable summary |

CLI flags always override the values from the config file.

## Config format

```yaml
options:
  conflict_strategy: rename
  date_basis: modified
  recursive: false

rules:
  - name: images
    extensions: [jpg, jpeg, png, gif, heic]
    destination: "{source}/Images/{year}/{month}"
    date_bucket: true
    priority: 10
```

Template placeholders: `{source}`, `{ext}`, `{year}`, `{month}`,
`{month_name}`, `{day}`, `{size_bucket}`, `{name}`, `{rule}`.

## Development

```bash
python -m pytest --cov
```

Tests require ≥80% coverage.

## License

MIT
