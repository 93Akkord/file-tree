import itertools
import os
import sys
import threading
import traceback
from ctypes import create_unicode_buffer, windll
from ctypes.wintypes import DWORD, DWORD, LPCWSTR, LPWSTR
from queue import Empty, Queue
from threading import Event, Lock, Thread
from typing import List



def get_long_path_name(short_path: str) -> str:
    """
    Gets the long path name of a given short path.
    http://stackoverflow.com/a/23598461/200291

    :param str short_path: short path name
    :return str: long path name
    """

    _GetLongPathNameW = windll.kernel32.GetLongPathNameW
    _GetLongPathNameW.argtypes = [LPCWSTR, LPWSTR, DWORD]
    _GetLongPathNameW.restype = DWORD

    output_buf_size = 0

    while True:
        output_buf = create_unicode_buffer(output_buf_size)
        needed = _GetLongPathNameW(short_path, output_buf, output_buf_size)

        if output_buf_size >= needed:
            return output_buf.value
        else:
            output_buf_size = needed


if __name__ == '__main__':
    pass
