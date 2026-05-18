"""PR-mode print() + ANSI log helpers.

Previously these lived in src/modes/eva/websocket_handler.py and were
imported across both modes. EVA migrated to Python `logging` with a
colored Formatter (see src/modes/eva/log_format.py); PR still uses
the print-based helpers below. If PR migrates to `logging`, delete
this file.
"""


class Colors:
    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"


def log_info(message: str) -> None:
    print(f"{Colors.OKBLUE}[INFO]{Colors.ENDC} {message}")


def log_success(message: str) -> None:
    print(f"{Colors.OKGREEN}[SUCCESS]{Colors.ENDC} {message}")


def log_warning(message: str) -> None:
    print(f"{Colors.WARNING}[WARNING]{Colors.ENDC} {message}")


def log_error(message: str) -> None:
    print(f"{Colors.FAIL}[ERROR]{Colors.ENDC} {message}")


def log_response(message: str) -> None:
    print(f"{Colors.HEADER}[RESPONSE]{Colors.ENDC} {Colors.HEADER}{message}{Colors.ENDC}")
