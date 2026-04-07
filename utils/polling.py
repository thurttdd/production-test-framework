# SPDX-License-Identifier: FSL-1.1-ALv2
# Copyright (c) 2025 Delos Data, Inc.

import time
from typing import Callable


def wait_for(condition: Callable[[], bool], timeout: float, poll_interval: float = 2.0):
    """ A polling function that evaluates a lambda expression until it returns True or until 
    the timeout is reached. Returns True if the condition is met, False otherwise.
    """
    for _ in range(int(timeout / poll_interval)):
        if condition():
            return True
        time.sleep(poll_interval)
    return False