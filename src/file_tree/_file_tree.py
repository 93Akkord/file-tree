# !/usr/bin/env python
# -*- coding: utf-8 -*-

'''file-tree.py: ...'''

from __future__ import annotations

import os
import re
import signal
import sys
from typing import Any, Callable, Dict, Iterator, List, Tuple, Union

import click
import six
from colr import color

from file_tree.utils import shorten_filename

__author__ = 'michaelcbarros@gmail.com'


class File(dict):
    def __init__(self, path):
        # type: (str) -> None

        self.path = path
        self.name = os.path.basename(self.path)
        self.type = type(self).__name__

    def __setitem__(self, key, item):
        # type: (Any, Any) -> None

        self.__dict__[key] = item

    def __getitem__(self, key):
        # type: (Any) -> Any

        return self.__dict__[key]

    def __repr__(self):
        # type: () -> str

        return repr(self.__dict__)

    def __len__(self):
        # type: () -> int

        return len(self.__dict__)

    def __delitem__(self, key):
        # type: (Any) -> None

        del self.__dict__[key]

    def clear(self):
        # type: () -> None

        return self.__dict__.clear()

    def copy(self):
        # type: () -> Dict[Any, Any]

        return self.__dict__.copy()

    def has_key(self, k):
        # type: (Any) -> bool

        return k in self.__dict__

    def update(self, *args, **kwargs):
        # type: (Any, Any) -> None

        return self.__dict__.update(*args, **kwargs)

    def keys(self):
        return self.__dict__.keys()

    def values(self):
        return self.__dict__.values()

    def items(self):
        return self.__dict__.items()

    def pop(self, *args):
        # type: (Any) -> Any

        return self.__dict__.pop(*args)

    def __cmp__(self, dict_):
        # type: (Dict[Any, Any]) -> Any

        return self.__cmp__(self.__dict__, dict_)  # type: ignore

    def __contains__(self, item):
        # type: (Any) -> bool

        return item in self.__dict__

    def __iter__(self):
        # type: (Any) -> Iterator[Any]

        return iter(self.__dict__)

    def __unicode__(self):
        # type: () -> str

        return six.text_type(repr(self.__dict__))


class Folder(File):
    def __init__(self, path: str, is_root: bool = False) -> None:
        super(Folder, self).__init__(path)

        self.children: List[Union[File, Folder]] = []
        self.is_root = is_root

    def walk(self, callback: Callable[[Union[File, Folder], int, bool, bool, str], None], level: int = 0, prefix: str = '', remove_pipe: bool = False) -> None:
        if self.is_root:
            callback(self, level, False, False, prefix)

        for idx, child in enumerate(self.children):
            is_last = idx == len(self.children) - 1
            is_mid_child = child.type == 'Folder' and len(self.children) > 1 and idx != len(self.children) - 1

            if child.type == 'Folder':
                if is_mid_child:
                    tmp_prefix = prefix + ('    ' if remove_pipe else '┃   ')
                else:
                    tmp_prefix = prefix + '     '

                callback(child, level + 1, is_last, is_mid_child, prefix)

                child.walk(callback=callback,  # type: ignore
                           level=level + 1,
                           prefix=tmp_prefix,
                           remove_pipe=remove_pipe)
            else:
                callback(child, level, is_last, is_mid_child, prefix)


