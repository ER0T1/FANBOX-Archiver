import json
import sys


def self_check() -> int:
    """Offline checks of the frozen runtime, run by the build and smoke-test scripts.

    The desktop app needs HTTPS for every FANBOX request. A sidecar frozen from some
    non-official Python builds cannot even create an SSL context (``FileNotFoundError``
    from ``ssl.SSLContext()``), so the build refuses to ship one that fails here.
    """
    results: dict[str, str] = {}
    try:
        import ssl

        import certifi
        import httpx

        ssl.create_default_context(cafile=certifi.where())
        httpx.Client().close()
        results["tls"] = ssl.OPENSSL_VERSION
    except Exception as exc:  # noqa: BLE001 - report any failure to the build script
        results["error"] = f"{type(exc).__name__}: {exc}"
    print(json.dumps(results))
    return 0 if "error" not in results else 1


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-check"]:
        raise SystemExit(self_check())
    from fanbox_archiver.cli import app

    app()
