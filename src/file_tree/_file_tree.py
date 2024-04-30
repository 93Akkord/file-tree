#!/usr/bin/env python
# -*- coding: utf-8 -*-

'''file-tree.py: ...'''

from __future__ import annotations

import copy
import ctypes
import datetime
import faulthandler
import math
import os
import re
import signal
import stat
import sys

from argparse import Namespace
from functools import cached_property
from typing import Any, Callable, Dict, Generator, Iterator, List, Tuple, Type, TypeVar, Union

from _collections_abc import dict_items, dict_keys, dict_values


__all__ = [
    'File',
    'Folder',
    'FileTreeMaker',
    'print_file_tree',
]

faulthandler.enable()


__author__ = 'michaelcbarros@gmail.com'


getcwd = os.getcwd if hasattr(os, 'getcwd') else os.getcwd

sys.setrecursionlimit(1_000_000)


# region Main Code

T = TypeVar('T')


# region Icons


class Icons:
    FOLDER = b'\xf0\x9f\x93\x81'.decode('utf-8')
    OPEN_FOLDER = b'\xf0\x9f\x93\x82'.decode('utf-8')
    FILE = b'\xf0\x9f\x93\x84'.decode('utf-8')
    LINK = b'\xf0\x9f\x94\x97'.decode('utf-8')


# endregion Icons

# region utils.py


def bytes_2_human_readable(number_of_bytes: int | float, si=False, decimals=1) -> str:
    thresh = 1000 if si else 1024

    if math.fabs(number_of_bytes) < thresh:
        return str(number_of_bytes) + ' B'

    units = ['kB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB'] if si else ['KiB', 'MiB', 'GiB', 'TiB', 'PiB', 'EiB', 'ZiB', 'YiB']
    u = -1

    while True:
        number_of_bytes = number_of_bytes / thresh

        u += 1

        if not (math.fabs(number_of_bytes) >= thresh and u < len(units) - 1):
            break

    return f'{number_of_bytes:.{decimals}f}' + ' ' + units[u]


colors_dict = {
    # blue
    'directory': '01;34'
}


def create_colored_str(string: str, color_file_type: str | None = None) -> str:
    if color_file_type is None:
        return string

    color = colors_dict.get(color_file_type.lower())

    return f'\033[{color}m{string}\033[0m'


def create_file_link_str(path: str, name: str, color_file_type: str | None = None) -> str:
    if color_file_type is None:
        output = f'\033]8;;file://{path}\033\\{name}\033]8;;\033\\'
    else:
        color = colors_dict.get(color_file_type.lower())

        output = f'\033[{color}m\033]8;;file://{path}\a{name}\033]8;;\a\033[0m'

    return output


error_files = []


