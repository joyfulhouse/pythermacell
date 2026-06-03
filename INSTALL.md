# Installing pythermacell

## Requirements

- Python 3.13 or newer.

## Install from PyPI

```bash
pip install pythermacell
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv add pythermacell
```

## Install from Source

```bash
git clone https://github.com/joyfulhouse/pythermacell.git
cd pythermacell
uv sync
```

This installs the package with its development dependencies into a local virtual
environment.

## Verify the Installation

```bash
python -c "import pythermacell; print(pythermacell.__version__)"
```

You should see the installed version printed with no import errors. (If the
distribution name contains a hyphen, the import name uses an underscore instead.)

## Next Steps

See the [README](README.md#quick-start) for a quick-start example and the
[Usage Guide](docs/USAGE.md) for the full walkthrough.
