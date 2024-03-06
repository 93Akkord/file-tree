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

import six


def get_threads():
    """ Returns the number of available threads on a posix/win based system """

    if sys.platform == 'win32':
        return int(os.environ['NUMBER_OF_PROCESSORS'])
    else:
        return int(os.popen('grep -c cores /proc/cpuinfo').read())


class FixedThreadPoolExecutor(object):
    """
    Executes tasks in a fixed thread pool.

    Makes sure to gather all returned results and thrown exceptions in one place, in order of task
    submission.

    Example::

        def sum(arg1, arg2):
            return arg1 + arg2

        executor = FixedThreadPoolExecutor(10)
        try:
            for value in range(100):
                executor.submit(sum, value, value)
            executor.drain()
        except:
            executor.close()
        executor.raise_first()
        print executor.returns

    You can also use it with the Python "with" keyword, in which case you don't need to call "close"
    explicitly::

        with FixedThreadPoolExecutor(10) as executor:
            for value in range(100):
                executor.submit(sum, value, value)
            executor.drain()
            executor.raise_first()
            print executor.returns
    """

    def __init__(self, size=get_threads(), timeout=0.1, print_exceptions=False):
        """
        :param size: Number of threads in the pool (fixed).
        :param timeout: Timeout in seconds for all blocking operations. (Defaults to none, meaning no timeout)
        :param print_exceptions: Set to true in order to print exceptions from tasks. (Defaults to false)
        """

        self.size = size
        self.timeout = timeout
        self.print_exceptions = print_exceptions
        self.task_count = 0

        self._returns = {}
        self._exceptions = {}
        self._id_creator = itertools.count()
        self._lock = Lock()  # for console output

        self._tasks = Queue()
        self._run_event = Event()

        self._workers: List[ThreadedWorker] = []

        for index in range(size):
            self._workers.append(ThreadedWorker(self, index, self._tasks, self._run_event))

    def submit(self, func, *args, **kwargs):
        """
        Submit a task for execution.

        The task will be called ASAP on the next available worker thread in the pool.
        """

        self.task_count += 1

        self._tasks.put((six.next(self._id_creator), func, args, kwargs), timeout=self.timeout)

    def close(self, raise_exec=False):
        """
        Blocks until all current tasks finish execution and all worker threads are dead.

        You cannot submit tasks anymore after calling this.

        This is called automatically upon exit if you are using the "with" keyword.
        """

        self.drain()

        while self.is_alive:
            self._tasks.put(FixedThreadPoolExecutor._CYANIDE, timeout=self.timeout)

        self._workers = None  # type: ignore

    def stop(self):
        self.run_event.set()  # type: ignore

        for worker in self._workers:
            # Allow worker threads to shut down completely
            worker.join()

    def terminate(self):
        for worker in self._workers:
            worker.keyboard_interrupted = True

        self.close()

    def drain(self):
        """
        Blocks until all current tasks finish execution, but leaves the worker threads alive.
        """

        self._tasks.join()  # oddly, the API does not support a timeout parameter

    @property
    def is_alive(self):
        """
        True if any of the worker threads are alive.
        """

        for worker in self._workers:
            if worker.is_alive():
                return True

        return False

    @property
    def returns(self):
        """
        The returned values from all tasks, in order of submission.
        """

        return [self._returns[k] for k in sorted(self._returns)]

    @property
    def exceptions(self):
        """
        The raised exceptions from all tasks, in order of submission.
        """

        return [self._exceptions[k] for k in sorted(self._exceptions)]

    def raise_first(self):
        """
        If exceptions were thrown by any task, then the first one will be raised.

        This is rather arbitrary: proper handling would involve iterating all the
        exceptions. However, if you want to use the "raise" mechanism, you are
        limited to raising only one of them.
        """

        exceptions = self.exceptions

        if exceptions:
            raise exceptions[0]

    _CYANIDE = object()

    """
    Special task marker used to kill worker threads.
    """

    def _execute_next_task(self):
        try:
            task = self._tasks.get(timeout=self.timeout)

            if task == FixedThreadPoolExecutor._CYANIDE:
                # Time to die :(
                return False

            self._execute_task(*task)

            return True
        except Empty:
            pass

    def _execute_task(self, id, func, args, kwargs):
        try:
            result = func(*args, **kwargs)

            self._returns[id] = result
        except Exception as e:
            self._exceptions[id] = e

            if self.print_exceptions:
                with self._lock:
                    traceback.print_exc()

        self._tasks.task_done()

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.close()

        return False


class ThreadedWorker(Thread):
    """
    Worker thread.

    Keeps executing tasks until fed with cyanide.
    """

    def __init__(self, executor, index, tasks, run_event: Event):
        super(ThreadedWorker, self).__init__(name='FixedThreadPoolExecutor%d' % index)

        self.executor = executor
        self.tasks = tasks
        self.run_event = run_event
        self.daemon = True
        self.keyboard_interrupted = False
        self.start()

    def run(self):
        while True:
            if not self.executor._execute_next_task() or self.keyboard_interrupted or self.run_event.is_set():
                break

    def _get_my_tid(self):
        """determines this (self's) thread id

        CAREFUL: this function is executed in the context of the caller
        thread, to get the identity of the thread represented by this
        instance.
        """

        if not self.isAlive():
            raise threading.ThreadError('the thread is not active')

        # do we have it cached?
        if hasattr(self, '_thread_id'):
            return self._thread_id

        # no, look for it in the _active dict
        for tid, tobj in threading._active.items():  # type: ignore
            if tobj is self:
                self._thread_id = tid

                return tid

        # TODO: in python 2.6, there's a simpler way to do: self.ident

        raise AssertionError("could not determine the thread's id")


def in_debugger():
    return sys.gettrace() is not None


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


if __name__ == '__main__':
    pass