if os.name == 'nt':
    from ctypes import create_unicode_buffer, windll, wintypes
    from ctypes.wintypes import DWORD, LPCWSTR, LPWSTR

    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
    ERROR_FILE_NOT_FOUND = 2
    ERROR_NO_MORE_FILES = 18
    FILE_ATTRIBUTE_DIRECTORY = 16
    FILE_ATTRIBUTE_READONLY = 1
    SECONDS_BETWEEN_EPOCHS = 11644473600  # seconds between 1601-01-01 and 1970-01-01

    kernel32 = ctypes.windll.kernel32

    _FindFirstFile = kernel32.FindFirstFileW
    _FindFirstFile.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.WIN32_FIND_DATAW)]
    _FindFirstFile.restype = wintypes.HANDLE

    _FindNextFile = kernel32.FindNextFileW
    _FindNextFile.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.WIN32_FIND_DATAW)]
    _FindNextFile.restype = wintypes.BOOL

    _FindClose = kernel32.FindClose
    _FindClose.argtypes = [wintypes.HANDLE]
    _FindClose.restype = wintypes.BOOL

    def _attributes_to_mode(attributes: int):
        """Convert Win32 dwFileAttributes to st_mode. Taken from CPython's
        Modules/posixmodule.c.
        """

        mode = 0

        if attributes & FILE_ATTRIBUTE_DIRECTORY:
            mode |= stat.S_IFDIR | 0o111
        else:
            mode |= stat.S_IFREG
        if attributes & FILE_ATTRIBUTE_READONLY:
            mode |= 0o444
        else:
            mode |= 0o666

        return mode

    def _filetime_to_time(filetime: Any) -> int:
        total = filetime.dwHighDateTime << 32 | filetime.dwLowDateTime

        return total / 10000000.0 - SECONDS_BETWEEN_EPOCHS

    def find_data_to_stat(data: Any) -> os.stat_result:
        st_mode = _attributes_to_mode(data.dwFileAttributes)
        st_ino = 0
        st_dev = 0
        st_nlink = 0
        st_uid = 0
        st_gid = 0
        st_size = data.nFileSizeHigh << 32 | data.nFileSizeLow
        st_atime = _filetime_to_time(data.ftLastAccessTime)
        st_mtime = _filetime_to_time(data.ftLastWriteTime)
        st_ctime = _filetime_to_time(data.ftCreationTime)

        st = os.stat_result((st_mode, st_ino, st_dev, st_nlink, st_uid, st_gid, st_size, st_atime, st_mtime, st_ctime))

        return st

    def get_short_path_name(long_name: str) -> str:
        """
        Gets the short path name of a given long path.

        http://stackoverflow.com/a/23598461/200291

        :param str long_name: long path name
        :return str: short path name
        """

        _GetShortPathNameW = windll.kernel32.GetShortPathNameW
        _GetShortPathNameW.argtypes = [LPCWSTR, LPWSTR, DWORD]
        _GetShortPathNameW.restype = DWORD

        output_buf_size = 0

        while True:
            output_buf = create_unicode_buffer(output_buf_size)
            needed = _GetShortPathNameW(long_name, output_buf, output_buf_size)

            if output_buf_size >= needed:
                return output_buf.value
            else:
                output_buf_size = needed

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

    def listdir_stat(dirname='.', glob: str | None = None) -> Generator[Tuple[str, os.stat_result], Any, None]:
        dirname = os.path.abspath(dirname)
        dirname = get_short_path_name(dirname) if len(dirname) >= 256 else dirname

        filename = os.path.join(dirname, glob or '*')

        data = wintypes.WIN32_FIND_DATAW()
        data_p = ctypes.byref(data)

        handle = _FindFirstFile(filename, data_p)

        if handle == INVALID_HANDLE_VALUE:
            error = ctypes.GetLastError()

            if error == ERROR_FILE_NOT_FOUND:
                return

            error = ctypes.WinError()

            error_files.append({
                'filename': filename,
                'error': str(error)
            })

            raise error
        try:
            while True:
                if data.cFileName not in ('.', '..'):
                    st = find_data_to_stat(data)
                    is_symlink = stat.S_ISLNK(st.st_mode)

                    # yield (data.cFileName, st, is_symlink)
                    yield (data.cFileName, st)

                success = _FindNextFile(handle, data_p)

                if not success:
                    error = ctypes.GetLastError()

                    if error == ERROR_NO_MORE_FILES:
                        break

                    raise ctypes.WinError()
        finally:
            if not _FindClose(handle):

                raise ctypes.WinError()

