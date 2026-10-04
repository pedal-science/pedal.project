"""pedald's configuration: what the service decides for itself, and what namchaind already owns.

`/etc/pedal/pedald.json` carries only the service's own settings: the UART the Pico is on, the
HTTP bind address and port, the upload size caps, the log level, the state directory. The
engine's port, its token file and the three roots under `/var/lib/pedal` are read from
`/etc/namchain/namchaind.json` instead, the way `pedal-resume` reads them, so each fact has one
home (R12 in docs/pedal-service.md) and a library that moves cannot leave the service pointing
at the old place.

The engine's file is not checked for unknown keys — it is the engine's, and it has keys this
process knows nothing about. pedald.json is checked, and an unknown key there is an error, not
a shrug: a misspelled `uart_baud` that quietly kept the default would be found on the bench at
best. Everything the service reads is small enough to name, so nothing is inferred.

Written for the Core host's `python3-minimal`: `json` and the standard library, nothing else.
"""

import json
import os

DEFAULT_UART_DEVICE = "/dev/ttyAMA0"
DEFAULT_UART_BAUD = 115200
DEFAULT_HTTP_HOST = "0.0.0.0"
DEFAULT_HTTP_PORT = 47820
DEFAULT_MAX_MODEL_BYTES = 16 << 20
DEFAULT_MAX_IR_BYTES = 64 << 20
DEFAULT_MAX_RIG_BYTES = 1 << 20
DEFAULT_LOG_LEVEL = "info"
DEFAULT_ENGINE_HOST = "127.0.0.1"
DEFAULT_STATE_ROOT = "/var/lib/pedal/state"

# Every key pedald.json may set, and the type each one has. The engine's keys are deliberately
# absent: `tcp_port` or `rigs_root` written here is a mistake, not an override (R12).
_SETTINGS = {
    "uart_device": str,
    "uart_baud": int,
    "http_host": str,
    "http_port": int,
    "max_model_bytes": int,
    "max_ir_bytes": int,
    "max_rig_bytes": int,
    "log_level": str,
    "engine_host": str,
    "state_root": str,
}

_INT_RANGES = {
    "uart_baud": (1, None),
    "http_port": (0, 65535),
    "max_model_bytes": (1, None),
    "max_ir_bytes": (1, None),
    "max_rig_bytes": (1, None),
}

# What the service takes from namchaind.json: attribute name in Config -> key in that file.
# None of these has a default, because without them the service has nowhere to read or write,
# so a missing engine file is an error rather than a set of empty strings.
_ENGINE_KEYS = {
    "engine_port": "tcp_port",
    "engine_token_file": "tcp_token_file",
    "rigs_root": "rigs_root",
    "models_root": "models_root",
    "irs_root": "irs_root",
}


class ConfigError(Exception):
    """pedald cannot be configured: an unreadable file, an unknown key, or a value that is not
    the kind of thing the key holds."""


