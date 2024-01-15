# pyra2yr

Python interface for ra2yrcpp.

## Installation

### Method 1: Install pre-built wheel using pip

Install a pre-built wheel:
```bash
pip install -U https://github.com/shmocz/pyra2yr/releases/download/v0.2.0/pyra2yr-0.2.0-py3-none-any.whl
```

### (TODO) Method 2: Install with poetry

## Setup

Multi-game test environments are created with docker and require Docker Compose. Build the necessary images:

```bash
docker compose build
```

Download and extract [ra2yrcpp](https://github.com/shmocz/ra2yrcpp/releases/download/latest/ra2yrcpp.zip) to CnCNet data folder. Patch `gamemd-spawn.exe` according to [instructions](https://github.com/shmocz/ra2yrcpp#usage).

## Usage

See `pyra2yr/examples/basic_usage.py` files for example usage.