# Linux/posix -- this is only half-tested and doesn't work at the moment, but
# leaving here for future use
else:
    import ctypes
    import ctypes.util

    class DIR(ctypes.Structure):
        pass

    DIR_p = ctypes.POINTER(DIR)

    class dirent(ctypes.Structure):
        _fields_ = (
            ('d_ino', ctypes.c_long),
            ('d_off', ctypes.c_long),
            ('d_reclen', ctypes.c_ushort),
            ('d_type', ctypes.c_byte),
            ('d_name', ctypes.c_char * 256)
        )

    dirent_p = ctypes.POINTER(dirent)

    _libc = ctypes.CDLL(ctypes.util.find_library('c'))
    _opendir = _libc.opendir
    _opendir.argtypes = [ctypes.c_char_p]
    _opendir.restype = DIR_p

    _readdir = _libc.readdir
    _readdir.argtypes = [DIR_p]
    _readdir.restype = dirent_p

    _closedir = _libc.closedir
    _closedir.argtypes = [DIR_p]
    _closedir.restype = ctypes.c_int

    DT_DIR = 4

    def find_data_to_stat(data: Any) -> os.stat_result:
        if data == DT_DIR:
            st_mode = stat.S_IFDIR | 0o111
        else:
            st_mode = stat.S_IFREG

        st_ino = 0
        st_dev = 0
        st_nlink = 0
        st_uid = 0
        st_gid = 0
        st_size = 0
        st_atime = None
        st_mtime = None
        st_ctime = None

        st = os.stat_result((st_mode, st_ino, st_dev, st_nlink, st_uid, st_gid, st_size, st_atime, st_mtime, st_ctime))  # type: ignore

        return st

    def listdir_stat(dirname=b'.', glob: str | None = None) -> Generator[Tuple[str, os.stat_result], Any, None]:
        dir_p = _opendir(dirname)

        try:
            while True:
                p = _readdir(dir_p)

                if not p:
                    break

                name: str = p.contents.d_name

                if name not in (b'.', b'..'):
                    st = find_data_to_stat(p.contents.d_type)

                    yield (name, st)
        finally:
            _closedir(dir_p)


# endregion utils.py


def get_obj_index(children: List[File | Folder], item_to_find: File | Folder) -> int:
    for i, item in enumerate(children):
        if item.path == item_to_find.path:
            return i
    else:
        return -1


class File(dict):
    def __init__(self, path: str | bytes, parent: 'Folder' | None, stat_obj: os.stat_result) -> None:
        self.path = path
        self.name = os.path.basename(self.path)
        self.type = type(self).__name__
        self.parent = parent
        self.stat_obj = stat_obj

    @property
    def size(self) -> int:
        return self.stat_obj.st_size

    @size.setter
    def size(self, value: int):
        pass

    @cached_property
    def key_path(self) -> List[int]:
        key_path = []

        temp_self = self

        while temp_self.parent is not None:
            key_path.append(temp_self.index)

            temp_self = temp_self.parent

        return list(reversed(key_path))

    @cached_property
    def index(self):
        if self.parent is not None:
            for i, item in enumerate(self.parent.children):
                if item.path == self.path:
                    return i

        return -1

    def remove(self):
        self.parent.children.pop(self.index)

        self.parent = None

    def __setitem__(self, key: Any, item: Any) -> None:
        self.__dict__[key] = item

    def __getitem__(self, key: Any) -> Any:
        return self.__dict__[key]

    def __repr__(self) -> str:
        return repr(self.__dict__)

    def __len__(self) -> int:
        return len(self.__dict__)

    def __delitem__(self, key: Any) -> None:
        del self.__dict__[key]

    def clear(self) -> None:
        return self.__dict__.clear()

    def copy(self: T) -> T:
        return copy.deepcopy(self)

    def has_key(self, k: Any) -> bool:
        return k in self.__dict__

    def update(self, *args: Any, **kwargs: Any) -> None:
        return self.__dict__.update(*args, **kwargs)

    def keys(self) -> dict_keys[str, Any]:
        return self.__dict__.keys()

    def values(self) -> dict_values[str, Any]:
        return self.__dict__.values()

    def items(self) -> dict_items[str, Any]:
        return self.__dict__.items()

    def pop(self, *args: Any) -> Any:
        return self.__dict__.pop(*args)

    def __cmp__(self, dict_: Dict[Any, Any]) -> Any:
        return self.__cmp__(self.__dict__, dict_)  # type: ignore

    def __contains__(self, item: Any) -> bool:
        return item in self.__dict__

    def __iter__(self) -> Iterator[Any]:
        return iter(self.__dict__)

    def __unicode__(self) -> str:
        return str(repr(self.__dict__))