class Config:
    """The service's settings, as `load()` filled them in.

    Every attribute is set, from the file or from the defaults above:

        uart_device, uart_baud                     the link to the Pico
        http_host, http_port                       this service's listener
        max_model_bytes, max_ir_bytes,             the upload caps
        max_rig_bytes
        log_level
        engine_host, engine_port, engine_token_file    namchaind, over TCP loopback
        rigs_root, models_root, irs_root           the library, as namchaind sees it
        state_root                                 bank.json and midi-map.json
    """

    def __init__(self):
        self.uart_device = DEFAULT_UART_DEVICE
        self.uart_baud = DEFAULT_UART_BAUD
        self.http_host = DEFAULT_HTTP_HOST
        self.http_port = DEFAULT_HTTP_PORT
        self.max_model_bytes = DEFAULT_MAX_MODEL_BYTES
        self.max_ir_bytes = DEFAULT_MAX_IR_BYTES
        self.max_rig_bytes = DEFAULT_MAX_RIG_BYTES
        self.log_level = DEFAULT_LOG_LEVEL
        self.engine_host = DEFAULT_ENGINE_HOST
        self.engine_port = 0
        self.engine_token_file = ""
        self.rigs_root = ""
        self.models_root = ""
        self.irs_root = ""
        self.state_root = DEFAULT_STATE_ROOT

    @classmethod
    def load(cls, path="/etc/pedal/pedald.json", engine_path="/etc/namchain/namchaind.json"):
        """Read both files and return a filled-in Config.

        Raises ConfigError for a file that cannot be read or parsed, a key that is not one of
        the service's own, a value of the wrong type or out of range, and an engine file that
        is missing one of the five values the service needs from it.
        """
        settings = _read_object(path, "configuration")
        engine = _read_object(engine_path, "engine configuration")
        config = cls()
        for key, value in settings.items():
            if key not in _SETTINGS:
                where = ""
                if key in _ENGINE_KEYS or key in _ENGINE_KEYS.values():
                    where = f"; the engine's values are read from {engine_path}"
                raise ConfigError(f"{path}: unknown key {key!r}{where}")
            config._set(path, key, value)
        for attribute, engine_key in _ENGINE_KEYS.items():
            if engine_key not in engine:
                raise ConfigError(f"{engine_path}: missing key {engine_key!r}")
            value = engine[engine_key]
            if attribute == "engine_port":
                value = _as_int(engine_path, engine_key, value, 1, 65535)
            elif not isinstance(value, str) or not value:
                raise ConfigError(f"{engine_path}: {engine_key} must be a non-empty string")
            setattr(config, attribute, value)
        return config

    def token(self):
        """The engine's shared secret, trimmed.

        The service uses the engine's token rather than keeping one of its own (Security in
        docs/pedal-service.md): one secret for one appliance, one credential for ljoss to
        store. systemd hands the service a readable copy through
        `LoadCredential=token:/etc/namchain/token` — that file is root's, 0600, and the service
        runs unprivileged, so without the copy it could never read it. Prefer the credential
        when it is there (the unit's case) and fall back to the file (root, and the tests).
        Read on every call, so a restart after a rotation picks up the new one.
        """
        directory = os.environ.get("CREDENTIALS_DIRECTORY")
        if directory:
            credential = os.path.join(directory, "token")
            if os.path.exists(credential):
                try:
                    with open(credential, encoding="utf-8") as f:
                        return f.read().strip()
                except (OSError, ValueError) as e:
                    raise ConfigError(
                        f"cannot read the token credential {credential}: {_why(e)}"
                    ) from e
        try:
            with open(self.engine_token_file, encoding="utf-8") as f:
                return f.read().strip()
        except (OSError, ValueError) as e:
            # ValueError covers a file that is not UTF-8: a corrupt token, not a crash.
            raise ConfigError(
                f"cannot read the token file {self.engine_token_file}: {_why(e)}"
            ) from e

    def _set(self, path, key, value):
        """One pedald.json value, checked against the type and range the key has."""
        if _SETTINGS[key] is int:
            low, high = _INT_RANGES[key]
            value = _as_int(path, key, value, low, high)
        elif not isinstance(value, str) or not value:
            raise ConfigError(f"{path}: {key} must be a non-empty string")
        setattr(self, key, value)


def _read_object(path, what):
    """The JSON object in `path`, or ConfigError saying why it could not be used."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except OSError as e:
        raise ConfigError(f"cannot read {what} {path}: {_why(e)}") from e
    except ValueError as e:
        # json.JSONDecodeError, and the UnicodeDecodeError a file that is not text gives.
        raise ConfigError(f"{path} is not valid JSON: {e}") from e
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: expected a JSON object, found {type(data).__name__}")
    return data


def _why(error):
    """An OSError's short reason, or the error itself for the kinds that have none."""
    return getattr(error, "strerror", None) or str(error)


def _as_int(path, key, value, low, high):
    """A whole number in range. JSON's true is not 1: a bool here is a typo, not a number."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise ConfigError(f"{path}: {key} must be a whole number, not {value!r}")
    if value < low or (high is not None and value > high):
        raise ConfigError(f"{path}: {key} is out of range: {value!r}")
    return value
