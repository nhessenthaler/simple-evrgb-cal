# Copyright 2026 [Nico Hessenthaler, Heilbronn University of Applied Sciences]
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Filename: operating_system.py
Author: Nico Hessenthaler
Date: 2026-06-05
Version: 1.0
Description:
    Module that provides utilities for interacting with the operating system.
License: Licensed under the Apache License, Version 2.0
Contact: nico.hessenthaler@hs-heilbronn.de
"""

from datetime import datetime
from pathlib import Path
import time

RED = "\033[31m"
GREEN = "\033[32m"
CYAN = "\033[36m"
RESET = "\033[0m"


def print_error(message: str) -> None:
    """
    Function to print an error message where only the word "ERROR" is colored red.

    Output format: "ERROR: {message} ..."

    Args:
        message (str): The error message to print.

    Returns:
        ():
    """

    print(f"{RED}ERROR{RESET}: {message} ...")

    return


def print_info(message: str) -> None:
    """
    Function to print an info message where only the word "INFO" is colored cyan.

    Output format: "INFO: {message} ..."

    Args:
        message (str): The info message to print.

    Returns:
        ():
    """

    print(f"{CYAN}INFO{RESET}: {message} ...")

    return


def print_success(message: str) -> None:
    """
    Function to print a success message where only the word "SUCCESS" is colored green.

    Output format: "SUCCESS: {message} ..."

    Args:
        message (str): The success message to print.

    Returns:
        ():
    """

    print(f"{GREEN}SUCCESS{RESET}: {message} ...")

    return


def check_file_exists(file_path: str | Path) -> bool:
    """
    Function to check if a file exists at the given path.

    Args:
        file_path (str | Path): The path to the file.

    Returns:
        exists (bool): True if the file exists, False otherwise.
    """

    if isinstance(file_path, str):
        t_path = Path(file_path)
    else:
        t_path = file_path

    t_exists = t_path.is_file()

    return t_exists


def create_directory(directory_path: str | Path, parents: bool = True, exist_ok: bool = True) -> None:
    """
    Function to create a directory at the given path if it does not already exist.

    Args:
        directory_path (str | Path): The path to the directory.
        parents (bool): Whether to create parent directories if they don't exist.
        exist_ok (bool): Whether to ignore if the directory already exists.

    Returns:
        ():
    """

    if isinstance(directory_path, str):
        t_path = Path(directory_path)
    else:
        t_path = directory_path

    t_path.mkdir(parents=parents, exist_ok=exist_ok)

    return


def generate_current_timestamp_string(timestamp_format: str = "%Y%m%d_%H%M%S") -> str:
    """
    Function that generates a string with the current timestamp in the default format "YYYYMMDD_HHMMSS".
    Other formats can be specified using the timestamp_format argument.

    Args:
        timestamp_format (str): The format string for the timestamp.

    Returns:
        timestamp_string (str): The generated timestamp string.
    """

    t_timestamp_string = datetime.now().strftime(timestamp_format)

    return t_timestamp_string


class Timer:
    """Generic timer class for managing intervals and remaining time."""

    def __init__(self, interval: float) -> None:
        self.__interval = interval
        self.__last_time = time.time()

    # ##### GETTER #####
    @property
    def interval(self) -> float:
        """
        Getter for the attribute '__interval'.

        Args:
            ():

        Returns:
            interval (float): The attribute '__interval'.
        """

        return self.__interval

    @property
    def last_time(self) -> float:
        """
        Getter for the attribute '__last_time'.

        Args:
            ():

        Returns:
            last_time (float): The attribute '__last_time'.
        """

        return self.__last_time

    # ##### SETTER #####
    @last_time.setter
    def last_time(self, value: float) -> None:
        """
        Setter for the attribute '__last_time'.

        Args:
            value (float): The new value for the attribute '__last_time'.

        Returns:
            ():
        """

        self.__last_time = value

        return

    # ##### PUBLIC METHODS #####
    def reset(self) -> None:
        """
        Method to reset the timer, setting the last time to zero.

        Args:
            ():

        Returns:
            ():
        """

        self.last_time = time.time()

        return

    def update_last_time(self) -> None:
        """
        Method to update the last time to the current time.

        Args:
            ():

        Returns:
            ():
        """

        self.last_time = time.time()

        return

    def has_elapsed(self) -> bool:
        """
        Method to check if the interval has elapsed since the last update.

        Args:
            ():

        Returns:
            bool: True if the interval has elapsed, False otherwise.
        """

        return (time.time() - self.last_time) >= self.interval

    def get_remaining_time(self) -> float:
        """
        Method to calculate the remaining time until the timer elapses based on the last update time and the interval.

        Args:
            ():

        Returns:
            float: The remaining time in seconds.
        """

        return max(0.0, self.interval - (time.time() - self.last_time))