class Folder(File):
    def __init__(self, path: str | bytes, parent: 'Folder' | None, stat_obj: os.stat_result, is_root: bool = False) -> None:
        super(Folder, self).__init__(path, parent, stat_obj)

        self.children: List[File | Folder] = []
        self.is_root = is_root

    @property
    def size(self) -> int:
        file_sizes: List[int] = []
        first_run = True

        def cb(item: File | Folder, level: int, is_last: bool, is_mid_child: bool) -> File | Folder:
            if type(item) == File:
                file_sizes.append(item.size)

            return item

        while first_run:
            first_run = False

            self.walk(cb)

        return sum(file_sizes)

    @size.setter
    def size(self, value: int):
        pass

    @property
    def nested_child_count(self) -> Tuple[int, int]:
        queue: List[Folder] = [self]
        folder_count = 0
        file_count = 0

        while queue:
            current_folder: Folder = queue.pop(0)

            for child in current_folder.children:
                if isinstance(child, Folder):
                    folder_count += 1
                    queue.append(child)
                elif isinstance(child, File):
                    file_count += 1

        return folder_count, file_count

    @nested_child_count.setter
    def nested_child_count(self, value: Tuple[int, int]):
        pass

    def walk_create_output_str(self, callback: Callable[[Union[File, Folder], int, bool, bool, str], None], level: int = 0, prefix: str = '', remove_pipe: bool = False) -> None:
        if self.is_root:
            callback(self, level, False, False, prefix)

        for idx, child in enumerate(self.children):
            is_last = idx == len(self.children) - 1
            is_mid_child = child.type == 'Folder' and len(self.children) > 1 and idx != len(self.children) - 1

            if isinstance(child, Folder):
                if is_mid_child:
                    tmp_prefix = prefix + ('    ' if remove_pipe else '┃   ')
                else:
                    tmp_prefix = prefix + '     '

                callback(child, level + 1, is_last, is_mid_child, prefix)

                child.walk_create_output_str(callback=callback,
                                             level=level + 1,
                                             prefix=tmp_prefix,
                                             remove_pipe=remove_pipe)
            else:
                callback(child, level, is_last, is_mid_child, prefix)

    def walk(self, callback: Callable[[File | Folder, int, bool, bool], File | Folder | Any], level: int = 0) -> None:
        if self.is_root:
            callback(self, level, False, False)

        for idx, child in enumerate(self.children):
            is_last = idx == len(self.children) - 1
            is_mid_child = isinstance(child, Folder) and len(self.children) > 1 and idx != len(self.children) - 1

            if isinstance(child, Folder):
                self.children[idx] = callback(child, level + 1, is_last, is_mid_child)

                child.walk(callback=callback, level=level + 1)
            else:
                self.children[idx] = callback(child, level, is_last, is_mid_child)


