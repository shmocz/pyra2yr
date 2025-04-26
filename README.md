# pyra2yr

Python interface for ra2yrcpp.

## Installation

### Method 1: Install pre-built wheel using pip

Install a pre-built wheel:
```bash
pip install -U https://github.com/shmocz/pyra2yr/releases/download/v0.3.0/pyra2yr-0.3.0-py3-none-any.whl
```

### Method 2: Install with poetry

TODO

## Setup

Multi-game test environments are created with docker and require Docker Compose. Build the necessary images:

```bash
docker compose build
```

Download and extract [ra2yrcpp](https://github.com/shmocz/ra2yrcpp/releases/download/latest/ra2yrcpp.zip) to CnCNet data folder. Patch `gamemd-spawn.exe` according to [instructions](https://github.com/shmocz/ra2yrcpp#usage).

## Usage

See `pyra2yr/examples/basic_usage.py` files for example usage.

## Tests

In a suitable python environment, run:

```bash
python -m unittest
```

Various environment variables are accepted:

- `USE_SYRINGE` if defined, use Syringe instead of legacy spawner. Assumes `Syringe.exe` is in game data folder.
- `USE_X11` (Linux only) Use host X server instead of VNC by exposing `/tmp/.X11-unix` to container.
- `X11_SOCKET` (Linux only) is `USE_X11` is defined alternative path to X server socket.

> [!NOTE]
> Any value will enable a boolean setting, even values like `no`, `False` and `n`.

For example:

```bash
USE_SYRINGE=y USE_X11=y python -m unittest
```
