from dataclasses import dataclass, field, asdict


class Docker:
    @classmethod
    def _common(cls, compose_files=None):
        cf = compose_files or ["docker-compose.yml"]
        r = ["docker", "compose"]
        for c in cf:
            r.extend(["-f", c])
        return r

    @classmethod
    def run(
        cls,
        cmd,
        service,
        compose_files=None,
        uid=None,
        name=None,
        env=None,
        volumes=None,
    ):
        r = cls._common(compose_files=compose_files)
        r.extend(["run", "--rm", "-T"])
        if uid:
            r.extend(["-u", f"{uid}:{uid}"])
        if env:
            for k, v in env:
                r.extend(["-e", f"{k}={v}"])
        if volumes:
            for k, v in volumes:
                r.extend(["-v", f"{k}:{v}"])
        if name:
            r.append(f"--name={name}")
        r.append(service)
        r.extend(cmd)
        return r

    @classmethod
    def exec(cls, cmd, service, compose_files=None, uid=None, env=None):
        r = cls._common(compose_files=compose_files)
        r.extend(["exec", "-T"])
        if uid:
            r.extend(["-u", f"{uid}:{uid}"])
        if env:
            for k, v in env:
                r.extend(["-e", f"{k}={v}"])
        r.append(service)
        r.extend(cmd)
        return r

    @classmethod
    def up(cls, services, compose_files=None):
        r = cls._common(compose_files)
        r.extend(["up", "--abort-on-container-exit"])
        r.extend(services)
        return r


@dataclass
class ComposeService:
    name: str
    image: str
    command: str = None
    network_mode: str = None
    user: str = None
    ports: list[int] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    environment: dict[str, str] = field(default_factory=dict)
    stop_signal: str = None
    cap_add: list[str] = field(default_factory=list)
    working_dir: str = None
    volumes: list[str] = field(default_factory=list)

    def to_dict(self):
        d = asdict(self)
        n = d.pop("name")
        return {n: {k: v for k, v in d.items() if v}}