class FileTreeMaker(object):
    def __init__(self, root: str, max_level: int, remove_pipe: bool, exclude_folder: List[str], exclude_name: List[str], exclude_regex: List[str]) -> None:
        self.root = root
        self.exclude_folder = exclude_folder
        self.exclude_name = exclude_name
        self.exclude_regex = [re.compile(str(p)) for p in exclude_regex]
        self.max_level = max_level
        self.remove_pipe = remove_pipe

        self.dir_tree = self.make_dir_tree()

    def _recurse(self, parent_path, file_list, level, dir_tree):
        # type: (str, List[str], int, Folder) -> None

        if len(file_list) == 0 or (self.max_level != -1 and self.max_level <= level):
            return
        else:
            file_list.sort(key=lambda f: os.path.isfile(os.path.join(parent_path, f)))

            for idx, sub_path in enumerate(file_list):
                if any(exclude_name in sub_path for exclude_name in self.exclude_name):
                    continue

                if any([p.match(sub_path) is not None for p in self.exclude_regex]):
                    continue

                full_path = os.path.join(parent_path, sub_path)

                if os.path.isdir(full_path) and sub_path not in self.exclude_folder:
                    sub_folder = Folder(full_path)

                    dir_tree.children.append(sub_folder)

                    self._recurse(parent_path=full_path,
                                  file_list=os.listdir(full_path),
                                  level=level + 1,
                                  dir_tree=sub_folder)
                elif os.path.isfile(full_path):
                    file = File(full_path)

                    dir_tree.children.append(file)

    def make_dir_tree(self):
        # type: () -> Folder

        dir_tree = Folder(self.root, True)

        self._recurse(parent_path=self.root,
                      file_list=os.listdir(self.root),
                      level=0,
                      dir_tree=dir_tree)

        return dir_tree

    def to_tree_str(self):
        # type: () -> str

        lines = []

        def cb(item: Union[File, Folder], level: int, is_last: bool, is_mid_child: bool, prefix: str) -> None:
            idc = '┗━' if is_last else '┣━'

            idc = '' if 'is_root' in item and item.is_root else idc  # type: ignore

            name = '[{name}]'.format(name=item.name) if item.type == 'Folder' else item.name

            output = '{prefix}{idc}{space}{name}'.format(prefix=prefix, idc=idc, space='' if 'is_root' in item and item.is_root else ' ', name=name)  # type: ignore

            lines.append(output)

        self.dir_tree.walk(cb, remove_pipe=self.remove_pipe)

        output_str = '\n'.join(lines)

        return output_str

    def to_flat_str(self):
        # type: () -> str

        lines = []

        def cb(item, level, is_last, is_mid_child, prefix):
            # type: (Union[File, Folder], int, bool, bool, str) -> None

            lines.append(item.path)

        self.dir_tree.walk(cb, remove_pipe=self.remove_pipe)

        output_str = '\n'.join(lines)

        return output_str


def sigint_handler(signum, frame):
    sys.exit(0)


@click.command(context_settings=dict(max_content_width=120))
@click.version_option(None, '-v', '--version')
@click.help_option('-h', '--help')
@click.option('-r', '--root', default=shorten_filename(os.getcwd()), help=f'Root path to git repository', show_default=True)
@click.option('-o', '--output', default=None, help=f'Output to filepath provided')
@click.option('-m', '--max-level', default=-1, help='Max level', show_default=True)
@click.option('-f', '--flat', default=False, is_flag=True, help='Output dir in flat format', show_default=True)
@click.option('-rp', '--remove-pipe', default=False, is_flag=True, help='Remove pipe character from output string', show_default=True)
@click.option('-xf', '--exclude-folder', default=None, help='Exclude folders')
@click.option('-xn', '--exclude-name', default=None, help='Exclude names')
@click.option('-xr', '--exclude-regex', default=None, help='Exclude path by regex pattern')
def run(root: str, output: str, max_level: int, flat: bool, remove_pipe: bool, exclude_folder: str, exclude_name: str, exclude_regex: str):  # type: ignore
    signal.signal(signal.SIGINT, sigint_handler)

    exclude_folder: List[str] = exclude_folder.split(',') if exclude_folder is not None else []
    exclude_name: List[str] = exclude_name.split(',') if exclude_name is not None else []
    exclude_regex: List[str] = exclude_regex.split(',') if exclude_regex is not None else []

    if root == '.':
        root = os.path.abspath(root)

    file_tree_maker = FileTreeMaker(root=root,
                                    max_level=max_level,
                                    remove_pipe=remove_pipe,
                                    exclude_folder=exclude_folder,
                                    exclude_name=exclude_name,
                                    exclude_regex=exclude_regex)

    output_str = file_tree_maker.to_flat_str() if flat else file_tree_maker.to_tree_str()

    if output is not None:
        with open(output, 'w') as f_out:
            f_out.write(output_str)

    print('root: {root}'.format(root=root))
    print(output_str)


if __name__ == '__main__':
    # args = [
    #     '-r',
    #     r'C:\Users\mbarros\Documents\DevProjects\Web\Tampermonkey\Palantir',
    #     '-xf',
    #     '"node_modules"'
    # ]

    # sys.argv = sys.argv + args

    run()
