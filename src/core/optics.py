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
Filename: optics.py
Author: Nico Hessenthaler
Date: 2026-06-05
Version: 1.0
Description:
    Module that provides utilities for camera related optic calculations.
License: Licensed under the Apache License, Version 2.0
Contact: nico.hessenthaler@hs-heilbronn.de
"""

from math import atan, degrees


def calculate_sensor_dimensions_m(
    vertical_resolution: int, horizontal_resolution: int, pixel_size: float
) -> tuple[float, float]:
    """
    Function that calculates the sensor dimensions in meters from the resolution and pixel size.

    Args:
        vertical_resolution (int): Vertical resolution of the camera in pixels.
        horizontal_resolution (int): Horizontal resolution of the camera in pixels.
        pixel_size (float): Size of a single pixel in meters.

    Returns:
        sensor_width (float): Width of the sensor in meters.
        sensor_height (float): Height of the sensor in meters.
    """

    # Calculate the sensor dimensions in meters
    t_sensor_width = horizontal_resolution * pixel_size
    t_sensor_height = vertical_resolution * pixel_size

    return t_sensor_width, t_sensor_height


def calculate_field_of_view_deg(focal_length: float, sensor_size: float) -> float:
    """
    Function that calculates the field of view in degrees from the focal length and sensor size.

    Args:
        focal_length (float): Focal length of the camera in meters.
        sensor_size (float): Size of the sensor in meters.

    Returns:
        field_of_view (float): Field of view in degrees.
    """

    # Calculate the field of view in radians
    t_field_of_view_rad = 2 * atan(sensor_size / (2 * focal_length))

    # Convert the field of view to degrees
    t_field_of_view_deg = degrees(t_field_of_view_rad)

    return t_field_of_view_deg
