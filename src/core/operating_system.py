#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Filename: operating_system.py
Author: Nico Hessenthaler
Date: 2026-06-05
Version: 1.0
Description:
    Module that provides utilities for interacting with the operating system.
License: Apache License Version 2.0
Contact: nico.hessenthaler@hs-heilbronn.de
"""

from datetime import datetime
import os
from pathlib import Path
import serial
import serial.tools.list_ports
import shutil
import subprocess
import time
from typing import Optional

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


def check_directory_exists(directory_path: str | Path) -> bool:
    """
    Function to check if a directory exists at the given path.

    Args:
        directory_path (str | Path): The path to the directory.

    Returns:
        exists (bool): True if the directory exists, False otherwise.
    """

    if isinstance(directory_path, str):
        t_path = Path(directory_path)
    else:
        t_path = directory_path

    t_exists = t_path.is_dir()

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


def delete_directory(directory_path: str | Path) -> None:
    """
    Function to delete a directory at the given path. Deletes all contents of the directory as well.

    Args:
        directory_path (str | Path): The path to the directory.

    Returns:
        ():
    """

    if isinstance(directory_path, str):
        t_path = Path(directory_path)
    else:
        t_path = directory_path

    if check_directory_exists(t_path):
        shutil.rmtree(t_path)

    return


def get_subdirectories(directory_path: str | Path) -> list[Path]:
    """
    Function to get a list of all subdirectories in the given main directory.

    Args:
        directory_path (str | Path): The path to the main directory.

    Returns:
        subdirectories (list[Path]): List of subdirectory Path objects.
    """

    if isinstance(directory_path, str):
        t_directory_path = Path(directory_path)
    else:
        t_directory_path = directory_path

    t_subdirectories = [t_path for t_path in t_directory_path.iterdir() if t_path.is_dir()]

    return t_subdirectories


def get_files_by_extension(directory_path: str | Path, extension: str) -> list[Path]:
    """
    Function to get a list of files in the given directory that match the specified file extension.

    Args:
        directory_path (str | Path): The path to the directory.
        extension (str): The file extension to filter by (e.g., ".png", ".txt").

    Returns:
        files (list[Path]): List of file Path objects matching the extension.
    """

    if isinstance(directory_path, str):
        t_path = Path(directory_path)
    else:
        t_path = directory_path

    if extension and not extension.startswith("."):
        extension = "." + extension

    if not extension:
        print_error("No file extension provided. Returning an empty list.")
        return []

    t_files = [t_file for t_file in t_path.iterdir() if t_file.is_file() and t_file.suffix == extension]

    return t_files


def get_all_files_in_directory(directory_path: str | Path) -> list[Path]:
    """
    Function to get a list of all files in the given directory.

    Args:
        directory_path (str | Path): The path to the directory.

    Returns:
        files (list[Path]): List of all file Path objects in the directory.
    """

    if isinstance(directory_path, str):
        t_path = Path(directory_path)
    else:
        t_path = directory_path

    t_files = [t_file for t_file in t_path.iterdir() if t_file.is_file()]

    return t_files


def copy_file(source_path: str | Path, destination_path: str | Path) -> None:
    """
    Function to copy a file from the source path to the destination path.

    Args:
        source_path (str | Path): The path to the source file.
        destination_path (str | Path): The path to the destination file.

    Returns:
        ():
    """

    if isinstance(source_path, str):
        t_source_path = Path(source_path)
    else:
        t_source_path = source_path

    if isinstance(destination_path, str):
        t_destination_path = Path(destination_path)
    else:
        t_destination_path = destination_path

    shutil.copy2(t_source_path, t_destination_path)

    return


def call_commands(
    commands: list[str],
    timeout: int = 60,
    env: Optional[dict[str, str]] = None,
    cwd: Optional[str] = None,
    shell_executable: str = "/bin/bash",
) -> tuple[int, str, str]:
    """
    Function to run multiple shell commands in one subprocess (commands are chained with '&&').
    Useful to activate a virtual environment and then run commands inside it.

    Args:
        commands (List[str]): List of shell commands to run sequentially.
        timeout (int): Timeout in seconds for the whole chained execution.
        env (Optional[Dict[str,str]]): Optional environment dict for the subprocess.
        cwd (Optional[str]): Optional working directory for the subprocess.
        shell_executable (str): Shell executable to use (default '/bin/bash').

    Returns:
        (return_code, stdout, stderr)
    """

    if not commands:
        return 0, "", ""

    # Chain commands so that later commands only run if earlier succeed
    t_cmd_str = " && ".join(commands)

    try:
        t_process = subprocess.Popen(
            t_cmd_str,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=True,
            executable=shell_executable,
            text=True,
            env=env or os.environ,
            cwd=cwd,
        )
        t_stdout, t_stderr = t_process.communicate(timeout=timeout)
        t_return_code = t_process.returncode
    except subprocess.TimeoutExpired:
        t_process.kill()
        t_stdout, t_stderr = t_process.communicate()
        t_return_code = -1
        t_stderr += "\nChained commands timed out."

    return t_return_code, t_stdout, t_stderr


def read_text_file(file_path: str) -> str:
    """
    Function to read the full content of a text file.

    Args:
        file_path (str): The path to the text file.

    Returns:
        content (str): The full content of the text file.
    """

    with open(file_path, "r", encoding="utf-8") as t_tf:
        t_content = t_tf.read()

    return t_content


def serial_port_list() -> list[str]:
    """
    Function that lists all available serial ports on the system.

    Args:
        ():

    Returns:
        port_list (list[str]): A list of available serial ports.
    """

    t_ports = serial.tools.list_ports.comports()

    t_port_list = []
    for t_port, t_description, _ in sorted(t_ports):
        t_port_list.append([t_port, t_description])

    return t_port_list


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


def check_file_modification_time(file_path: str | Path) -> float | None:
    """
    Function to check the modification time of a file.

    Args:
        file_path (str | Path): The path to the file.

    Returns:
        modification_time (float): Modification time of the file in seconds since epoch.
    """

    if isinstance(file_path, str):
        t_file_path = Path(file_path)
    else:
        t_file_path = file_path

    t_modification_time = t_file_path.stat().st_mtime

    return t_modification_time


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
