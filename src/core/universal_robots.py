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
Filename: universal_robots.py
Author: Nico Hessenthaler
Date: 2026-06-05
Version: 1.0
Description:
    Module that provides utilities for interacting with Universal Robots robotic arms, such as calculating the required step movements for the calibration process.
License: Licensed under the Apache License, Version 2.0
Contact: nico.hessenthaler@hs-heilbronn.de
"""

import socket
import subprocess
import platform


def ping_robot(robot_ip: str) -> bool:
    """
    Function that pings the robot at the given IP address.

    Args:
        robot_ip (str): IP address of the robot.

    Returns:
        reachable (bool): True if the robot is reachable, False otherwise.
    """

    t_param = "-n" if platform.system().lower() == "windows" else "-c"
    t_command = ["ping", t_param, "1", robot_ip]

    try:
        return subprocess.call(t_command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0
    except Exception:
        return False


def open_ur_script_file(file_path: str) -> str:
    """
    Function that opens a URScript file and returns its content as a single string.

    Args:
        file_path (str): Path to the URScript file.

    Returns:
        content (str): Content of the URScript file as a single string.
    """

    with open(file_path, "r") as t_file:
        t_content = t_file.read()

    return t_content


def send_urscript(ur_script: str, robot_ip: str, primary_port: int, timeout: float = 1.0) -> None:
    """
    Function that sends a URScript to the Universal Robots robotic arm.

    Args:
        ur_script (str): URScript to be sent to the robot.
        robot_ip (str): IP address of the robot.
        primary_port (int): Primary port for communication with the robot.
        timeout (float): Timeout for the socket connection.

    Returns:
        ():
    """

    t_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    t_socket.settimeout(timeout)
    t_socket.connect((robot_ip, primary_port))
    t_socket.sendall((ur_script + "\n").encode("utf-8"))
    t_socket.close()

    return


def reset_digital_outputs(robot_ip: str, primary_port: int) -> None:
    """
    Function that resets the digital outputs of the Universal Robots robotic arm to a known state (all outputs set to False).

    Args:
        robot_ip (str): IP address of the robot.
        primary_port (int): Primary port for communication with the robot.

    Returns:
        ():
    """

    t_reset_script = (
        "def reset_outputs():\n"
        "  set_standard_digital_out(1, False)\n"
        "  set_standard_digital_out(2, False)\n"
        "end\n"
    )

    send_urscript(t_reset_script, robot_ip, primary_port)

    return


def send_stop_command(robot_ip: str, primary_port: int, timeout: float = 1.0) -> None:
    """
    Function that sends a soft stop command to the Universal Robots robotic arm.

    Args:
        robot_ip (str): IP address of the robot.
        primary_port (int): Primary port for communication with the robot.
        timeout (float): Timeout for the socket connection.

    Returns:
        ():
    """

    t_stop_command = 'b"stop\n"'
    t_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    t_socket.settimeout(timeout)
    t_socket.connect((robot_ip, primary_port))
    t_socket.sendall((t_stop_command + "\n").encode("utf-8"))
    t_socket.close()

    return
