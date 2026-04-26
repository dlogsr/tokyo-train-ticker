"""
ctypes wrapper around tslib (libts.so).
Returns pre-calibrated (x, y, pressure) samples — no axis math in the app.
Calibration data lives in /etc/pointercal; write it once with:
    sudo bash pi/setup_touch.sh
"""
import ctypes


class _Timeval(ctypes.Structure):
    # c_long is pointer-width: 4 bytes on 32-bit Pi Zero, 8 on 64-bit Pi 4
    _fields_ = [("tv_sec", ctypes.c_long), ("tv_usec", ctypes.c_long)]


class TsSample(ctypes.Structure):
    _fields_ = [
        ("x",        ctypes.c_int),
        ("y",        ctypes.c_int),
        ("pressure", ctypes.c_uint),
        ("tv",       _Timeval),
    ]


_lib = None


def _load():
    global _lib
    if _lib is not None:
        return _lib
    for name in ("libts.so.0", "libts.so"):
        try:
            lib = ctypes.CDLL(name, use_errno=True)
            lib.ts_open.restype   = ctypes.c_void_p
            lib.ts_open.argtypes  = [ctypes.c_char_p, ctypes.c_int]
            lib.ts_config.restype  = ctypes.c_int
            lib.ts_config.argtypes = [ctypes.c_void_p]
            lib.ts_read.restype   = ctypes.c_int
            lib.ts_read.argtypes  = [ctypes.c_void_p, ctypes.POINTER(TsSample), ctypes.c_int]
            lib.ts_close.argtypes = [ctypes.c_void_p]
            _lib = lib
            return _lib
        except OSError:
            continue
    return None


def open_ts(dev_path: str):
    """Open and configure tslib for dev_path. Returns opaque handle or None."""
    lib = _load()
    if lib is None:
        return None
    handle = lib.ts_open(dev_path.encode(), 0)   # 0 = blocking
    if not handle:
        return None
    if lib.ts_config(handle) != 0:
        lib.ts_close(handle)
        return None
    return handle


def read_ts(handle):
    """Block until one sample arrives. Returns (x, y, pressure) or None."""
    lib = _load()
    if lib is None:
        return None
    sample = TsSample()
    ret = lib.ts_read(handle, ctypes.byref(sample), 1)
    if ret == 1:
        return sample.x, sample.y, sample.pressure
    return None


def close_ts(handle):
    lib = _load()
    if lib and handle:
        lib.ts_close(handle)