class FileTreeMaker(object):
    def __init__(self,
                 root: str | bytes = '.',
                 max_level: int = -1,
                 remove_pipe: bool = False,
                 exclude_folder: List[str] | List[bytes] = [],
                 exclude_name: List[str] | List[bytes] = [],
                 exclude_regex: List[str] | List[bytes] = [],
                 include_regex: List[str] | List[bytes] = [],
                 size_limit: int = -1,
                 exclude_empty_files: bool = False,
                 later_than_date: str = None,
                 links: bool = False,
                 show_size: bool = False,
                 show_counts: bool = False) -> None:
        global error_files

        error_files = []

        self.root = os.path.abspath(root)
        self.exclude_folder = exclude_folder
        self.exclude_name = exclude_name
        self.exclude_regex = [re.compile(str(p)) for p in exclude_regex]
        self.include_regex = [re.compile(str(p)) for p in include_regex]
        self.max_level = max_level
        self.remove_pipe = remove_pipe
        self.size_limit = size_limit
        self.exclude_empty_files = exclude_empty_files
        self.later_than_date = later_than_date
        self.links = links
        self.show_size = show_size
        self.show_counts = show_counts

        self.root_dir_tree = self.make_dir_tree()

        if len(self.include_regex) > 0:
            self.remove_empty_dirs()

    def _recurse(self, parent_path: str | bytes, file_list: List[Tuple[str | bytes, os.stat_result]], level: int, dir_tree: Folder) -> None:
        if len(file_list) == 0 or (self.max_level != -1 and self.max_level <= level):
            return
        else:
            file_list.sort(key=lambda f: not stat.S_ISDIR(f[1].st_mode))

            for idx, file_obj in enumerate(file_list):
                try:
                    sub_path = file_obj[0]
                    stat_obj = file_obj[1]
                    full_path = os.path.join(parent_path, sub_path)  # type: ignore
                    fize_size = -1

                    if self.later_than_date is not None and not stat.S_ISDIR(stat_obj.st_mode) and datetime.datetime.fromtimestamp(os.path.getmtime(full_path)) < datetime.datetime.strptime(self.later_than_date, '%Y-%m-%d'):
                        continue

                    if self.size_limit > -1 or self.exclude_empty_files:
                        fize_size = 0 if stat.S_ISDIR(stat_obj.st_mode) else stat_obj.st_size if stat_obj.st_size is not None else os.path.getsize(full_path)

                    if self.size_limit > -1 and fize_size > self.size_limit:
                        continue

                    if self.exclude_empty_files and fize_size == 0:
                        continue

                    if any(exclude_name in sub_path for exclude_name in self.exclude_name):  # type: ignore
                        continue

                    if not stat.S_ISDIR(stat_obj.st_mode) and (len(self.include_regex) > 0 and all([p.search(full_path) is None for p in self.include_regex])):
                        continue

                    if any([p.search(full_path) is not None for p in self.exclude_regex]):
                        continue

                    if stat.S_ISDIR(stat_obj.st_mode) and sub_path not in self.exclude_folder:
                        sub_folder = Folder(full_path, parent=dir_tree, stat_obj=stat_obj)

                        dir_tree.children.append(sub_folder)

                        try:
                            self._recurse(parent_path=full_path,
                                          file_list=list(listdir_stat(full_path)),
                                          level=level + 1,
                                          dir_tree=sub_folder)
                        except FileNotFoundError as fnfe:
                            print('full_path:', full_path)
                            print('\n' * 5)
                            print(fnfe)
                            sys.exit()

                            raise fnfe
                        except RecursionError as rex:
                            print('full_path:', full_path)
                            print('\n' * 5)
                            print(rex)
                            # sys.exit()

                            raise rex
                    elif not stat.S_ISDIR(stat_obj.st_mode):
                        file = File(full_path, parent=dir_tree, stat_obj=stat_obj)

                        dir_tree.children.append(file)
                except OSError as ex:
                    if '[Errno 13] Permission denied' not in str(ex) and '[WinError 5] Access is denied' not in str(ex):
                        raise ex

    def make_dir_tree(self) -> Folder:
        dir_tree = Folder(self.root, None, os.stat(self.root), True)

        self._recurse(parent_path=self.root,
                      file_list=list(listdir_stat(self.root)),  # type: ignore
                      level=0,
                      dir_tree=dir_tree)

        return dir_tree

    def get_item_by_key_path(self, key_path: List[int]) -> File | Folder:
        temp = self.root_dir_tree

        for i in key_path:
            if isinstance(temp, Folder):
                temp = temp.children[i]
            else:
                raise ValueError('Invalid key path')

        return temp

    def to_dict(self) -> Dict[str, str | bool | Dict[str, Any]]:
        def cb(item: File | Folder, level: int, is_last: bool, is_mid_child: bool) -> Dict[str, Any]:
            return dict(item)

        dir_tree_copy = self.root_dir_tree.copy()

        dir_tree_copy.walk(cb)

        return dict(dir_tree_copy)

    def remove_empty_dirs(self):
        to_be_removed: List[Folder] = []
        first_run = True

        def cb(item: File | Folder, level: int, is_last: bool, is_mid_child: bool) -> File | Folder:
            if isinstance(item, Folder) and len(item.children) == 0:
                to_be_removed.append(item)

            return item

        while first_run or len(to_be_removed) > 0:
            first_run = False

            to_be_removed: List[Folder] = []

            self.root_dir_tree.walk(cb)

            for item in to_be_removed:
                item.remove()

    def to_tree_str(self) -> str:
        lines = []

        def cb(item: File | Folder, level: int, is_last: bool, is_mid_child: bool, prefix: str) -> None:
            idc = '┗━' if is_last else '┣━'

            idc = '' if type(item) == Folder and item.is_root else idc

            icon = f'{Icons.FOLDER if type(item) == Folder else Icons.FILE}'

            color_file_type: str | None = None

            if type(item) == Folder:
                color_file_type = 'directory'

            item_name: str = item.name.decode('utf-8') if isinstance(item.name, bytes) else item.name  # type: ignore
            item_path: str = item.path.decode('utf-8') if isinstance(item.path, bytes) else item.path  # type: ignore

            if self.links:
                name = '{name}'.format(name=create_file_link_str(item_path, item_name, color_file_type)) if item.type == 'Folder' else create_file_link_str(item_path, item_name, color_file_type)
            else:
                name = '{name}'.format(name=create_colored_str(item_name, color_file_type)) if item.type == 'Folder' else create_colored_str(item_name, color_file_type)

            size_count_str = get_size_count_str(self, item)

            output = '{prefix}{idc}{space}{icon} {name}{size_count_str}'.format(prefix=prefix,
                                                                                idc=idc,
                                                                                space='' if type(item) == Folder and item.is_root else ' ',
                                                                                icon=icon,
                                                                                name=name,
                                                                                size_count_str=size_count_str)

            lines.append(output)

        self.root_dir_tree.walk_create_output_str(cb, remove_pipe=self.remove_pipe)

        output_str = '\n'.join(lines)

        return output_str

    def to_flat_str(self) -> str:
        lines = []

        def cb(item: Union[File, Folder], level: int, is_last: bool, is_mid_child: bool, prefix: str) -> None:
            item_path: str = item.path.decode('utf-8') if isinstance(item.path, bytes) else item.path  # type: ignore

            if self.links:
                name = create_file_link_str(item_path, item_path)
            else:
                name = item.path

            size_count_str = get_size_count_str(self, item)

            output = '{name}{size_count_str}'.format(name=name, size_count_str=size_count_str)

            lines.append(output)

        self.root_dir_tree.walk_create_output_str(cb, remove_pipe=self.remove_pipe)

        output_str = '\n'.join(lines)

        return output_str


