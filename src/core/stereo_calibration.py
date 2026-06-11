#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Filename: stereo_calibration.py
Author: Nico Hessenthaler
Date: 2026-06-05
Version: 1.0
Description:
    Module that provides functionality to perform cross-modal stereo calibration on the event camera and RGB camera.
License: Apache License Version 2.0
Contact: nico.hessenthaler@hs-heilbronn.de
"""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gui.stereo_calibration import StereoCalibrationGUI
    from multiprocessing.managers import ValueProxy
    from multiprocessing.synchronize import Event as EventProxy

import configparser
import cv2
from .calibration import (
    calculate_intrinsic_parameters,
    calculate_stereo_parameters,
    visualize_fov_coverage,
    save_intrinsics_to_json,
    save_extrinsics_to_json,
    CharucoBoardHandler,
    UR5eCalibrator,
)
from .image_processing import bgr2gray_cv, resize_image_cv, Cv2ToBase64Converter
from .multiprocessing import RawSharedMemory, B64SharedMemory
from .operating_system import Timer, print_info, print_error, print_success
from .prophesee import prophesee_worker
from .ueye import ueye_worker
from .enums import CalibrationPhase
from .universal_robots import (
    ping_robot,
    send_stop_command,
    reset_digital_outputs,
)
import multiprocessing
import numpy as np
from pathlib import Path
import threading
import time


class StereoCalibration:
    """Class that provides the core functionality for the stereo calibration process."""

    def __init__(
        self,
        event_raw_shm: RawSharedMemory,
        rgb_raw_shm: RawSharedMemory,
        event_b64_shm: B64SharedMemory,
        rgb_b64_shm: B64SharedMemory,
        stereo_calibration_active: EventProxy,
        generate_targets_triggered: EventProxy,
        next_capture_timer: ValueProxy,
        target_square_size: ValueProxy,
        current_calibration_phase: ValueProxy,
    ) -> None:

        # Store multiprocessing shared memory and synchronization primitives
        self.__event_raw_shm = event_raw_shm
        self.__rgb_raw_shm = rgb_raw_shm
        self.__event_b64_shm = event_b64_shm
        self.__rgb_b64_shm = rgb_b64_shm
        self.__stereo_calibration_active = stereo_calibration_active
        self.__generate_targets_triggered = generate_targets_triggered
        self.__next_capture_timer = next_capture_timer
        self.__target_square_size = target_square_size
        self.__current_calibration_phase = current_calibration_phase

        # Instantiate b64 converter
        self.__cv2_to_b64_converter_instance = Cv2ToBase64Converter()

        # Load configurations from file system
        self.__stereo_calibration_config = configparser.ConfigParser()
        self.__stereo_calibration_config.read(Path(__file__).parents[2] / "parameter" / "stereo_calibration.ini")
        self.__gui_config = configparser.ConfigParser()
        self.__gui_config.read(Path(__file__).parents[2] / "parameter" / "gui.ini")
        self.__camera_config = configparser.ConfigParser()
        self.__camera_config.read(
            [
                Path(__file__).parents[2] / "parameter" / "camera.ini",
                Path(__file__).parents[2] / "parameter" / "camera_stereo_calibration.ini",
            ]
        )

        # Parse the camera parameters from the configuration file
        self.__prophesee_intrinsic_calibration_file_name = self.__camera_config.get(
            "prophesee", "intrinsic_calibration_file_name"
        )
        self.__ueye_intrinsic_calibration_file_name = self.__camera_config.get(
            "ueye", "intrinsic_calibration_file_name"
        )

        # Load the intrinsic calibration parameters for both cameras from the specified files
        # (adds new parameters to the config if not already present)
        self.__camera_config.read(
            [
                Path(__file__).parents[2] / "parameter" / self.__prophesee_intrinsic_calibration_file_name,
                Path(__file__).parents[2] / "parameter" / self.__ueye_intrinsic_calibration_file_name,
            ]
        )

        # Build initial guess camera matrices from physical sensor parameters - RGB
        t_rgb_focal_length = self.__camera_config.getfloat("ueye_lens", "focal_length")
        t_rgb_pixel_size = self.__camera_config.getfloat("ueye", "pixel_size")
        t_rgb_width = self.__camera_config.getint("ueye", "horizontal_resolution")
        t_rgb_height = self.__camera_config.getint("ueye", "vertical_resolution")
        t_rgb_f_px = t_rgb_focal_length / t_rgb_pixel_size
        self.__rgb_initial_camera_matrix = np.array(
            [
                [t_rgb_f_px, 0.0, t_rgb_width / 2.0],
                [0.0, t_rgb_f_px, t_rgb_height / 2.0],
                [0.0, 0.0, 1.0],
            ],
            dtype=np.float64,
        )

        # Build initial guess camera matrices from physical sensor parameters - Event
        t_event_focal_length = self.__camera_config.getfloat("prophesee_lens", "focal_length")
        t_event_pixel_size = self.__camera_config.getfloat("prophesee", "pixel_size")
        t_event_width = self.__camera_config.getint("prophesee", "horizontal_resolution")
        t_event_height = self.__camera_config.getint("prophesee", "vertical_resolution")
        t_event_f_px = t_event_focal_length / t_event_pixel_size
        self.__event_initial_camera_matrix = np.array(
            [
                [t_event_f_px, 0.0, t_event_width / 2.0],
                [0.0, t_event_f_px, t_event_height / 2.0],
                [0.0, 0.0, 1.0],
            ],
            dtype=np.float64,
        )

        # Parse the GUI parameters from the configuration file
        self.__image_display_height = self.__gui_config.getint("data_capture", "image_display_height")
        self.__image_width = self.__gui_config.getint("data_capture", "image_width")

        # Read parameters from file system
        self.__capture_interval = self.__stereo_calibration_config.getfloat("recording", "capture_interval")
        self.__target_pattern_size = (
            self.__stereo_calibration_config.getint("target", "target_columns"),
            self.__stereo_calibration_config.getint("target", "target_rows"),
        )
        self.__target_marker_size_fraction = self.__stereo_calibration_config.getfloat(
            "target", "target_marker_size_fraction"
        )
        self.__target_window_title = self.__stereo_calibration_config.get("target", "target_window_title")
        self.__target_bitmap_size = (
            self.__stereo_calibration_config.getint("target", "target_bitmap_width"),
            self.__stereo_calibration_config.getint("target", "target_bitmap_height"),
        )
        self.__target_display_size = (
            self.__stereo_calibration_config.getint("target", "target_display_width"),
            self.__stereo_calibration_config.getint("target", "target_display_height"),
        )
        self.__target_dim_alpha = self.__stereo_calibration_config.getfloat("target", "target_dim_alpha")
        self.__target_margin = self.__stereo_calibration_config.getint("target", "target_margin")
        self.__target_video_duration = self.__stereo_calibration_config.getfloat("target", "target_video_duration")
        self.__target_video_fps = self.__stereo_calibration_config.getint("target", "target_video_fps")
        self.__target_frequency = self.__stereo_calibration_config.getfloat("target", "target_frequency")
        self.__target_bitmap_file_name = self.__stereo_calibration_config.get("target", "target_bitmap_file_name")
        self.__target_video_file_name = self.__stereo_calibration_config.get("target", "target_video_file_name")
        self.__header_output_path = str(
            Path(__file__).parents[2] / "data" / "flicker_calib_board" / self.__target_bitmap_file_name
        )
        self.__video_output_path = str(Path(__file__).parents[2] / "data" / self.__target_video_file_name)
        self.__min_corners_for_calibration = self.__stereo_calibration_config.getint(
            "calibration", "min_corners_for_calibration"
        )
        self.__reprojection_error_threshold = self.__stereo_calibration_config.getfloat(
            "calibration", "reprojection_error_threshold"
        )
        self.__rgb_intrinsics_file_path = self.__stereo_calibration_config.get("recording", "rgb_intrinsics_file_path")
        self.__event_intrinsics_file_path = self.__stereo_calibration_config.get(
            "recording", "event_intrinsics_file_path"
        )
        self.__extrinsics_file_path = self.__stereo_calibration_config.get("recording", "extrinsics_file_path")
        self.__stop_command_delay = self.__stereo_calibration_config.getfloat("ur5e", "stop_command_delay")
        self.__robot_ip = self.__stereo_calibration_config.get("ur5e", "robot_ip")
        self.__secondary_port = self.__stereo_calibration_config.getint("ur5e", "secondary_port")
        self.__primary_port = self.__stereo_calibration_config.getint("ur5e", "primary_port")

        # Initialize Timer
        self.__capture_timer_instance = Timer(self.__capture_interval)

        # Initialize Charuco Board Handler
        self.__charuco_board_handler = CharucoBoardHandler(
            live_window_title=self.__target_window_title,
            squares_x=self.__target_pattern_size[0] + 1,
            squares_y=self.__target_pattern_size[1] + 1,
            square_length=self.__target_square_size.value,
            marker_length=self.__target_square_size.value * self.__target_marker_size_fraction,
        )

        # Initialization attributes
        self.__rgb_initialized = False
        self.__event_initialized = False

        # States
        self.__calibration_was_active = False

        # Calibration state
        self.__rgb_fov_mask = None
        self.__event_fov_mask = None

        # Storage for synchronized calibration points
        self.__rgb_image_points_synced = []
        self.__event_image_points_synced = []
        self.__object_points_synced = []

        # Storage for single camera calibration points
        self.__rgb_image_points = []
        self.__event_image_points = []
        self.__object_points_rgb = []
        self.__object_points_event = []

        # Latest frames
        self.__latest_rgb_frame = None
        self.__latest_event_frame = None

        # Base64 encoded processed frames for display
        self.__processed_rgb_b64 = None
        self.__processed_event_b64 = None

        # Persistent storage for latest detected corners (used for draw_corners)
        self.__latest_rgb_corners = None
        self.__latest_event_corners = None
        self.__latest_rgb_corner_ids = None
        self.__latest_event_corner_ids = None

        # Persistent storage for latest detected ArUco marker corners (used for draw_markers)
        self.__latest_rgb_marker_corners = None
        self.__latest_rgb_marker_ids = None
        self.__latest_event_marker_corners = None
        self.__latest_event_marker_ids = None

        # Robot-assisted calibration phase tracking
        self.__calibration_phase = None
        self.__robot_thread = None

        # Event set by the robot thread when a position reached DO2 signal is detected
        self.__robot_position_reached = threading.Event()

        # Timestamp recorded when position reached fires (for non-blocking settle delay)
        self.__position_reached_time: float | None = None

        # Asynchronous robot ping state (to avoid blocking the main loop / freezing the GUI)
        self.__robot_ping_complete = False
        self.__robot_reachable = False

    # ##### GETTER #####
    @property
    def event_raw_shm(self) -> RawSharedMemory:
        """
        Getter for the attribute '__event_raw_shm'.

        Args:
            ():

        Returns:
            event_raw_shm (RawSharedMemory): The attribute '__event_raw_shm'.
        """

        return self.__event_raw_shm

    @property
    def rgb_raw_shm(self) -> RawSharedMemory:
        """
        Getter for the attribute '__rgb_raw_shm'.

        Args:
            ():

        Returns:
            rgb_raw_shm (RawSharedMemory): The attribute '__rgb_raw_shm'.
        """

        return self.__rgb_raw_shm

    @property
    def event_b64_shm(self) -> B64SharedMemory:
        """
        Getter for the attribute '__event_b64_shm'.

        Args:
            ():

        Returns:
            event_b64_shm (B64SharedMemory): The attribute '__event_b64_shm'.
        """

        return self.__event_b64_shm

    @property
    def rgb_b64_shm(self) -> B64SharedMemory:
        """
        Getter for the attribute '__rgb_b64_shm'.

        Args:
            ():

        Returns:
            rgb_b64_shm (B64SharedMemory): The attribute '__rgb_b64_shm'.
        """

        return self.__rgb_b64_shm

    @property
    def stereo_calibration_active(self) -> EventProxy:
        """
        Getter for the attribute '__stereo_calibration_active'.

        Args:
            ():

        Returns:
            stereo_calibration_active (EventProxy): The attribute '__stereo_calibration_active'.
        """

        return self.__stereo_calibration_active

    @property
    def generate_targets_triggered(self) -> EventProxy:
        """
        Getter for the attribute '__generate_targets_triggered'.

        Args:
            ():

        Returns:
            generate_targets_triggered (EventProxy): The attribute '__generate_targets_triggered'.
        """

        return self.__generate_targets_triggered

    @property
    def next_capture_timer(self) -> ValueProxy:
        """
        Getter for the attribute '__next_capture_timer'.

        Args:
            ():

        Returns:
            next_capture_timer (ValueProxy): The attribute '__next_capture_timer'.
        """

        return self.__next_capture_timer

    @property
    def cv2_to_b64_converter_instance(self) -> Cv2ToBase64Converter:
        """
        Getter for the attribute '__cv2_to_b64_converter_instance'.

        Args:
            ():

        Returns:
            cv2_to_b64_converter_instance (Cv2ToBase64Converter): The attribute '__cv2_to_b64_converter_instance'.
        """

        return self.__cv2_to_b64_converter_instance

    @property
    def capture_timer_instance(self) -> Timer:
        """
        Getter for the attribute '__capture_timer_instance'.

        Args:
            ():

        Returns:
            capture_timer_instance (Timer): The attribute '__capture_timer_instance'.
        """

        return self.__capture_timer_instance

    @property
    def charuco_board_handler(self) -> CharucoBoardHandler:
        """
        Getter for the attribute '__charuco_board_handler'.

        Args:
            ():

        Returns:
            charuco_board_handler (CharucoBoardHandler): The attribute '__charuco_board_handler'.
        """

        return self.__charuco_board_handler

    @property
    def rgb_initialized(self) -> bool:
        """
        Getter for the attribute '__rgb_initialized'.

        Args:
            ():

        Returns:
            rgb_initialized (bool): The attribute '__rgb_initialized'.
        """

        return self.__rgb_initialized

    @property
    def event_initialized(self) -> bool:
        """
        Getter for the attribute '__event_initialized'.

        Args:
            ():

        Returns:
            event_initialized (bool): The attribute '__event_initialized'.
        """

        return self.__event_initialized

    @property
    def calibration_was_active(self) -> bool:
        """
        Getter for the attribute '__calibration_was_active'.

        Args:
            ():

        Returns:
            calibration_was_active (bool): The attribute '__calibration_was_active'.
        """

        return self.__calibration_was_active

    @property
    def rgb_fov_mask(self) -> np.ndarray | None:
        """
        Getter for the attribute '__rgb_fov_mask'.

        Args:
            ():

        Returns:
            rgb_fov_mask (np.ndarray | None): The attribute '__rgb_fov_mask'.
        """

        return self.__rgb_fov_mask

    @property
    def event_fov_mask(self) -> np.ndarray | None:
        """
        Getter for the attribute '__event_fov_mask'.

        Args:
            ():

        Returns:
            event_fov_mask (np.ndarray | None): The attribute '__event_fov_mask'.
        """

        return self.__event_fov_mask

    @property
    def rgb_image_points_synced(self) -> list[np.ndarray]:
        """
        Getter for the attribute '__rgb_image_points_synced'.

        Args:
            ():

        Returns:
            rgb_image_points_synced (list[np.ndarray]): The attribute '__rgb_image_points_synced'.
        """

        return self.__rgb_image_points_synced

    @property
    def event_image_points_synced(self) -> list[np.ndarray]:
        """
        Getter for the attribute '__event_image_points_synced'.

        Args:
            ():

        Returns:
            event_image_points_synced (list[np.ndarray]): The attribute '__event_image_points_synced'.
        """

        return self.__event_image_points_synced

    @property
    def object_points_synced(self) -> list[np.ndarray]:
        """
        Getter for the attribute '__object_points_synced'.

        Args:
            ():

        Returns:
            object_points_synced (list[np.ndarray]): The attribute '__object_points_synced'.
        """

        return self.__object_points_synced

    @property
    def rgb_image_points(self) -> list[np.ndarray]:
        """
        Getter for the attribute '__rgb_image_points'.

        Args:
            ():

        Returns:
            rgb_image_points (list[np.ndarray]): The attribute '__rgb_image_points'.
        """

        return self.__rgb_image_points

    @property
    def event_image_points(self) -> list[np.ndarray]:
        """
        Getter for the attribute '__event_image_points'.

        Args:
            ():

        Returns:
            event_image_points (list[np.ndarray]): The attribute '__event_image_points'.
        """

        return self.__event_image_points

    @property
    def object_points_rgb(self) -> list[np.ndarray]:
        """
        Getter for the attribute '__object_points_rgb'.

        Args:
            ():

        Returns:
            object_points_rgb (list[np.ndarray]): The attribute '__object_points_rgb'.
        """

        return self.__object_points_rgb

    @property
    def object_points_event(self) -> list[np.ndarray]:
        """
        Getter for the attribute '__object_points_event'.

        Args:
            ():

        Returns:
            object_points_event (list[np.ndarray]): The attribute '__object_points_event'.
        """

        return self.__object_points_event

    @property
    def latest_rgb_frame(self) -> np.ndarray | None:
        """
        Getter for the attribute '__latest_rgb_frame'.

        Args:
            ():

        Returns:
            latest_rgb_frame (np.ndarray | None): The attribute '__latest_rgb_frame'.
        """

        return self.__latest_rgb_frame

    @property
    def latest_event_frame(self) -> np.ndarray | None:
        """
        Getter for the attribute '__latest_event_frame'.

        Args:
            ():

        Returns:
            latest_event_frame (np.ndarray | None): The attribute '__latest_event_frame'.
        """

        return self.__latest_event_frame

    @property
    def processed_rgb_b64(self) -> str | None:
        """
        Getter for the attribute '__processed_rgb_b64'.

        Args:
            ():

        Returns:
            processed_rgb_b64 (str | None): The attribute '__processed_rgb_b64'.
        """

        return self.__processed_rgb_b64

    @property
    def processed_event_b64(self) -> str | None:
        """
        Getter for the attribute '__processed_event_b64'.

        Args:
            ():

        Returns:
            processed_event_b64 (str | None): The attribute '__processed_event_b64'.
        """

        return self.__processed_event_b64

    @property
    def latest_rgb_corners(self) -> np.ndarray | None:
        """
        Getter for the attribute '__latest_rgb_corners'.

        Args:
            ():

        Returns:
            latest_rgb_corners (np.ndarray | None): The attribute '__latest_rgb_corners'.
        """

        return self.__latest_rgb_corners

    @property
    def latest_event_corners(self) -> np.ndarray | None:
        """
        Getter for the attribute '__latest_event_corners'.

        Args:
            ():

        Returns:
            latest_event_corners (np.ndarray | None): The attribute '__latest_event_corners'.
        """

        return self.__latest_event_corners

    @property
    def latest_rgb_corner_ids(self) -> np.ndarray | None:
        """
        Getter for the attribute '__latest_rgb_corner_ids'.

        Args:
            ():

        Returns:
            latest_rgb_corner_ids (np.ndarray | None): The attribute '__latest_rgb_corner_ids'.
        """

        return self.__latest_rgb_corner_ids

    @property
    def latest_event_corner_ids(self) -> np.ndarray | None:
        """
        Getter for the attribute '__latest_event_corner_ids'.

        Args:
            ():

        Returns:
            latest_event_corner_ids (np.ndarray | None): The attribute '__latest_event_corner_ids'.
        """

        return self.__latest_event_corner_ids

    @property
    def latest_rgb_marker_corners(self) -> list | None:
        """
        Getter for the attribute '__latest_rgb_marker_corners'.

        Args:
            ():

        Returns:
            latest_rgb_marker_corners (list | None): The attribute '__latest_rgb_marker_corners'.
        """

        return self.__latest_rgb_marker_corners

    @property
    def latest_rgb_marker_ids(self) -> np.ndarray | None:
        """
        Getter for the attribute '__latest_rgb_marker_ids'.

        Args:
            ():

        Returns:
            latest_rgb_marker_ids (np.ndarray | None): The attribute '__latest_rgb_marker_ids'.
        """

        return self.__latest_rgb_marker_ids

    @property
    def latest_event_marker_corners(self) -> list | None:
        """
        Getter for the attribute '__latest_event_marker_corners'.

        Args:
            ():

        Returns:
            latest_event_marker_corners (list | None): The attribute '__latest_event_marker_corners'.
        """

        return self.__latest_event_marker_corners

    @property
    def latest_event_marker_ids(self) -> np.ndarray | None:
        """
        Getter for the attribute '__latest_event_marker_ids'.

        Args:
            ():

        Returns:
            latest_event_marker_ids (np.ndarray | None): The attribute '__latest_event_marker_ids'.
        """

        return self.__latest_event_marker_ids

    @property
    def calibration_phase(self) -> CalibrationPhase | None:
        """
        Getter for the attribute '__calibration_phase'.

        Args:
            ():

        Returns:
            calibration_phase (CalibrationPhase | None): The attribute '__calibration_phase'.
        """

        return self.__calibration_phase

    @property
    def robot_thread(self) -> threading.Thread | None:
        """
        Getter for the attribute '__robot_thread'.

        Args:
            ():

        Returns:
            robot_thread (threading.Thread | None): The attribute '__robot_thread'.
        """

        return self.__robot_thread

    @property
    def robot_position_reached(self) -> threading.Event:
        """
        Getter for the attribute '__robot_position_reached'.

        Args:
            ():

        Returns:
            robot_position_reached (threading.Event): The attribute '__robot_position_reached'.
        """

        return self.__robot_position_reached

    @property
    def position_reached_time(self) -> float | None:
        """
        Getter for the attribute '__position_reached_time'.

        Args:
            ():

        Returns:
            position_reached_time (float | None): The attribute '__position_reached_time'.
        """

        return self.__position_reached_time

    @property
    def robot_ping_complete(self) -> bool:
        """
        Getter for the attribute '__robot_ping_complete'.

        Args:
            ():

        Returns:
            robot_ping_complete (bool): The attribute '__robot_ping_complete'.
        """

        return self.__robot_ping_complete

    @property
    def robot_reachable(self) -> bool:
        """
        Getter for the attribute '__robot_reachable'.

        Args:
            ():

        Returns:
            robot_reachable (bool): The attribute '__robot_reachable'.
        """

        return self.__robot_reachable

    # ##### SETTER #####
    @capture_timer_instance.setter
    def capture_timer_instance(self, value: Timer) -> None:
        """
        Setter for the attribute '__capture_timer_instance'.

        Args:
            value (Timer): The new value for the attribute '__capture_timer_instance'.

        Returns:
            ():
        """

        self.__capture_timer_instance = value

        return

    @rgb_initialized.setter
    def rgb_initialized(self, value: bool) -> None:
        """
        Setter for the attribute '__rgb_initialized'.

        Args:
            value (bool): The new value for the attribute '__rgb_initialized'.

        Returns:
            ():
        """

        self.__rgb_initialized = value

        return

    @event_initialized.setter
    def event_initialized(self, value: bool) -> None:
        """
        Setter for the attribute '__event_initialized'.

        Args:
            value (bool): The new value for the attribute '__event_initialized'.

        Returns:
            ():
        """

        self.__event_initialized = value

        return

    @calibration_was_active.setter
    def calibration_was_active(self, value: bool) -> None:
        """
        Setter for the attribute '__calibration_was_active'.

        Args:
            value (bool): The new value for the attribute '__calibration_was_active'.

        Returns:
            ():
        """

        self.__calibration_was_active = value

        return

    @rgb_fov_mask.setter
    def rgb_fov_mask(self, value: np.ndarray | None) -> None:
        """
        Setter for the attribute '__rgb_fov_mask'.

        Args:
            value (np.ndarray | None): The new value for the attribute '__rgb_fov_mask'.

        Returns:
            ():
        """

        self.__rgb_fov_mask = value

        return

    @event_fov_mask.setter
    def event_fov_mask(self, value: np.ndarray | None) -> None:
        """
        Setter for the attribute '__event_fov_mask'.

        Args:
            value (np.ndarray | None): The new value for the attribute '__event_fov_mask'.

        Returns:
            ():
        """

        self.__event_fov_mask = value

        return

    @rgb_image_points_synced.setter
    def rgb_image_points_synced(self, value: list[np.ndarray]) -> None:
        """
        Setter for the attribute '__rgb_image_points_synced'.

        Args:
            value (list[np.ndarray]): The new value for the attribute '__rgb_image_points_synced'.

        Returns:
            ():
        """

        self.__rgb_image_points_synced = value

        return

    @event_image_points_synced.setter
    def event_image_points_synced(self, value: list[np.ndarray]) -> None:
        """
        Setter for the attribute '__event_image_points_synced'.

        Args:
            value (list[np.ndarray]): The new value for the attribute '__event_image_points_synced'.

        Returns:
            ():
        """

        self.__event_image_points_synced = value

        return

    @object_points_synced.setter
    def object_points_synced(self, value: list[np.ndarray]) -> None:
        """
        Setter for the attribute '__object_points_synced'.

        Args:
            value (list[np.ndarray]): The new value for the attribute '__object_points_synced'.

        Returns:
            ():
        """

        self.__object_points_synced = value

        return

    @rgb_image_points.setter
    def rgb_image_points(self, value: list[np.ndarray]) -> None:
        """
        Setter for the attribute '__rgb_image_points'.

        Args:
            value (list[np.ndarray]): The new value for the attribute '__rgb_image_points'.

        Returns:
            ():
        """

        self.__rgb_image_points = value

        return

    @event_image_points.setter
    def event_image_points(self, value: list[np.ndarray]) -> None:
        """
        Setter for the attribute '__event_image_points'.

        Args:
            value (list[np.ndarray]): The new value for the attribute '__event_image_points'.

        Returns:
            ():
        """

        self.__event_image_points = value

        return

    @object_points_rgb.setter
    def object_points_rgb(self, value: list[np.ndarray]) -> None:
        """
        Setter for the attribute '__object_points_rgb'.

        Args:
            value (list[np.ndarray]): The new value for the attribute '__object_points_rgb'.

        Returns:
            ():
        """

        self.__object_points_rgb = value

        return

    @object_points_event.setter
    def object_points_event(self, value: list[np.ndarray]) -> None:
        """
        Setter for the attribute '__object_points_event'.

        Args:
            value (list[np.ndarray]): The new value for the attribute '__object_points_event'.

        Returns:
            ():
        """

        self.__object_points_event = value

        return

    @latest_rgb_frame.setter
    def latest_rgb_frame(self, value: np.ndarray | None) -> None:
        """
        Setter for the attribute '__latest_rgb_frame'.

        Args:
            value (np.ndarray | None): The new value for the attribute '__latest_rgb_frame'.

        Returns:
            ():
        """

        self.__latest_rgb_frame = value

        return

    @latest_event_frame.setter
    def latest_event_frame(self, value: np.ndarray | None) -> None:
        """
        Setter for the attribute '__latest_event_frame'.

        Args:
            value (np.ndarray | None): The new value for the attribute '__latest_event_frame'.

        Returns:
            ():
        """

        self.__latest_event_frame = value

        return

    @latest_rgb_corner_ids.setter
    def latest_rgb_corner_ids(self, value: np.ndarray | None) -> None:
        """
        Setter for the attribute '__latest_rgb_corner_ids'.

        Args:
            value (np.ndarray | None): The new value for the attribute '__latest_rgb_corner_ids'.

        Returns:
            ():
        """

        self.__latest_rgb_corner_ids = value

        return

    @latest_event_corner_ids.setter
    def latest_event_corner_ids(self, value: np.ndarray | None) -> None:
        """
        Setter for the attribute '__latest_event_corner_ids'.

        Args:
            value (np.ndarray | None): The new value for the attribute '__latest_event_corner_ids'.

        Returns:
            ():
        """

        self.__latest_event_corner_ids = value

        return

    @latest_rgb_marker_corners.setter
    def latest_rgb_marker_corners(self, value: list | None) -> None:
        """
        Setter for the attribute '__latest_rgb_marker_corners'.

        Args:
            value (list | None): The new value for the attribute '__latest_rgb_marker_corners'.

        Returns:
            ():
        """

        self.__latest_rgb_marker_corners = value

        return

    @latest_rgb_marker_ids.setter
    def latest_rgb_marker_ids(self, value: np.ndarray | None) -> None:
        """
        Setter for the attribute '__latest_rgb_marker_ids'.

        Args:
            value (np.ndarray | None): The new value for the attribute '__latest_rgb_marker_ids'.

        Returns:
            ():
        """

        self.__latest_rgb_marker_ids = value

        return

    @latest_event_marker_corners.setter
    def latest_event_marker_corners(self, value: list | None) -> None:
        """
        Setter for the attribute '__latest_event_marker_corners'.

        Args:
            value (list | None): The new value for the attribute '__latest_event_marker_corners'.

        Returns:
            ():
        """

        self.__latest_event_marker_corners = value

        return

    @latest_event_marker_ids.setter
    def latest_event_marker_ids(self, value: np.ndarray | None) -> None:
        """
        Setter for the attribute '__latest_event_marker_ids'.

        Args:
            value (np.ndarray | None): The new value for the attribute '__latest_event_marker_ids'.

        Returns:
            ():
        """

        self.__latest_event_marker_ids = value

        return

    @processed_rgb_b64.setter
    def processed_rgb_b64(self, value: str | None) -> None:
        """
        Setter for the attribute '__processed_rgb_b64'.

        Args:
            value (str | None): The new value for the attribute '__processed_rgb_b64'.

        Returns:
            ():
        """

        self.__processed_rgb_b64 = value

        return

    @processed_event_b64.setter
    def processed_event_b64(self, value: str | None) -> None:
        """
        Setter for the attribute '__processed_event_b64'.

        Args:
            value (str | None): The new value for the attribute '__processed_event_b64'.

        Returns:
            ():
        """

        self.__processed_event_b64 = value

        return

    @latest_rgb_corners.setter
    def latest_rgb_corners(self, value: np.ndarray | None) -> None:
        """
        Setter for the attribute '__latest_rgb_corners'.

        Args:
            value (np.ndarray | None): The new value for the attribute '__latest_rgb_corners'.

        Returns:
            ():
        """

        self.__latest_rgb_corners = value

        return

    @latest_event_corners.setter
    def latest_event_corners(self, value: np.ndarray | None) -> None:
        """
        Setter for the attribute '__latest_event_corners'.

        Args:
            value (np.ndarray | None): The new value for the attribute '__latest_event_corners'.

        Returns:
            ():
        """

        self.__latest_event_corners = value

        return

    @calibration_phase.setter
    def calibration_phase(self, value: CalibrationPhase | None) -> None:
        """
        Setter for the attribute '__calibration_phase'.

        Args:
            value (CalibrationPhase | None): The new value for the attribute '__calibration_phase'.

        Returns:
            ():
        """

        self.__calibration_phase = value
        if self.__current_calibration_phase is not None:
            self.__current_calibration_phase.value = int(value) if value is not None else -1

        return

    @robot_thread.setter
    def robot_thread(self, value: threading.Thread | None) -> None:
        """
        Setter for the attribute '__robot_thread'.

        Args:
            value (threading.Thread | None): The new value for the attribute '__robot_thread'.

        Returns:
            ():
        """

        self.__robot_thread = value

        return

    @position_reached_time.setter
    def position_reached_time(self, value: float | None) -> None:
        """
        Setter for the attribute '__position_reached_time'.

        Args:
            value (float | None): The new value for the attribute '__position_reached_time'.

        Returns:
            ():
        """

        self.__position_reached_time = value

        return

    @robot_ping_complete.setter
    def robot_ping_complete(self, value: bool) -> None:
        """
        Setter for the attribute '__robot_ping_complete'.

        Args:
            value (bool): The new value for the attribute '__robot_ping_complete'.

        Returns:
            ():
        """

        self.__robot_ping_complete = value

        return

    @robot_reachable.setter
    def robot_reachable(self, value: bool) -> None:
        """
        Setter for the attribute '__robot_reachable'.

        Args:
            value (bool): The new value for the attribute '__robot_reachable'.

        Returns:
            ():
        """

        self.__robot_reachable = value

        return

    # ##### PRIVATE METHODS #####
    def _check_calibration_reset(self) -> None:
        """
        Method to check if the calibration has been stopped and reset necessary parameters.
        This should be called at the beginning of each loop iteration in the run method.

        Args:
            ():

        Returns:
            ():
        """

        # Falling edge detection for calibration active state
        if not self.stereo_calibration_active.is_set() and self.calibration_was_active:
            # Calculate the calibration results before resetting
            self._calculate_final_calibration_results()

            # Reset FOV masks
            self.rgb_fov_mask = None
            self.event_fov_mask = None

            # Clear all calibration points
            self.rgb_image_points.clear()
            self.event_image_points.clear()
            self.rgb_image_points_synced.clear()
            self.event_image_points_synced.clear()
            self.object_points_synced.clear()
            self.object_points_rgb.clear()
            self.object_points_event.clear()

            # Clear persistent corners
            self.latest_rgb_corners = None
            self.latest_event_corners = None
            self.latest_rgb_corner_ids = None
            self.latest_event_corner_ids = None
            self.latest_rgb_marker_corners = None
            self.latest_rgb_marker_ids = None
            self.latest_event_marker_corners = None
            self.latest_event_marker_ids = None

            # Reset capture timer to avoid immediate capture when calibration is restarted
            self.capture_timer_instance.reset()

            # Reset that calibration was active flag
            self.calibration_was_active = False

            # Reset calibration phase; any running robot thread will finish on its own (daemon)
            self.calibration_phase = None
            self.robot_position_reached.clear()
            self.position_reached_time = None

            # Stop the robot execution if it is still running (safety measure, should be daemon and finish on its own)
            # Only attempt robot communication if the robot is reachable (e.g. not connected during testing)
            # Run ping + stop in a background thread to avoid blocking the main loop / freezing the GUI
            self.robot_reachable = False
            self.robot_ping_complete = False
            threading.Thread(
                target=self._stop_robot_if_reachable,
                daemon=True,
            ).start()

            # Kill the robot thread if it's still running (safety measure, should be daemon and finish on its own)
            if self.robot_thread is not None and self.robot_thread.is_alive():
                self.robot_thread.join(timeout=0.1)
                self.robot_thread = None

        return

    def _stop_robot_if_reachable(self) -> None:
        """
        Background thread helper to ping the robot and send stop/reset commands if reachable.
        Runs asynchronously to avoid blocking the main loop.

        Args:
            ():

        Returns:
            ():
        """

        if ping_robot(self.__robot_ip):
            self.robot_reachable = True
            send_stop_command(self.__robot_ip, self.__secondary_port)
            reset_digital_outputs(self.__robot_ip, self.__primary_port)

        self.robot_ping_complete = True

        return

    def _ping_robot_async(self, robot_ip: str) -> None:
        """
        Background thread helper to ping the robot and set the reachability flag.
        Runs asynchronously to avoid blocking the main loop / freezing the GUI.

        Args:
            robot_ip (str): IP address of the robot to ping.

        Returns:
            ():
        """

        self.robot_reachable = ping_robot(robot_ip)
        self.robot_ping_complete = True

        return

    def _pull_latest_frame(
        self, shm: RawSharedMemory, b64_shm: B64SharedMemory, current_frame: np.ndarray | None, initialized: bool
    ) -> tuple[np.ndarray | None, bool, bool]:
        """
        Generic method to pull the latest frame from a shared memory and notify readiness.

        Args:
            shm (RawSharedMemory): The shared memory to pull the raw frame from.
            b64_shm (B64SharedMemory): The shared memory to notify readiness.
            current_frame (np.ndarray | None): The current frame stored in the core.
            initialized (bool): Flag indicating if the core has been initialized.

        Returns:
            new_frame (np.ndarray | None): The latest frame pulled from shared memory.
            initialized (bool): Flag indicating if the core has been initialized.
            new_received (bool): Flag indicating if a NEW frame was actually received in this call.
        """

        t_new_frame = current_frame
        t_received = False
        while not shm.empty():
            t_new_frame = shm.get()
            t_received = True

        if t_new_frame is not None and not initialized:
            b64_shm.put("INITIALIZED")
            initialized = True

        return t_new_frame, initialized, t_received

    def _preprocess_event_frame(self, frame: np.ndarray) -> np.ndarray:
        """
        Method to preprocess an event camera frame by converting to grayscale and applying median filters.

        Args:
            frame (np.ndarray): The raw event camera frame.

        Returns:
            gray_frame (np.ndarray): The preprocessed and filtered grayscale frame ready for corner detection.
        """

        # Generate a gray frame of the given event frame
        t_gray_frame = bgr2gray_cv(frame)

        # Median filter to reduce noise while preserving edges (important for corner detection)
        t_gray_frame = cv2.medianBlur(t_gray_frame, 3)

        return t_gray_frame

    def _process_frame(
        self, frame: np.ndarray, sensor_type: str
    ) -> tuple[str | None, np.ndarray | None, np.ndarray | None, list | None, np.ndarray | None]:
        """
        Method to process a single frame for corner detection and FOV management.

        Args:
            frame (np.ndarray): The raw frame to be processed.
            sensor_type (str): The type of sensor ("rgb" or "event") to determine processing steps.

        Returns:
            processed_frame_b64 (str | None): The base64-encoded processed frame for display.
            corners (np.ndarray | None): The corner coordinates if detected, None otherwise.
            corner_ids (np.ndarray | None): The identifiers of the detected corners.
            marker_corners (list | None): Raw ArUco marker corner arrays for drawing.
            marker_ids (np.ndarray | None): The identifiers of the detected ArUco markers.
        """

        # Preprocess the rgb and event frame and store it for further processing
        if sensor_type == "event":
            t_preprocessed_frame = self._preprocess_event_frame(frame)
        else:
            t_preprocessed_frame = bgr2gray_cv(frame)

        # Detect, refine and draw corners on the original frame
        frame, t_corners, t_corner_ids, t_marker_corners, t_marker_ids = self._detect_corners(
            t_preprocessed_frame, frame.copy()
        )

        # Update and overlay the FOV mask
        frame = self._manage_fov_mask(frame, sensor_type, t_corners)

        # Generate the processed frame
        t_processed_frame_b64 = self.cv2_to_b64_converter_instance.convert(
            resize_image_cv(frame, self.__image_width, self.__image_display_height)
        )

        return t_processed_frame_b64, t_corners, t_corner_ids, t_marker_corners, t_marker_ids

    def _detect_corners(
        self, preprocessed_frame: np.ndarray, original_frame: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray | None, np.ndarray | None]:
        """
        Method to detect, refine and draw Charuco board corners in a preprocessed frame.

        Args:
            preprocessed_frame (np.ndarray): The grayscale or binary frame to detect corners in.
            original_frame (np.ndarray): The original BGR frame to draw corners on.

        Returns:
            drawn_frame (np.ndarray): The frame with drawn corners.
            corners (np.ndarray | None): The corner coordinates if successful.
            corner_ids (np.ndarray | None): The identifiers of the detected corners.
        """

        # Find Charuco corners in the preprocessed frame
        t_success, t_corners, t_ids, t_marker_corners, t_marker_ids = self.charuco_board_handler.find_corners(
            preprocessed_frame
        )
        t_corner_ids = None

        if t_success:
            t_corner_ids = t_ids
            original_frame = self.charuco_board_handler.draw_corners(original_frame, t_corners, t_corner_ids)

            if t_marker_corners is not None and len(t_marker_corners) > 0:
                original_frame = self.charuco_board_handler.draw_markers(
                    original_frame, t_marker_corners, t_marker_ids
                )

        return original_frame, t_corners, t_corner_ids, t_marker_corners, t_marker_ids

    def _manage_fov_mask(self, frame: np.ndarray, sensor_type: str, corners: np.ndarray | None) -> np.ndarray:
        """
        Method to manage the FOV mask by updating it with new corners and overlaying it on the frame.
        Draws the FOV coverage with green circles to indicate locations of detected corners.

        Args:
            frame (np.ndarray): The current frame.
            sensor_type (str): The type of sensor ("rgb" or "event").
            corners (np.ndarray | None): The detected corners.

        Returns:
            frame (np.ndarray): The frame with the FOV mask overlaid.
        """

        # Get the current FOV mask (event or rgb)
        t_fov_mask = self.rgb_fov_mask if sensor_type == "rgb" else self.event_fov_mask

        # Update FOV coverage if corners are detected
        if corners is not None:

            # Initialize the FOV mask if it doesn't exist yet
            if t_fov_mask is None:
                t_fov_mask = np.zeros((*frame.shape[:2], 4), dtype=np.uint8)

            # Perform the FOV update
            t_fov_update = visualize_fov_coverage(frame.shape[:2], corners)
            t_fov_mask = cv2.addWeighted(t_fov_mask, 1.0, t_fov_update, 1.0, 0)

            # Store the updated mask
            if sensor_type == "rgb":
                self.rgb_fov_mask = t_fov_mask
            else:
                self.event_fov_mask = t_fov_mask

        # Overlay the FOV mask on the frame if it exists
        if t_fov_mask is not None:
            t_overlay = t_fov_mask[:, :, :3]
            t_alpha = t_fov_mask[:, :, 3] / 255.0
            for t_channel in range(3):
                frame[:, :, t_channel] = frame[:, :, t_channel] * (1 - t_alpha) + t_overlay[:, :, t_channel] * t_alpha

        return frame

    def _is_collinear(self, object_points: np.ndarray) -> bool:
        """
        Method to check whether a set of object points is collinear (all lie on a straight line along x or y).

        Args:
            object_points (np.ndarray): The object points to check, shaped (N, 2) or (N, 3).

        Returns:
            collinear (bool): True if all points share the same x-coordinate or the same y-coordinate.
        """

        t_is_line_x = np.allclose(object_points[:, 0], object_points[0, 0])
        t_is_line_y = np.allclose(object_points[:, 1], object_points[0, 1])

        return t_is_line_x or t_is_line_y

    def _collect_rgb_intrinsic_sample(self, corners: np.ndarray | None, ids: np.ndarray | None) -> tuple[bool, bool]:
        """
        Method to collect a valid RGB camera frame for intrinsic calibration if corners are not collinear.

        Args:
            corners (np.ndarray | None): The detected corners in the RGB frame.
            ids (np.ndarray | None): The identifiers of the detected corners.

        Returns:
            detected (bool): True if >= 4 corners were found (sufficient for a calibration attempt).
            usable (bool): True if the pattern was not collinear and the sample was added.
        """

        if corners is None or len(corners) < 4:
            return False, False

        t_object_points = self.charuco_board_handler.get_object_points(ids)

        if not self._is_collinear(t_object_points):
            self.rgb_image_points.append(corners)
            self.object_points_rgb.append(t_object_points)
            print_info(f"Captured valid RGB image for intrinsic calibration. Sample: {len(self.rgb_image_points)}")
            return True, True
        else:
            print_info("Skipping RGB sample: Points are collinear (straight line).")
            return True, False

    def _collect_event_intrinsic_sample(self, corners: np.ndarray | None, ids: np.ndarray | None) -> tuple[bool, bool]:
        """
        Method to collect a valid event camera frame for intrinsic calibration if corners are not collinear.

        Args:
            corners (np.ndarray | None): The detected corners in the event frame.
            ids (np.ndarray | None): The identifiers of the detected corners.

        Returns:
            detected (bool): True if >= 4 corners were found (sufficient for a calibration attempt).
            usable (bool): True if the pattern was not collinear and the sample was added.
        """

        if corners is None or len(corners) < 4:
            return False, False

        t_object_points = self.charuco_board_handler.get_object_points(ids)

        if not self._is_collinear(t_object_points):
            self.event_image_points.append(corners)
            self.object_points_event.append(t_object_points)
            print_info(f"Captured valid event image for intrinsic calibration. Sample: {len(self.event_image_points)}")
            return True, True
        else:
            print_info("Skipping event sample: Points are collinear (straight line).")
            return True, False

    def _collect_stereo_sample(
        self,
        corners_rgb: np.ndarray | None,
        ids_rgb: np.ndarray | None,
        corners_event: np.ndarray | None,
        ids_event: np.ndarray | None,
    ) -> tuple[bool, bool]:
        """
        Method to collect synchronized samples for stereo calibration by matching detected corners from both sensors.
        It ensures that the same physical points are matched by using the corner IDs, and checks for collinearity.

        Args:
            corners_rgb (np.ndarray | None): The detected corners in the RGB frame.
            ids_rgb (np.ndarray | None): The identifiers of the detected corners in the RGB frame.
            corners_event (np.ndarray | None): The detected corners in the event frame.
            ids_event (np.ndarray | None): The identifiers of the detected corners in the event frame

        Returns:
            detected (bool): True if both cameras had >= 4 common corner IDs.
            usable (bool): True if the common pattern was not collinear and the pair was added.
        """

        if corners_rgb is None or corners_event is None:
            return False, False

        # Find common IDs to ensure we are matching the same physical points
        t_ids_rgb_flat = ids_rgb.flatten()
        t_ids_event_flat = ids_event.flatten()
        t_common_ids = np.intersect1d(t_ids_rgb_flat, t_ids_event_flat)

        if len(t_common_ids) < 4:
            return False, False

        # Ensure correct ordering: get indices of common IDs in each detected IDs array
        t_rgb_indices = [np.where(t_ids_rgb_flat == i)[0][0] for i in t_common_ids]
        t_event_indices = [np.where(t_ids_event_flat == i)[0][0] for i in t_common_ids]
        t_common_corners_rgb = corners_rgb[t_rgb_indices]
        t_common_corners_event = corners_event[t_event_indices]

        # t_common_ids to get object points for BOTH sensors in stereo calibration
        t_common_object_points = self.charuco_board_handler.get_object_points(t_common_ids)

        # Check for collinearity (straight lines) in object points
        if not self._is_collinear(t_common_object_points):
            self.rgb_image_points_synced.append(t_common_corners_rgb)
            self.event_image_points_synced.append(t_common_corners_event)
            self.object_points_synced.append(t_common_object_points)
            print_info(
                f"Captured valid synchronized image pair for extrinsic calibration. Common points: {len(t_common_ids)}. Sample: {len(self.rgb_image_points_synced)}"
            )
            return True, True
        else:
            print_info("Skipping synchronized pair: Points are collinear (straight line).")
            return True, False

    def _start_robot_phase(self, camera_name: str) -> None:
        """
        Method to start the robot-assisted calibration phase by initializing the UR5eCalibrator and running it in a separate thread.

        Args:
            camera_name (str): The name of the camera for which to perform robot-assisted calibration.

        Returns:
            ():
        """

        # Instantiate the UR5eCalibrator and reset the position reached event
        t_calibrator = UR5eCalibrator(
            camera_name, self.__camera_config, self.__stereo_calibration_config, self.__target_square_size
        )
        self.robot_position_reached.clear()

        # Instantiate a separate thread to avoid blocking the main loop and start it
        self.robot_thread = threading.Thread(
            target=t_calibrator.perform_calibration,
            args=(self.robot_position_reached,),
            daemon=True,
        )
        self.robot_thread.start()

        return

    def _check_phase_transition(self) -> None:
        """
        Method to check whether the current robot thread has finished and advances to the next
        calibration phase. Called every loop iteration in robot-active mode so that
        transitions fire even when no further position-reached signal arrives.

        Args:
            ():

        Returns:
            ():
        """

        if self.robot_thread is None or self.robot_thread.is_alive():
            return

        self.robot_thread = None

        # 1st calibration phase (RGB intrinsic)
        if self.calibration_phase == CalibrationPhase.RGB_INTRINSIC:
            print_info("Phase 1 complete. Starting Phase 2: Prophesee intrinsic calibration")
            self.calibration_phase = CalibrationPhase.EVENT_INTRINSIC
            # Reset RGB visualization before entering event-only phase
            self.latest_rgb_corners = None
            self.latest_rgb_corner_ids = None
            self.latest_rgb_marker_corners = None
            self.latest_rgb_marker_ids = None
            self.rgb_fov_mask = None
            self._start_robot_phase("prophesee")

        # 2nd calibration phase (Event intrinsic)
        elif self.calibration_phase == CalibrationPhase.EVENT_INTRINSIC:
            print_info("Phase 2 complete. Starting Phase 3: Stereo extrinsic calibration")
            self.calibration_phase = CalibrationPhase.STEREO_EXTRINSIC
            # Reset event visualization before entering stereo phase
            self.latest_event_corners = None
            self.latest_event_corner_ids = None
            self.latest_event_marker_corners = None
            self.latest_event_marker_ids = None
            self.event_fov_mask = None
            self._start_robot_phase("ueye")

        # 3rd calibration phase (Stereo extrinsic)
        elif self.calibration_phase == CalibrationPhase.STEREO_EXTRINSIC:
            print_info("Phase 3 complete. Robot-assisted calibration finished.")
            self.stereo_calibration_active.clear()

        return

    def _synchronized_calibration_processing(self) -> None:
        """
        Method to perform synchronized processing of RGB and event frames for calibration.
        This should be called when the stereo calibration is active and both frames are available.

        Args:
            ():

        Returns:
            ():
        """

        # Determine which cameras should perform corner detection based on the current phase
        t_detect_rgb = self.calibration_phase in (
            CalibrationPhase.NO_ROBOT,
            CalibrationPhase.RGB_INTRINSIC,
            CalibrationPhase.STEREO_EXTRINSIC,
        )
        t_detect_event = self.calibration_phase in (
            CalibrationPhase.NO_ROBOT,
            CalibrationPhase.EVENT_INTRINSIC,
            CalibrationPhase.STEREO_EXTRINSIC,
        )

        # Process frames: only detect corners for active cameras in the current phase
        if t_detect_rgb:
            self.processed_rgb_b64, t_corners_rgb, t_ids_rgb, t_marker_corners_rgb, t_marker_ids_rgb = (
                self._process_frame(self.latest_rgb_frame.copy(), "rgb")
            )
        else:
            self.processed_rgb_b64 = self.cv2_to_b64_converter_instance.convert(
                resize_image_cv(self.latest_rgb_frame.copy(), self.__image_width, self.__image_display_height)
            )
            t_corners_rgb, t_ids_rgb, t_marker_corners_rgb, t_marker_ids_rgb = None, None, None, None

        if t_detect_event:
            self.processed_event_b64, t_corners_event, t_ids_event, t_marker_corners_event, t_marker_ids_event = (
                self._process_frame(self.latest_event_frame.copy(), "event")
            )
        else:
            self.processed_event_b64 = self.cv2_to_b64_converter_instance.convert(
                resize_image_cv(self.latest_event_frame.copy(), self.__image_width, self.__image_display_height)
            )
            t_corners_event, t_ids_event, t_marker_corners_event, t_marker_ids_event = None, None, None, None

        # Store the latest detected corners for persistent display
        self.latest_rgb_corners = t_corners_rgb
        self.latest_event_corners = t_corners_event
        self.latest_rgb_corner_ids = t_ids_rgb
        self.latest_event_corner_ids = t_ids_event
        self.latest_rgb_marker_corners = t_marker_corners_rgb
        self.latest_rgb_marker_ids = t_marker_ids_rgb
        self.latest_event_marker_corners = t_marker_corners_event
        self.latest_event_marker_ids = t_marker_ids_event

        # Collect calibration data based on the current phase
        # All phases at once if no robot
        if self.calibration_phase == CalibrationPhase.NO_ROBOT:
            self._collect_rgb_intrinsic_sample(t_corners_rgb, t_ids_rgb)
            self._collect_event_intrinsic_sample(t_corners_event, t_ids_event)
            self._collect_stereo_sample(t_corners_rgb, t_ids_rgb, t_corners_event, t_ids_event)
            t_rgb_ann = self.latest_rgb_frame.copy()
            if t_corners_rgb is not None:
                t_rgb_ann = self.charuco_board_handler.draw_corners(t_rgb_ann, t_corners_rgb, t_ids_rgb)
                if t_marker_corners_rgb is not None and len(t_marker_corners_rgb) > 0:
                    t_rgb_ann = self.charuco_board_handler.draw_markers(
                        t_rgb_ann, t_marker_corners_rgb, t_marker_ids_rgb
                    )
            t_evt_ann = self.latest_event_frame.copy()
            if t_corners_event is not None:
                t_evt_ann = self.charuco_board_handler.draw_corners(t_evt_ann, t_corners_event, t_ids_event)
                if t_marker_corners_event is not None and len(t_marker_corners_event) > 0:
                    t_evt_ann = self.charuco_board_handler.draw_markers(
                        t_evt_ann, t_marker_corners_event, t_marker_ids_event
                    )

        # 1st phase: RGB intrinsic only
        elif self.calibration_phase == CalibrationPhase.RGB_INTRINSIC:
            self._collect_rgb_intrinsic_sample(t_corners_rgb, t_ids_rgb)
            t_rgb_ann = self.latest_rgb_frame.copy()
            if t_corners_rgb is not None:
                t_rgb_ann = self.charuco_board_handler.draw_corners(t_rgb_ann, t_corners_rgb, t_ids_rgb)
                if t_marker_corners_rgb is not None and len(t_marker_corners_rgb) > 0:
                    t_rgb_ann = self.charuco_board_handler.draw_markers(
                        t_rgb_ann, t_marker_corners_rgb, t_marker_ids_rgb
                    )

        # 2nd phase: Event intrinsic only
        elif self.calibration_phase == CalibrationPhase.EVENT_INTRINSIC:
            self._collect_event_intrinsic_sample(t_corners_event, t_ids_event)
            t_evt_ann = self.latest_event_frame.copy()
            if t_corners_event is not None:
                t_evt_ann = self.charuco_board_handler.draw_corners(t_evt_ann, t_corners_event, t_ids_event)
                if t_marker_corners_event is not None and len(t_marker_corners_event) > 0:
                    t_evt_ann = self.charuco_board_handler.draw_markers(
                        t_evt_ann, t_marker_corners_event, t_marker_ids_event
                    )

        # 3rd phase: Stereo extrinsic only
        elif self.calibration_phase == CalibrationPhase.STEREO_EXTRINSIC:
            self._collect_stereo_sample(t_corners_rgb, t_ids_rgb, t_corners_event, t_ids_event)
            t_rgb_ann = self.latest_rgb_frame.copy()
            if t_corners_rgb is not None:
                t_rgb_ann = self.charuco_board_handler.draw_corners(t_rgb_ann, t_corners_rgb, t_ids_rgb)
                if t_marker_corners_rgb is not None and len(t_marker_corners_rgb) > 0:
                    t_rgb_ann = self.charuco_board_handler.draw_markers(
                        t_rgb_ann, t_marker_corners_rgb, t_marker_ids_rgb
                    )

            t_evt_ann = self.latest_event_frame.copy()
            if t_corners_event is not None:
                t_evt_ann = self.charuco_board_handler.draw_corners(t_evt_ann, t_corners_event, t_ids_event)
                if t_marker_corners_event is not None and len(t_marker_corners_event) > 0:
                    t_evt_ann = self.charuco_board_handler.draw_markers(
                        t_evt_ann, t_marker_corners_event, t_marker_ids_event
                    )

        # Set the b64 encoded processed frames for display, use shared memory
        if self.processed_rgb_b64:
            self.rgb_b64_shm.put(self.processed_rgb_b64)
        if self.processed_event_b64:
            self.event_b64_shm.put(self.processed_event_b64)

        return

    def _calculate_final_calibration_results(self) -> None:
        """
        Method to calculate the final calibration results (intrinsic and extrinsic parameters) after the calibration process is stopped.

        Args:
            ():

        Returns:
            ():
        """

        # ##### Save Results #####
        t_output_path = Path(__file__).parents[2] / "data"

        # Collect calibration results
        t_k_rgb: np.ndarray | None = None
        t_dist_rgb: np.ndarray | None = None
        t_error_rgb: float | None = None
        t_k_event: np.ndarray | None = None
        t_dist_event: np.ndarray | None = None
        t_error_event: float | None = None
        t_R: np.ndarray | None = None
        t_T: np.ndarray | None = None
        t_error_stereo: float | None = None

        try:
            # ##### Intrinsic #####
            # RGB Calibration
            if len(self.rgb_image_points) < self.__min_corners_for_calibration:
                print_error(f"Not enough RGB points for intrinsic calibration: {len(self.rgb_image_points)}")

            else:
                print_info("Starting RGB intrinsic calibration")
                t_rgb_shape = self.latest_rgb_frame.shape[:2]

                t_error_rgb, t_k_rgb, t_dist_rgb, _, _ = calculate_intrinsic_parameters(
                    self.object_points_rgb,
                    self.rgb_image_points,
                    t_rgb_shape,
                    self.__reprojection_error_threshold,
                    self.__min_corners_for_calibration,
                    self.__rgb_initial_camera_matrix,
                )
                print_info(f"Reprojection error (RGB): {t_error_rgb}")

                save_intrinsics_to_json(
                    str(t_output_path / self.__rgb_intrinsics_file_path),
                    t_k_rgb,
                    t_dist_rgb,
                    tuple(t_rgb_shape[::-1]),
                    t_error_rgb,
                )

            # Event Calibration
            if len(self.event_image_points) < self.__min_corners_for_calibration:
                print_error(f"Not enough event points for intrinsic calibration: {len(self.event_image_points)}")
            else:
                print_info("Starting Event intrinsic calibration")
                t_event_shape = self.latest_event_frame.shape[:2]
                t_error_event, t_k_event, t_dist_event, _, _ = calculate_intrinsic_parameters(
                    self.object_points_event,
                    self.event_image_points,
                    t_event_shape,
                    self.__reprojection_error_threshold,
                    self.__min_corners_for_calibration,
                    self.__event_initial_camera_matrix,
                )
                print_info(f"Reprojection error (Event): {t_error_event}")

                save_intrinsics_to_json(
                    str(t_output_path / self.__event_intrinsics_file_path),
                    t_k_event,
                    t_dist_event,
                    tuple(t_event_shape[::-1]),
                    t_error_event,
                )

            # ##### Extrinsic #####
            if (
                len(self.rgb_image_points_synced) < self.__min_corners_for_calibration
                or len(self.event_image_points_synced) < self.__min_corners_for_calibration
            ):
                print_error(
                    f"Not enough synchronized points for extrinsic calibration: {len(self.rgb_image_points_synced)} pairs"
                )

            else:
                print_info("Starting extrinsic calibration")

                # Convert lists to float32 arrays/lists as required by OpenCV for stereo calibration
                t_obj_pts_stereo = [np.array(pts, dtype=np.float32) for pts in self.object_points_synced]
                t_rgb_img_pts_stereo = [
                    np.array(pts, dtype=np.float32).reshape(-1, 1, 2) for pts in self.rgb_image_points_synced
                ]
                t_event_img_pts_stereo = [
                    np.array(pts, dtype=np.float32).reshape(-1, 1, 2) for pts in self.event_image_points_synced
                ]

                (
                    t_error_stereo,
                    t_R,
                    t_T,
                    _,
                    _,
                ) = calculate_stereo_parameters(
                    t_obj_pts_stereo,
                    t_rgb_img_pts_stereo,
                    t_event_img_pts_stereo,
                    t_k_rgb,
                    t_dist_rgb,
                    t_k_event,
                    t_dist_event,
                    t_rgb_shape,
                    self.__reprojection_error_threshold,
                    self.__min_corners_for_calibration,
                )
                print_info(f"Reprojection error (Stereo): {t_error_stereo}")

                # Save extrinsic results
                save_extrinsics_to_json(str(t_output_path / self.__extrinsics_file_path), t_R, t_T, t_error_stereo)

        except Exception as e:
            print_error(f"Error during calibration: {e}")

        return

    # ##### PUBLIC METHODS #####
    def run(self) -> None:
        """
        Main method that runs the stereo calibration core, continuously pulling frames, processing them, and managing the calibration state.

        Args:
            ():

        Returns:
            ():
        """

        # Main loop to continuously pull frames and process them for calibration if active
        while True:

            self._check_calibration_reset()

            # 1. Pull latest available RGB and event frames
            self.latest_rgb_frame, self.rgb_initialized, t_new_rgb_received = self._pull_latest_frame(
                self.rgb_raw_shm, self.rgb_b64_shm, self.latest_rgb_frame, self.rgb_initialized
            )
            self.latest_event_frame, self.event_initialized, t_new_event_received = self._pull_latest_frame(
                self.event_raw_shm, self.event_b64_shm, self.latest_event_frame, self.event_initialized
            )

            # 2. Continuous display update with FOV mask - only update if NEW frames were received
            if self.latest_rgb_frame is not None and t_new_rgb_received:
                t_rgb_display = self._manage_fov_mask(self.latest_rgb_frame.copy(), "rgb", None)

                # Draw persistent corners if available
                if self.latest_rgb_corners is not None:
                    t_rgb_display = self.charuco_board_handler.draw_corners(
                        t_rgb_display, self.latest_rgb_corners, self.latest_rgb_corner_ids
                    )
                    if self.latest_rgb_marker_corners is not None and len(self.latest_rgb_marker_corners) > 0:
                        t_rgb_display = self.charuco_board_handler.draw_markers(
                            t_rgb_display, self.latest_rgb_marker_corners, self.latest_rgb_marker_ids
                        )
                    cv2.drawChessboardCorners(
                        t_rgb_display, (1, len(self.latest_rgb_corners)), self.latest_rgb_corners, True
                    )
                t_processed_rgb_b64 = self.cv2_to_b64_converter_instance.convert(
                    resize_image_cv(t_rgb_display, self.__image_width, self.__image_display_height)
                )
                self.rgb_b64_shm.put(t_processed_rgb_b64)

            if self.latest_event_frame is not None and t_new_event_received:
                t_event_display = self._manage_fov_mask(self.latest_event_frame.copy(), "event", None)

                # Draw persistent corners if available
                if self.latest_event_corners is not None:
                    t_event_display = self.charuco_board_handler.draw_corners(
                        t_event_display, self.latest_event_corners, self.latest_event_corner_ids
                    )
                    if self.latest_event_marker_corners is not None and len(self.latest_event_marker_corners) > 0:
                        t_event_display = self.charuco_board_handler.draw_markers(
                            t_event_display, self.latest_event_marker_corners, self.latest_event_marker_ids
                        )

                    cv2.drawChessboardCorners(
                        t_event_display, (1, len(self.latest_event_corners)), self.latest_event_corners, True
                    )
                t_processed_event_b64 = self.cv2_to_b64_converter_instance.convert(
                    resize_image_cv(t_event_display, self.__image_width, self.__image_display_height)
                )
                self.event_b64_shm.put(t_processed_event_b64)

            self.charuco_board_handler.update_board_parameters(
                square_length=self.__target_square_size.value,
                marker_length=self.__target_square_size.value * self.__target_marker_size_fraction,
            )

            self.charuco_board_handler.update_display(
                calibration_active=self.stereo_calibration_active.is_set(),
                width=self.__target_display_size[0],
                height=self.__target_display_size[1],
                margin=self.__target_margin,
                overlay_opacity=self.__target_dim_alpha,
            )

            # Check if generation of calibration targets was requested
            if self.generate_targets_triggered.is_set():
                print_info("Generation of calibration targets requested")

                # Generate Arduino bitmap and save header
                self.charuco_board_handler.generate_arduino_bitmap(
                    output_path=self.__header_output_path,
                    width=self.__target_bitmap_size[0],
                    height=self.__target_bitmap_size[1],
                    margin=self.__target_margin,
                )

                # Generate toggling video
                self.charuco_board_handler.generate_toggling_video(
                    output_path=self.__video_output_path,
                    width=self.__target_display_size[0],
                    height=self.__target_display_size[1],
                    margin=self.__target_margin,
                    duration_sec=self.__target_video_duration,
                    fps=self.__target_video_fps,
                    toggle_freq_hz=self.__target_frequency,
                    overlay_opacity=self.__target_dim_alpha,
                )

                print_success("Generation of calibration targets completed")
                self.generate_targets_triggered.clear()

            # 3. Synchronized processing for calibration
            if self.stereo_calibration_active.is_set():
                if not self.calibration_was_active:
                    self.calibration_was_active = True
                    self.capture_timer_instance.reset()

                    # Initialize calibration phase by checking robot connectivity asynchronously
                    # to avoid blocking the main loop / freezing the GUI
                    t_robot_ip = self.__stereo_calibration_config.get("ur5e", "robot_ip")
                    self.calibration_phase = CalibrationPhase.CHECKING_ROBOT
                    self.robot_ping_complete = False
                    self.robot_reachable = False
                    threading.Thread(
                        target=self._ping_robot_async,
                        args=(t_robot_ip,),
                        daemon=True,
                    ).start()

                # If still checking robot connectivity, wait for the ping to complete
                if self.calibration_phase == CalibrationPhase.CHECKING_ROBOT:
                    if self.robot_ping_complete:
                        if self.robot_reachable:
                            print_info("Robot connected. Starting Phase 1: RGB intrinsic calibration")
                            self.calibration_phase = CalibrationPhase.RGB_INTRINSIC
                            self._start_robot_phase("ueye")
                        else:
                            print_info("No robot connected. Running manual calibration.")
                            self.calibration_phase = CalibrationPhase.NO_ROBOT
                            self.capture_timer_instance.reset()

                # Choose capture mode based on whether a robot is driving the process
                t_robot_active = self.calibration_phase not in (
                    None,
                    CalibrationPhase.NO_ROBOT,
                    CalibrationPhase.CHECKING_ROBOT,
                )

                if t_robot_active:
                    # Robot-driven capture: triggered by the position-reached signal (DO2)
                    # Hide the capture timer in the GUI (sentinel value -1)
                    self.next_capture_timer.value = -1

                    # Check for phase transitions every iteration (handles the case where the
                    # robot thread finishes without a further position-reached signal)
                    self._check_phase_transition()

                    # Non-blocking settle delay: record when position-reached first fires
                    if self.robot_position_reached.is_set() and self.position_reached_time is None:
                        self.position_reached_time = time.monotonic()
                        self.robot_position_reached.clear()

                    # Process after the settle time has elapsed (without blocking the display loop)
                    if (
                        self.position_reached_time is not None
                        and time.monotonic() - self.position_reached_time >= self.__stop_command_delay
                    ):
                        # Process latest frames and get detection results
                        if self.latest_rgb_frame is not None and self.latest_event_frame is not None:
                            self._synchronized_calibration_processing()
                        self.position_reached_time = None

                elif self.calibration_phase == CalibrationPhase.NO_ROBOT:
                    # Manual (no robot) capture: timer-driven
                    self.next_capture_timer.value = self.capture_timer_instance.get_remaining_time()

                    if self.capture_timer_instance.has_elapsed():
                        self.capture_timer_instance.update_last_time()

                        # Process latest frames and get detection results
                        if self.latest_rgb_frame is not None and self.latest_event_frame is not None:
                            self._synchronized_calibration_processing()

                else:
                    # CHECKING_ROBOT or unknown phase: hide timer, do nothing
                    self.next_capture_timer.value = -1

            # Wait for a short time to avoid busy waiting and allow other processes to run
            time.sleep(0.01)

        return


def core_worker(
    event_raw_shm: RawSharedMemory,
    rgb_raw_shm: RawSharedMemory,
    event_b64_shm: B64SharedMemory,
    rgb_b64_shm: B64SharedMemory,
    stereo_calibration_active: EventProxy,
    generate_targets_triggered: EventProxy,
    next_capture_timer: ValueProxy,
    target_square_size: ValueProxy,
    current_calibration_phase: ValueProxy,
) -> None:
    """
    Worker function for the stereo calibration core process.

    Args:
        event_raw_shm (RawSharedMemory): Shared memory for raw event camera frames.
        rgb_raw_shm (RawSharedMemory): Shared memory for raw RGB camera frames.
        event_b64_shm (B64SharedMemory): Shared memory for base64-encoded event camera frames.
        rgb_b64_shm (B64SharedMemory): Shared memory for base64-encoded RGB camera frames.
        stereo_calibration_active (EventProxy): Event to signal if stereo calibration is active.
        generate_targets_triggered (EventProxy): Event to signal if target generation was triggered.
        next_capture_timer (ValueProxy): Shared value to indicate time until next capture.
        target_square_size (ValueProxy): Shared value to indicate the size of the target square in meters.
        current_calibration_phase (ValueProxy): Shared value to communicate the current calibration phase to the GUI.

    Returns:
        ():
    """

    # Run the main stereo calibration in a separate thread from this worker process
    try:
        t_core = StereoCalibration(
            event_raw_shm,
            rgb_raw_shm,
            event_b64_shm,
            rgb_b64_shm,
            stereo_calibration_active,
            generate_targets_triggered,
            next_capture_timer,
            target_square_size,
            current_calibration_phase,
        )
        t_core.run()
    except KeyboardInterrupt:
        pass

    return


class CoreStereoCalibration:
    """Class that provides all core functionality for the stereo calibration process."""

    def __init__(self, gui_instance: StereoCalibrationGUI | None = None) -> None:

        # 0. Store reference to GUI instance for shared memory access and communication
        self.__gui_instance: StereoCalibrationGUI | None = gui_instance

        # 1. New process for uEyeWorker (uEye camera capture) and start it
        self.__ueye_process = multiprocessing.Process(
            target=ueye_worker,
            args=(
                self.__gui_instance.rgb_raw_shared_memory,
                self.__gui_instance.synchronization_queue,
                self.__gui_instance.rgb_recording_path,
                self.__gui_instance.rgb_recording_active,
                self.__gui_instance.rgb_camera_ready,
                "camera_stereo_calibration.ini",
            ),
        )
        self.__ueye_process.start()

        # 2. New process for PropheseeWorker (Prophesee event camera capture) and start it
        self.__prophesee_process = multiprocessing.Process(
            target=prophesee_worker,
            args=(
                self.__gui_instance.event_raw_shared_memory,
                self.__gui_instance.synchronization_queue,
                self.__gui_instance.rgb_camera_ready,
                self.__gui_instance.event_recording_path,
                self.__gui_instance.event_recording_active,
                "camera_stereo_calibration.ini",
            ),
        )
        self.__prophesee_process.start()

        # 3. New process for StereoCalibration(Processing) and start it
        self.__stereo_calibration_process = multiprocessing.Process(
            target=core_worker,
            args=(
                self.__gui_instance.event_raw_shared_memory,
                self.__gui_instance.rgb_raw_shared_memory,
                self.__gui_instance.event_frame_shared_memory,
                self.__gui_instance.rgb_frame_shared_memory,
                self.__gui_instance.stereo_calibration_active,
                self.__gui_instance.generate_targets_triggered,
                self.__gui_instance.next_capture_timer,
                self.__gui_instance.target_square_size,
                self.__gui_instance.current_calibration_phase,
            ),
        )
        self.__stereo_calibration_process.start()

        return

    # ##### GETTER #####
    @property
    def ueye_process(self) -> multiprocessing.Process:
        """
        Getter for the attribute '__ueye_process'.

        Args:
            ():

        Returns:
            ueye_process (multiprocessing.Process): The attribute '__ueye_process'.
        """

        return self.__ueye_process

    @property
    def prophesee_process(self) -> multiprocessing.Process:
        """
        Getter for the attribute '__prophesee_process'.

        Args:
            ():

        Returns:
            prophesee_process (multiprocessing.Process): The attribute '__prophesee_process'.
        """

        return self.__prophesee_process

    @property
    def stereo_calibration_process(self) -> multiprocessing.Process:
        """
        Getter for the attribute '__stereo_calibration_process'.

        Args:
            ():

        Returns:
            stereo_calibration_process (multiprocessing.Process): The attribute '__stereo_calibration_process'.
        """

        return self.__stereo_calibration_process

    # ##### SETTER #####

    # ##### PRIVATE METHODS #####

    # ##### PUBLIC METHODS #####
    def ueye_running(self) -> bool:
        """
        Method to check if the uEye worker process is still running.

        Args:
            ():

        Returns:
            (bool): True if the worker is running, False otherwise.
        """

        return self.ueye_process.is_alive()

    def prophesee_running(self) -> bool:
        """
        Method to check if the prophesee worker process is still running.

        Args:
            ():

        Returns:
            (bool): True if the worker is running, False otherwise.
        """

        return self.prophesee_process.is_alive()

    def terminate_processes(self) -> None:
        """
        Method to terminate all running processes when the application is closed.

        Args:
            ():

        Returns:
            ():
        """

        self.ueye_process.terminate()
        self.prophesee_process.terminate()
        self.stereo_calibration_process.terminate()

        return
