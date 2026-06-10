#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Filename: enums.py
Author: Nico Hessenthaler
Date: 2026-06-05
Version: 1.0
Description:
    Module that provides enumerations.
License: Apache License Version 2.0
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

    NO_ROBOT = 0
    RGB_INTRINSIC = 1
    EVENT_INTRINSIC = 2
    STEREO_EXTRINSIC = 3

    @property
    def label(self) -> str:
        """Human-readable display label for the calibration phase."""
        _labels = {
            CalibrationPhase.NO_ROBOT: "Handheld Calibration",
            CalibrationPhase.RGB_INTRINSIC: "Phase 1 - RGB Intrinsic",
            CalibrationPhase.EVENT_INTRINSIC: "Phase 2 - Event Intrinsic",
            CalibrationPhase.STEREO_EXTRINSIC: "Phase 3 - Stereo Extrinsic",
        }
        return _labels[self]