def get_size_count_str(file_tree_maker: FileTreeMaker, item: File | Folder):
    size_count = []

    if file_tree_maker.show_size:
        size_count.append(bytes_2_human_readable(item.size))

    if file_tree_maker.show_counts and type(item) == Folder:
        folders = item.nested_child_count[0]
        files = item.nested_child_count[1]

        size_count.append(f'{files} Files, {folders} Folders, {folders + files} Total')

    size_count_str = f" ({' -- '.join(size_count)})" if file_tree_maker.show_size or file_tree_maker.show_counts else ''

    return size_count_str


def sigint_handler(signum: int, frame: Any):
    sys.exit(0)


signal.signal(signal.SIGINT, sigint_handler)


def run() -> None:
    res = parse_args()

    print_file_tree(**res.__dict__)


def print_file_tree(root: str | bytes = '.',
                    output: str = None,
                    max_level: int = -1,
                    flat: bool = False,
                    remove_pipe: bool = False,
                    exclude_folder: List[str] | List[bytes] = [],
                    exclude_name: List[str] | List[bytes] = [],
                    exclude_regex: List[str] | List[bytes] = [],
                    include_regex: List[str] | List[bytes] = [],
                    size_limit: int = -1,
                    exclude_empty_files: bool = False,
                    later_than_date: str = None,
                    links: bool = False,
                    show_size: bool = False,
                    show_counts: bool = False,
                    errors: bool = False) -> None:
    exclude_folder = list(exclude_folder)
    exclude_name = list(exclude_name)
    exclude_regex = list(exclude_regex)
    include_regex = list(include_regex)

    root = os.path.abspath(root)

    file_tree_maker = FileTreeMaker(root=root.encode('utf-8') if os.name == 'posix' else root,
                                    max_level=max_level,
                                    remove_pipe=remove_pipe,
                                    exclude_folder=exclude_folder,
                                    exclude_name=exclude_name,
                                    exclude_regex=exclude_regex,
                                    include_regex=include_regex,
                                    size_limit=size_limit,
                                    exclude_empty_files=exclude_empty_files,
                                    later_than_date=later_than_date,
                                    links=links,
                                    show_size=show_size,
                                    show_counts=show_counts)

    output_str = file_tree_maker.to_flat_str() if flat else file_tree_maker.to_tree_str()

    if output is not None:
        with open(output, 'w') as f_out:
            f_out.write(output_str)

    if links:
        name = 'root: {root}'.format(root=f"\033]8;;file://{root}\033\\{root}\033]8;;\033\\")
    else:
        name = 'root: {root}'.format(root=root)

    size_count_str = get_size_count_str(file_tree_maker, file_tree_maker.root_dir_tree)

    root_str = '{name}{size_count_str}'.format(name=name, size_count_str=size_count_str)

    output_str = output_str.replace('�', '')

    print(root_str)
    print(output_str)

    if errors and len(error_files) > 0:
        print('')
        print('Error Files:')

        for error_file in error_files:
            print('  {filename}: {error}'.format(filename=error_file['filename'], error=error_file['error']))


