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
Filename: enums.py
Author: Nico Hessenthaler
Date: 2026-06-05
Version: 1.0
Description:
    Module that provides enumerations.
License: Licensed under the Apache License, Version 2.0
Contact: nico.hessenthaler@hs-heilbronn.de
"""

from enum import IntEnum


class CameraType(IntEnum):
    """Enumeration for camera types."""

    EVENT = 0
    RGB = 1


class CameraState(IntEnum):
    """Enumeration for camera states."""

    INIT = 0
    RUNNING = 1
    ERROR = 2


class CalibrationPhase(IntEnum):
    """Enumeration for robot-assisted stereo calibration phases."""

    CHECKING_ROBOT = -1
    NO_ROBOT = 0
    RGB_INTRINSIC = 1
    EVENT_INTRINSIC = 2
    STEREO_EXTRINSIC = 3

    @property
    def label(self) -> str:
        """Human-readable display label for the calibration phase."""
        _labels = {
            CalibrationPhase.CHECKING_ROBOT: "Pinging UR5e Robot",
            CalibrationPhase.NO_ROBOT: "Handheld Calibration",
            CalibrationPhase.RGB_INTRINSIC: "Phase 1 - RGB Intrinsic",
            CalibrationPhase.EVENT_INTRINSIC: "Phase 2 - Event Intrinsic",
            CalibrationPhase.STEREO_EXTRINSIC: "Phase 3 - Stereo Extrinsic",
        }
        return _labels[self]
