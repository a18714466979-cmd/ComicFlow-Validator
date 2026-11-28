"""Handle headerless WKWebView navigation when freezing pywebview 6.2.1."""

from importlib.metadata import distribution
import sys


def patch_cocoa() -> None:
    if sys.platform != "darwin":
        raise SystemExit("The Cocoa patch applies only to macOS installer builds.")
    package = distribution("pywebview")
    if package.version != "6.2.1":
        raise SystemExit(f"Review the Cocoa patch for pywebview {package.version} before building.")
    cocoa = package.locate_file("webview/platforms/cocoa.py")
    source = cocoa.read_text(encoding="utf-8")
    # Apple declares NSURLRequest.allHTTPHeaderFields nullable. Allow the
    # initial headerless request to reach WKNavigationDelegate's decision block.
    before = "original_headers = dict(request.allHTTPHeaderFields())"
    after = "original_headers = dict(request.allHTTPHeaderFields() or {})"
    if source.count(before) != 1 or after in source:
        raise SystemExit("The expected unpatched Cocoa request handler was not found exactly once.")
    cocoa.write_text(source.replace(before, after, 1), encoding="utf-8")
    print(f"Patched nullable Cocoa request headers in pywebview {package.version}.")


if __name__ == "__main__":
    patch_cocoa()