# endregion Main Code


def remove_surrounding_quotes(string: str) -> str:
    if (string.startswith("'") and string.endswith("'")) or (string.startswith('"') and string.endswith('"')):
        return string[1:-1]
    else:
        return string


def parse_args() -> Namespace:
    import argparse

    from file_tree.version import __version__

    class ExtendAction(argparse.Action):
        def __call__(self, parser, namespace, values, option_string=None):
            items = getattr(namespace, self.dest) or []

            if values is not None:
                items.extend(values)

            setattr(namespace, self.dest, items)

    # Create a parser object
    parser = argparse.ArgumentParser(description='Command Line Parser Example')

    parser.register('action', 'extend', ExtendAction)

    # Add command-line arguments
    parser.add_argument('-v', '--version', action='version', version=__version__, help='Display version')
    parser.add_argument('-r', '--root', default='.', type=str, help='Root path to git repository')
    parser.add_argument('-o', '--output', default=None, type=str, help='Output to filepath provided')
    parser.add_argument('-m', '--max-level', default=-1, type=int, help='Max level')
    parser.add_argument('-f', '--flat', default=False, action='store_true', help='Output dir in flat format')
    parser.add_argument('-rp', '--remove-pipe', default=False, action='store_true', help='Remove pipe character from output string')
    parser.add_argument('-xf', '--exclude-folder', default=[], action='extend', nargs='+', help='Exclude folders')
    parser.add_argument('-xn', '--exclude-name', default=[], action='extend', nargs='+', help='Exclude names')
    parser.add_argument('-xr', '--exclude-regex', default=[], action='extend', nargs='+', help='Exclude path by regex pattern')
    parser.add_argument('-ir', '--include-regex', default=[], action='extend', nargs='+', help='Include path by regex pattern')
    parser.add_argument('-sl', '--size-limit', default=-1, type=int, help='Exclude files larger than size limit')
    parser.add_argument('-xef', '--exclude-empty-files', default=False, action='store_true', help='Exclude empty files')
    parser.add_argument('-ltd', '--later-than-date', default=None, type=str, help='Include files later than date.  Must be in yyyy-MM-dd format')
    parser.add_argument('-l', '--links', default=False, action='store_true', help='Show hyperlinks in terminal')
    parser.add_argument('-s', '--show-size', default=False, action='store_true', help='Show size of files/folders in terminal')
    parser.add_argument('-c', '--show-counts', default=False, action='store_true', help='Show counts of files/folders in terminal')
    parser.add_argument('-e', '--errors', default=False, action='store_true', help='Display which files had errors')

    # Parse the command-line arguments
    args = parser.parse_args()

    args = update_parsed_args(args)

    return args


def update_parsed_args(args: Namespace) -> Namespace:
    # Iterate over the parsed arguments
    for arg, value in vars(args).items():
        if isinstance(value, str):
            value = remove_surrounding_quotes(value)

        elif isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, str):
                    value[i] = remove_surrounding_quotes(item)

    return args


if __name__ == '__main__':
    # args = [
    #     '-r',
    #     'C:\\Users\\mbarros\\development\\big_data\\entity_resolution\\spark-node-dev\\scripts\\python\\tools',
    #     '-s',
    #     '-c',
    # ]

    # sys.argv = sys.argv + args

    run()
