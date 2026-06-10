# -*- coding: utf-8 -*-
"""
Filename: calibration.py
Author: Nico Hessenthaler
Date: 2026-06-05
Version: 1.0
Description:
    Module that provides utilities for the calibration of the event camera and the RGB camera of the sorting system.
License: Apache License Version 2.0
Contact: nico.hessenthaler@hs-heilbronn.de
"""

import configparser
import cv2
import datetime
from .image_processing import binary_threshold_cv, add_weighted_overlay_cv, gray2bgr_cv
import json
from math import radians, tan
from multiprocessing.managers import ValueProxy
import numpy as np
from .operating_system import print_info, print_error
from .optics import calculate_field_of_view_deg, calculate_sensor_dimensions_m
from pathlib import Path
from rtde_receive import RTDEReceiveInterface
import threading
import time
from .universal_robots import open_ur_script_file, send_urscript


class CharucoBoardHandler:
    """
    Class to handle Charuco board detection and storage of detector parameters.
    Persistent storage of the detector and board objects avoids re-initialization in every iteration.
    """

    def __init__(
        self,
        live_window_title: str,
        squares_x: int,
        squares_y: int,
        square_length: float,
        marker_length: float,
        dictionary_id: int = cv2.aruco.DICT_4X4_50,
    ) -> None:
        """
        Initializes the Charuco board handler with specific board parameters.

        Args:
            live_window_title (str): The title of the live window.
            squares_x (int): Number of squares in X direction (columns).
            squares_y (int): Number of squares in Y direction (rows).
            square_length (float): Chessboard square side length (in meters).
            marker_length (float): ArUco marker side length (in meters).
            dictionary_id (int): The ID of the ArUco dictionary used (e.g., cv2.aruco.DICT_4X4_50).
        """

        self.__squares_x = squares_x
        self.__squares_y = squares_y
        self.__square_length = square_length
        self.__marker_length = marker_length
        self.__dictionary_id = dictionary_id

        # Initialize detector components once
        self.__dictionary = cv2.aruco.getPredefinedDictionary(self.__dictionary_id)
        self.__parameters = cv2.aruco.DetectorParameters()
        self.__parameters.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
        self.__parameters.cornerRefinementMinAccuracy = 0.005
        self.__board = cv2.aruco.CharucoBoard(
            (self.__squares_x, self.__squares_y), self.__square_length, self.__marker_length, self.__dictionary
        )
        self.__detector = cv2.aruco.CharucoDetector(self.__board, detectorParams=self.__parameters)
        self.__board_image = None
        self.__bitmap_data = None

        # Display attributes
        self.__live_window_title = live_window_title
        self.__live_window_created = False
        self.__target_toggle = False
        self.__target_toggle_counter = 0

    # ##### GETTER #####
    @property
    def squares_x(self) -> int:
        """
        Getter for the attribute '__squares_x'.

        Args:
            ():

        Returns:
            squares_x (int): The attribute '__squares_x'.
        """

        return self.__squares_x

    @property
    def squares_y(self) -> int:
        """
        Getter for the attribute '__squares_y'.

        Args:
            ():

        Returns:
            squares_y (int): The attribute '__squares_y'.
        """

        return self.__squares_y

    @property
    def square_length(self) -> float:
        """
        Getter for the attribute '__square_length'.

        Args:
            ():

        Returns:
            square_length (float): The attribute '__square_length'.
        """

        return self.__square_length

    @property
    def marker_length(self) -> float:
        """
        Getter for the attribute '__marker_length'.

        Args:
            ():

        Returns:
            marker_length (float): The attribute '__marker_length'.
        """

        return self.__marker_length

    @property
    def dictionary(self) -> cv2.aruco.Dictionary:
        """
        Getter for the attribute '__dictionary'.

        Args:
            ():

        Returns:
            dictionary (cv2.aruco.Dictionary): The attribute '__dictionary'.
        """

        return self.__dictionary

    @property
    def parameters(self) -> cv2.aruco.DetectorParameters:
        """
        Getter for the attribute '__parameters'.

        Args:
            ():

        Returns:
            parameters (cv2.aruco.DetectorParameters): The attribute '__parameters'.
        """

        return self.__parameters

    @property
    def board(self) -> cv2.aruco.CharucoBoard:
        """
        Getter for the attribute '__board'.

        Args:
            ():

        Returns:
            board (cv2.aruco.CharucoBoard): The attribute '__board'.
        """

        return self.__board

    @property
    def detector(self) -> cv2.aruco.CharucoDetector:
        """
        Getter for the attribute '__detector'.

        Args:
            ():

        Returns:
            detector (cv2.aruco.CharucoDetector): The attribute '__detector'.
        """

        return self.__detector

    @property
    def board_image(self) -> np.ndarray:
        """
        Getter for the attribute '__board_image'.

        Args:
            ():

        Returns:
            board_image (np.ndarray): The attribute '__board_image'.
        """

        return self.__board_image

    @property
    def bitmap_data(self) -> list[str]:
        """
        Getter for the attribute '__bitmap_data'.

        Args:
            ():

        Returns:
            bitmap_data (list[str]): The attribute '__bitmap_data'.
        """

        return self.__bitmap_data

    @property
    def live_window_title(self) -> str:
        """
        Getter for the attribute '__live_window_title'.

        Args:
            ():

        Returns:
            live_window_title (str): The attribute '__live_window_title'.
        """

        return self.__live_window_title

    @property
    def live_window_created(self) -> bool:
        """
        Getter for the attribute '__live_window_created'.

        Args:
            ():

        Returns:
            live_window_created (bool): The attribute '__live_window_created'.
        """

        return self.__live_window_created

    @property
    def target_toggle(self) -> bool:
        """
        Getter for the attribute '__target_toggle'.

        Args:
            ():

        Returns:
            target_toggle (bool): The attribute '__target_toggle'.
        """

        return self.__target_toggle

    @property
    def target_toggle_counter(self) -> int:
        """
        Getter for the attribute '__target_toggle_counter'.

        Args:
            ():

        Returns:
            target_toggle_counter (int): The attribute '__target_toggle_counter'.
        """

        return self.__target_toggle_counter

    # ##### SETTER #####
    @square_length.setter
    def square_length(self, value: float) -> None:
        """
        Setter for the attribute '__square_length'.

        Args:
            value (float): The new value for the attribute '__square_length'.

        Returns:
            ():
        """

        self.__square_length = value

        return

    @marker_length.setter
    def marker_length(self, value: float) -> None:
        """
        Setter for the attribute '__marker_length'.

        Args:
            value (float): The new value for the attribute '__marker_length'.

        Returns:
            ():
        """

        self.__marker_length = value

        return

    @board.setter
    def board(self, value: cv2.aruco.CharucoBoard) -> None:
        """
        Setter for the attribute '__board'.

        Args:
            value (cv2.aruco.CharucoBoard): The new value for the attribute '__board'.

        Returns:
            ():
        """

        self.__board = value

        return

    @detector.setter
    def detector(self, value: cv2.aruco.CharucoDetector) -> None:
        """
        Setter for the attribute '__detector'.

        Args:
            value (cv2.aruco.CharucoDetector): The new value for the attribute '__detector'.

        Returns:
            ():
        """

        self.__detector = value

        return

    @board_image.setter
    def board_image(self, value: np.ndarray) -> None:
        """
        Setter for the attribute '__board_image'.

        Args:
            value (np.ndarray): The new value for the attribute '__board_image'.

        Returns:
            ():
        """

        self.__board_image = value

        return

    @bitmap_data.setter
    def bitmap_data(self, value: list[str]) -> None:
        """
        Setter for the attribute '__bitmap_data'.

        Args:
            value (list[str]): The new value for the attribute '__bitmap_data'.

        Returns:
            ():
        """

        self.__bitmap_data = value

        return

    @live_window_title.setter
    def live_window_title(self, value: str) -> None:
        """
        Setter for the attribute '__live_window_title'.

        Args:
            value (str): The new value for the attribute '__live_window_title'.

        Returns:
            ():
        """

        self.__live_window_title = value

        return

    @live_window_created.setter
    def live_window_created(self, value: bool) -> None:
        """
        Setter for the attribute '__live_window_created'.

        Args:
            value (bool): The new value for the attribute '__live_window_created'.

        Returns:
            ():
        """

        self.__live_window_created = value

        return

    @target_toggle.setter
    def target_toggle(self, value: bool) -> None:
        """
        Setter for the attribute '__target_toggle'.

        Args:
            value (bool): The new value for the attribute '__target_toggle'.

        Returns:
            ():
        """

        self.__target_toggle = value

        return

    @target_toggle_counter.setter
    def target_toggle_counter(self, value: int) -> None:
        """
        Setter for the attribute '__target_toggle_counter'.

        Args:
            value (int): The new value for the attribute '__target_toggle_counter'.

        Returns:
            ():
        """

        self.__target_toggle_counter = value

        return

    # ##### PRIVATE METHODS #####
    def _ensure_live_window_is_ready(self, calibration_active: bool) -> None:
        """
        Method to ensure that the live window is created and visible when calibration is active,
        and destroyed when calibration is not active.

        Args:
            calibration_active (bool): Flag indicating if the calibration process is currently active.

        Returns:
            ():
        """

        if calibration_active and not self.live_window_created:
            cv2.namedWindow(self.live_window_title, cv2.WINDOW_AUTOSIZE)
            self.live_window_created = True

        elif not calibration_active and self.live_window_created:
            self._close_live_window()
            self.live_window_created = False

        return

    def _close_live_window(self) -> None:
        """
        Method to close the live window and release resources.

        Args:
            ():

        Returns:
            ():
        """

        cv2.destroyWindow(self.live_window_title)

        return

    def _generate_board_image(self, width: int = 640, height: int = 480, margin: int = 10) -> None:
        """
        Method to generate a ChArUco board image of the specified size.

        Args:
            width (int): The required width of the generated image.
            height (int): The required height of the generated image.
            margin (int): The margin around the board in pixels.

        Returns:
            ():
        """

        # Calculate square size to fit the target resolution with margin
        # We use floor division to ensure the board fits within the dimensions
        t_square_size = min((width - 2 * margin) // self.squares_x, (height - 2 * margin) // self.squares_y)

        # Generate the board image using the internal board object
        # The generateImage method takes (outSize) as argument
        t_board_img = self.board.generateImage((self.squares_x * t_square_size, self.squares_y * t_square_size))

        # Center and pad to target resolution (white background)
        t_final_img = np.ones((height, width), dtype=np.uint8) * 255
        t_y_offset = (height - t_board_img.shape[0]) // 2
        t_x_offset = (width - t_board_img.shape[1]) // 2
        t_final_img[t_y_offset : t_y_offset + t_board_img.shape[0], t_x_offset : t_x_offset + t_board_img.shape[1]] = (
            t_board_img
        )

        self.board_image = t_final_img

        return

    def _save_arduino_bitmap_to_header(self, output_path: str, width: int, height: int) -> None:
        """
        Saves the binary bitmap data to an Arduino-compatible C header file.

        Args:
            output_path (str): The path to the output .h file.
            width (int): The width of the image.
            height (int): The height of the image.

        Returns:
            ():
        """

        with open(output_path, "w") as t_file:
            t_file.write(f"/* Charuco Board Bitmap: {width}x{height} */\n")
            t_file.write("#include <avr/pgmspace.h>\n\n")
            t_file.write("const unsigned char charuco_bitmap[] PROGMEM = {\n")
            for t_data in range(0, len(self.bitmap_data), 12):
                t_file.write("    " + ", ".join(self.bitmap_data[t_data : t_data + 12]) + ",\n")
            t_file.write("};\n")

        print_info(f"Stored Arduino header at {output_path}")

        return

    # ##### PUBLIC METHODS #####
    def update_board_parameters(self, square_length: float, marker_length: float) -> None:
        """
        Method to update the ChArUco board and detector with new square and marker lengths.
        This step is skipped if the provided dimensions are the same as the current ones to avoid unnecessary re-initialization.

        Args:
            square_length (float): The new square length in meters.
            marker_length (float): The new marker length in meters.

        Returns:
            ():
        """

        if self.square_length == square_length and self.marker_length == marker_length:
            return

        self.square_length = square_length
        self.marker_length = marker_length

        # Re-initialize the board and detector with new physical dimensions
        self.board = cv2.aruco.CharucoBoard(
            (self.squares_x, self.squares_y), self.square_length, self.marker_length, self.dictionary
        )
        self.detector = cv2.aruco.CharucoDetector(self.board, detectorParams=self.parameters)

        # Force regeneration of the board image on the next display update
        self.board_image = None

        return

    def estimate_pose(
        self,
        charuco_corners: np.ndarray,
        charuco_ids: np.ndarray,
        camera_matrix: np.ndarray,
        distortion_coefficients: np.ndarray,
    ) -> tuple[bool, np.ndarray, np.ndarray]:
        """
        Method to estimate the pose of the Charuco board (rotation and translation vectors).

        Args:
            charuco_corners (np.ndarray): The detected Charuco corners.
            charuco_ids (np.ndarray): The identifiers of the detected corners.
            camera_matrix (np.ndarray): The intrinsic camera matrix.
            distortion_coefficients (np.ndarray): The distortion coefficients.

        Returns:
            success (bool): Whether the pose was successfully estimated.
            rotation_vector (np.ndarray): Rotation vector.
            translation_vector (np.ndarray): Translation vector.
        """

        # Get the corresponding 3D object points for the detected corner IDs
        t_object_points = self.get_object_points(charuco_ids)

        # Estimate the pose using solvePnP
        t_success, t_rotation_vector, t_translation_vector = cv2.solvePnP(
            t_object_points, charuco_corners, camera_matrix, distortion_coefficients
        )

        if t_success:
            print_info(
                f"Charuco Board Pose - Rvec: {t_rotation_vector.flatten()}, Tvec: {t_translation_vector.flatten()}"
            )

        return t_success, t_rotation_vector, t_translation_vector

    def find_corners(self, gray_image: np.ndarray) -> tuple[bool, np.ndarray, np.ndarray, list, np.ndarray]:
        """
        Method to detect ChArUco board corners in a grayscale image.

        Args:
            gray_image (np.ndarray): The input grayscale image.

        Returns:
            success (bool): Whether corners were detected.
            charuco_corners (np.ndarray): Refined corner positions.
            charuco_ids (np.ndarray): Identifiers for detected corners.
            marker_corners (list): Raw ArUco marker corner arrays, each of shape (1, 4, 2).
            marker_ids (np.ndarray): Identifiers for detected ArUco markers.
        """

        t_charuco_corners, t_charuco_ids, t_marker_corners, t_marker_ids = self.detector.detectBoard(gray_image)
        t_success = t_charuco_corners is not None and len(t_charuco_corners) > 0

        # Invert the image for better detection if no corners are found (could be inverted by design of the flickering display)
        if not t_success:
            t_inverted_image = cv2.bitwise_not(gray_image)
            t_charuco_corners, t_charuco_ids, t_marker_corners, t_marker_ids = self.detector.detectBoard(
                t_inverted_image
            )
            t_success = t_charuco_corners is not None and len(t_charuco_corners) > 0

        return t_success, t_charuco_corners, t_charuco_ids, t_marker_corners, t_marker_ids

    def draw_corners(self, image: np.ndarray, corners: np.ndarray, ids: np.ndarray) -> np.ndarray:
        """
        Method to draw the detected Charuco corners on an image.

        Args:
            image (np.ndarray): The input image.
            corners (np.ndarray): The detected corner positions.
            ids (np.ndarray): The identifiers of the corners. (Currently not in use, but could be used to display the labels in the corners)

        Returns:
            annotated_image (np.ndarray): The image with drawn corners.
        """

        return cv2.aruco.drawDetectedCornersCharuco(image, corners, None, (0, 60, 255))

    def draw_markers(self, image: np.ndarray, corners: np.ndarray, ids: np.ndarray) -> np.ndarray:
        """
        Method to draw the detected ArUco markers on an image.

        Args:
            image (np.ndarray): The input image.
            corners (np.ndarray): The detected marker corner positions.
            ids (np.ndarray): The identifiers of the markers.

        Returns:
            annotated_image (np.ndarray): The image with drawn markers.
        """

        image = cv2.aruco.drawDetectedMarkers(image, corners, ids, (0, 60, 255))

        for t_corner in corners:
            t_pts = t_corner.reshape(4, 1, 2).astype(np.int32)
            cv2.polylines(image, [t_pts], isClosed=True, color=(0, 60, 255), thickness=3)
        return image

    def get_object_points(self, ids: np.ndarray) -> np.ndarray:
        """
        Method to retrieve the 3D object points corresponding to the detected corner IDs.

        Args:
            ids (np.ndarray): The identifiers of the detected corners.

        Returns:
            object_points (np.ndarray): The corresponding 3D object points.
        """

        # The CharucoBoard object has a property 'chessboardCorners' containing all corner positions in 3D
        # We index it using the detected IDs
        return self.board.getChessboardCorners()[ids.flatten()]

    def generate_arduino_bitmap(self, output_path: str, width: int = 640, height: int = 480, margin: int = 10) -> None:
        """
        Method to convert a Charuco board image to a binary bitmap (1 bit per pixel) for Arduino and saves it as a header.

        Args:
            output_path (str): The path to the output .h file.
            width (int): The required width of the generated image.
            height (int): The required height of the generated image.
            margin (int): The margin around the board in pixels.

        Returns:
            ():
        """

        # 1. Generate the board image
        self._generate_board_image(width=width, height=height, margin=margin)

        # 2. Creation of the bitmap
        # Thresholding to ensure strictly black or white (1 for WHITE, 0 for BLACK)
        t_binary_img = binary_threshold_cv(self.board_image, 127, 1)

        t_bitmap_data = []
        for t_y_position in range(height):
            for t_x_position in range(0, width, 8):
                t_byte = 0
                for t_bit in range(8):
                    if t_x_position + t_bit < width:
                        # Set bit to 1 if pixel is WHITE
                        if t_binary_img[t_y_position, t_x_position + t_bit] == 1:
                            t_byte |= 1 << (7 - t_bit)
                t_bitmap_data.append(f"0x{t_byte:02X}")

        self.bitmap_data = t_bitmap_data

        # 3. Save to header file
        self._save_arduino_bitmap_to_header(output_path, width, height)

        return

    def generate_toggling_video(
        self,
        output_path: str,
        width: int,
        height: int,
        margin: int,
        duration_sec: int,
        fps: int,
        toggle_freq_hz: float,
        overlay_opacity: float,
    ) -> None:
        """
        Method to generate a ChArUco board video that toggles brightness to trigger event cameras.
        Works with any sufficiently performing display.

        Args:
            output_path (str): The path to the output video file.
            width (int): The width of the video.
            height (int): The height of the video.
            margin (int): The margin around the board in pixels.
            duration_sec (int): The duration of the video in seconds.
            fps (int): The frames per second of the video.
            toggle_freq_hz (float): The frequency at which the brightness toggles (Hz).
            overlay_opacity (float): The opacity of the white overlay for the \"bright\" state (0 to 1).

        Returns:
            ():
        """

        # 1. Generate the base Charuco Board image
        self._generate_board_image(width=width, height=height, margin=margin)

        # 2. Setup the video writer
        t_fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        t_out = cv2.VideoWriter(output_path, t_fourcc, fps, (width, height))

        # 3. Generate frames and store in video
        t_num_frames = int(duration_sec * fps)
        t_white_overlay = np.ones_like(self.board_image) * 255

        for t_frame_counter in range(t_num_frames):
            if (t_frame_counter // (fps // (2 * toggle_freq_hz))) % 2 == 0:
                t_frame = add_weighted_overlay_cv(
                    self.board_image, t_white_overlay, 1 - overlay_opacity, overlay_opacity, 0
                )
            else:
                t_frame = self.board_image

            t_out.write(gray2bgr_cv(t_frame))

        t_out.release()
        print_info(f"Stored toggling video at {output_path}")

        return

    def update_display(
        self,
        calibration_active: bool,
        width: int,
        height: int,
        margin: int,
        overlay_opacity: float,
    ) -> None:
        """
        Updates the display based on calibration state.
        Toggles between original and dimmed board image.

        Args:
            calibration_active (bool): Flag indicating if the calibration process is currently active.
            width (int): The width of the generated image.
            height (int): The height of the generated image.
            margin (int): The margin around the board in pixels.
            overlay_opacity (float): The opacity of the white overlay for the "bright" state (0 to 1).

        Returns:
            ():
        """

        # Sync window visibility with calibration state
        self._ensure_live_window_is_ready(calibration_active)

        if not calibration_active:
            return

        # Generate board image if it hasn't been generated yet or if dimensions changed
        if self.board_image is None or self.board_image.shape[:2] != (height, width):
            self._generate_board_image(width=width, height=height, margin=margin)

        # Show chessboard if we are within threshold of the next capture
        # Toggle with the frequency of the call to trigger event camera
        if self.target_toggle:
            t_white_overlay = np.ones_like(self.board_image) * 255
            t_display_image = add_weighted_overlay_cv(
                self.board_image, t_white_overlay, 1 - overlay_opacity, overlay_opacity, 0
            )
        else:
            t_display_image = self.board_image

        # Increment toggle counter and update toggle every 3rd call
        self.target_toggle_counter += 1
        if self.target_toggle_counter >= 3:
            self.target_toggle = not self.target_toggle
            self.target_toggle_counter = 0

        # Display the image and process events
        cv2.imshow(self.live_window_title, t_display_image)
        cv2.waitKey(1)

        return


def visualize_fov_coverage(
    image_shape: tuple[int, int], corners: np.ndarray, color: tuple[int, int, int, int] = (0, 255, 0, 128)
) -> np.ndarray:
    """
    Function that visualizes the field of view coverage of the cameras by drawing circles at the corner positions of the calibration pattern.

    Args:
        image_shape (tuple [int, int]): The shape of the image (height, width) on which to visualize the field of view coverage.
        corners (np.ndarray): An array of the corner positions to be visualized.
        color (tuple [int, int, int, int]): The RGBA color of the circles.

    Returns:
        annotated_image (np.ndarray): The output image with the visualized field of view coverage.
    """

    # Create a blank image with the specified shape and 4 channels for transparency
    t_annotated_image = np.zeros((*image_shape, 4), dtype=np.uint8)

    # Draw filled circles at the corner positions
    for t_corner in corners:
        x_position, y_position = t_corner.ravel()
        cv2.circle(t_annotated_image, (int(x_position), int(y_position)), 13, color, -1)

    return t_annotated_image


def save_intrinsics_to_json(
    output_path: str,
    camera_matrix: np.ndarray,
    distortion_coefficients: np.ndarray,
    image_size: tuple[int, int],
    reprojection_error: float,
) -> None:
    """
    Function that saves the intrinsic camera parameters to a JSON file.

    Args:
        output_path (str): The path to the output JSON file.
        camera_matrix (np.ndarray): The 3x3 camera matrix.
        distortion_coefficients (np.ndarray): The distortion coefficients.
        image_size (tuple[int, int]): The image size (width, height).
        reprojection_error (float): The reprojection error of the calibration.

    Returns:
        ():
    """

    # Generate the dictionary with the intrinsic camera parameters
    t_intrinsics_dict = {
        "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "image_size": image_size,
        "camera_matrix": {
            "rows": camera_matrix.shape[0],
            "cols": camera_matrix.shape[1],
            "data": camera_matrix.flatten().tolist(),
        },
        "distortion_coefficients": {
            "rows": distortion_coefficients.shape[0],
            "cols": distortion_coefficients.shape[1],
            "data": distortion_coefficients.flatten().tolist(),
        },
        "reprojection_error": reprojection_error,
    }

    # Save the dictionary to a JSON file
    with open(output_path, "w") as t_file:
        json.dump(t_intrinsics_dict, t_file, indent=4)

    return


def save_extrinsics_to_json(
    output_path: str,
    rotation_matrix: np.ndarray,
    translation_vector: np.ndarray,
    reprojection_error: float,
) -> None:
    """
    Function that saves the extrinsic camera parameters to a JSON file.

    Args:
        output_path (str): The path to the output JSON file.
        rotation_matrix (np.ndarray): The 3x3 rotation matrix.
        translation_vector (np.ndarray): The 3x1 translation vector.
        reprojection_error (float): The reprojection error of the calibration.

    Returns:
        ():
    """

    # Generate the dictionary with the extrinsic camera parameters
    t_extrinsics_dict = {
        "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "rotation_matrix": {
            "rows": rotation_matrix.shape[0],
            "cols": rotation_matrix.shape[1],
            "data": rotation_matrix.flatten().tolist(),
        },
        "translation_vector": {
            "rows": translation_vector.shape[0],
            "cols": translation_vector.shape[1],
            "data": translation_vector.flatten().tolist(),
        },
        "reprojection_error": reprojection_error,
    }

    # Save the dictionary to a JSON file
    with open(output_path, "w") as t_file:
        json.dump(t_extrinsics_dict, t_file, indent=4)

    return


def calculate_intrinsic_parameters(
    object_points: list[np.ndarray],
    image_points: list[np.ndarray],
    image_shape: tuple[int, int],
    reprojection_error_threshold: float,
    min_corners_for_calibration: int,
    initial_camera_matrix: np.ndarray | None = None,
) -> tuple[float, np.ndarray, np.ndarray, tuple[np.ndarray, ...], tuple[np.ndarray, ...]]:
    """
    Function that calculates the intrinsic parameters of a camera and refines the dataset by removing
    outliers with high reprojection error. Implemented as two-stage process using the OpenCV calculated reprojection errors.

    Args:
        object_points (list[np.ndarray]): List of 3D object points.
        image_points (list[np.ndarray]): List of 2D image points.
        image_shape (tuple [int, int]): The shape of the image (height, width).
        reprojection_error_threshold (float): Threshold for removing frames with high error.
        initial_camera_matrix (np.ndarray | None): Optional initial guess for the camera matrix.
            When provided, OpenCV uses it as a starting point with CALIB_USE_INTRINSIC_GUESS.

    Returns:
        error (float): Final global reprojection error.
        camera_matrix (np.ndarray): The intrinsic camera matrix.
        distortion_coefficients (np.ndarray): The distortion coefficients.
        rotation_vectors (tuple[np.ndarray, ...]): Rotation vectors for each remaining frame.
        translation_vectors (tuple[np.ndarray, ...]): Translation vectors for each remaining frame.
    """

    t_flags = cv2.CALIB_USE_INTRINSIC_GUESS if initial_camera_matrix is not None else 0
    t_init_matrix = initial_camera_matrix.copy() if initial_camera_matrix is not None else None

    # 1. Initial calibration to identify outliers
    # We use calibrateCameraExtended to get the per-view RMS error directly from OpenCV
    (
        t_error,
        t_camera_matrix,
        t_distortion_coefficients,
        t_rotation_vectors,
        t_translation_vectors,
        _,
        _,
        t_per_view_error,
    ) = cv2.calibrateCameraExtended(
        object_points, image_points, tuple(image_shape[::-1]), t_init_matrix, None, flags=t_flags
    )
    print_info(f"Initial calibration RMS error before outlier removal: {t_error:.4f}")

    # Initialize temporary variables
    t_filtered_object_points = []
    t_filtered_image_points = []
    t_removed_frames = 0

    # 2. Evaluate all frames and filter out those with high reprojection error
    for t_counter in range(len(object_points)):
        t_individual_error = t_per_view_error[t_counter][0]

        if t_individual_error <= reprojection_error_threshold:
            t_filtered_object_points.append(object_points[t_counter])
            t_filtered_image_points.append(image_points[t_counter])
            print_info(f"Frame {t_counter}: Accepted - Error: {t_individual_error:.4f}")
        else:
            t_removed_frames += 1
            print_info(
                f"Frame {t_counter}: Rejected - Error: {t_individual_error:.4f} > {reprojection_error_threshold}"
            )

    # 3. Re-perform calibration if outliers were found and we have enough data left
    if t_removed_frames > 0 and len(t_filtered_object_points) >= min_corners_for_calibration:
        print_info(f"Re-calibrating after removing {t_removed_frames} frame(s)")
        t_error, t_camera_matrix, t_distortion_coefficients, t_rotation_vectors, t_translation_vectors = (
            cv2.calibrateCamera(
                t_filtered_object_points,
                t_filtered_image_points,
                tuple(image_shape[::-1]),
                initial_camera_matrix.copy() if initial_camera_matrix is not None else None,
                None,
                flags=t_flags,
            )
        )
    elif t_removed_frames > 0:
        print_error(
            "Not enough frames left for re-calibration. Using initial results. It is recommended to repeat the calibration process"
        )

    return t_error, t_camera_matrix, t_distortion_coefficients, t_rotation_vectors, t_translation_vectors


def calculate_stereo_parameters(
    object_points: list[np.ndarray],
    image_points_rgb: list[np.ndarray],
    image_points_event: list[np.ndarray],
    camera_matrix_rgb: np.ndarray,
    dist_coeffs_rgb: np.ndarray,
    camera_matrix_event: np.ndarray,
    dist_coeffs_event: np.ndarray,
    image_shape: tuple[int, int],
    reprojection_error_threshold: float,
    min_corners_for_calibration: int,
) -> tuple[float, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Function that calculates the extrinsic stereo parameters and refines the dataset by removing
    synchronized pairs with high stereo reprojection error. Implemented as two-stage process using
    the OpenCV calculated reprojection errors.

    Args:
        object_points (list[np.ndarray]): List of 3D object points.
        image_points_rgb (list[np.ndarray]): List of 2D points from the RGB camera.
        image_points_event (list[np.ndarray]): List of 2D points from the event camera.
        camera_matrix_rgb (np.ndarray): Intrinsic matrix of the RGB camera.
        dist_coeffs_rgb (np.ndarray): Distortion coefficients of the RGB camera.
        camera_matrix_event (np.ndarray): Intrinsic matrix of the event camera.
        dist_coeffs_event (np.ndarray): Distortion coefficients of the event camera.
        image_shape (tuple[int, int]): The shape of the image (height, width).
        reprojection_error_threshold (float): Threshold for removing pairs with high reprojection RMS error.
        min_corners_for_calibration (int): Minimum number of corners required for calibration.

    Returns:
        error (float): Final stereo reprojection error.
        R (np.ndarray): Rotation matrix.
        T (np.ndarray): Translation vector.
        E (np.ndarray): Essential matrix.
        F (np.ndarray): Fundamental matrix.
    """

    # 1. Initial stereo calibration
    # We use stereoCalibrateExtended to get the per-view RMS error directly from OpenCV
    (
        t_global_error,
        _,
        _,
        _,
        _,
        R,
        T,
        E,
        F,
        _,
        _,
        t_per_view_error,
    ) = cv2.stereoCalibrateExtended(
        object_points,
        image_points_rgb,
        image_points_event,
        camera_matrix_rgb,
        dist_coeffs_rgb,
        camera_matrix_event,
        dist_coeffs_event,
        tuple(image_shape[::-1]),
        None,  # R - no initial guess
        None,  # T - no initial guess
        criteria=(cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 1e-6),
        flags=cv2.CALIB_FIX_INTRINSIC,
    )
    print_info(f"Stereo calibration RMS error before outlier removal: {t_global_error:.4f}")

    # Initialize temporary variables
    t_filtered_object_points = []
    t_filtered_image_points_rgb = []
    t_filtered_image_points_event = []
    t_removed_pairs = 0

    # 2. Evaluate all pairs and filter out those with high stereo reprojection error
    for t_counter in range(len(object_points)):

        # Calculate the RMS from the per-view error for both cameras
        t_error_rgb = t_per_view_error[t_counter][0]
        t_error_event = t_per_view_error[t_counter][1]
        t_rms_reprojection_error = np.sqrt((t_error_rgb**2 + t_error_event**2) / 2)

        # Filter out pairs with high reprojection error
        if t_rms_reprojection_error < reprojection_error_threshold:
            t_filtered_object_points.append(object_points[t_counter])
            t_filtered_image_points_rgb.append(image_points_rgb[t_counter])
            t_filtered_image_points_event.append(image_points_event[t_counter])
            print_info(
                f"Pair {t_counter}: Accepted - Stereo RMS Error: {t_rms_reprojection_error:.4f} (RGB: {t_error_rgb:.4f}, Event: {t_error_event:.4f})"
            )
        else:
            t_removed_pairs += 1
            print_info(
                f"Pair {t_counter}: Rejected - Stereo RMS Error: {t_rms_reprojection_error:.4f} > {reprojection_error_threshold} (RGB: {t_error_rgb:.4f}, Event: {t_error_event:.4f})"
            )

    # 3. Re-perform stereo calibration if outliers were found and we have enough data left
    if t_removed_pairs > 0 and len(t_filtered_object_points) >= min_corners_for_calibration:
        print_info(f"Re-calibrating after removing {t_removed_pairs} pair(s)")
        t_global_error, _, _, _, _, R, T, E, F, _, _, _ = cv2.stereoCalibrateExtended(
            t_filtered_object_points,
            t_filtered_image_points_rgb,
            t_filtered_image_points_event,
            camera_matrix_rgb,
            dist_coeffs_rgb,
            camera_matrix_event,
            dist_coeffs_event,
            tuple(image_shape[::-1]),
            None,  # R - no initial guess
            None,  # T - no initial guess
            criteria=(cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 1e-6),
            flags=cv2.CALIB_FIX_INTRINSIC,
        )
    elif t_removed_pairs > 0:
        print_error(
            "Not enough pairs left for re-calibration. Using initial results. It is recommended to repeat the calibration process"
        )

    return t_global_error, R, T, E, F


class UR5eCalibrator:
    """
    Class that provides methods to perform calibration of (a) camera(s) using an UR5e robot arm to move the camera(s) in front
    of a calibration target.
    """

    def __init__(
        self,
        camera_name: str,
        camera_config: configparser.ConfigParser,
        stereo_calibration_config: configparser.ConfigParser,
        target_square_size: ValueProxy,
    ) -> None:

        # Get the parameters from the configuration file
        self.camera_name = camera_name
        self.camera_config = camera_config
        self.stereo_calibration_config = stereo_calibration_config

        # Read the ur5e robot parameters from the configuration file
        self.__robot_ip = self.stereo_calibration_config.get("ur5e", "robot_ip")
        self.__primary_port = self.stereo_calibration_config.getint("ur5e", "primary_port")
        self.__sweep_steps = self.stereo_calibration_config.getint("ur5e", "sweep_steps")

        # Read camera parameters from configuration file
        self.__vertical_resolution = self.camera_config.getint(f"{self.camera_name}", "vertical_resolution")
        self.__horizontal_resolution = self.camera_config.getint(f"{self.camera_name}", "horizontal_resolution")
        self.__pixel_size = self.camera_config.getfloat(f"{self.camera_name}", "pixel_size")
        self.__focal_length = self.camera_config.getfloat(f"{self.camera_name}_lens", "focal_length")

        # Target pattern parameters
        self.__target_columns = self.stereo_calibration_config.getint("target", "target_columns")
        self.__target_rows = self.stereo_calibration_config.getint("target", "target_rows")
        self.__target_square_size = target_square_size.value
        self.__distance_to_target = self.camera_config.getfloat(
            f"{self.camera_name}_calibration", "distance_to_target"
        )

        # Calibration parameters
        self.__positional_offset_x = self.camera_config.getfloat(
            f"{self.camera_name}_calibration", "positional_offset_x"
        )
        self.__calibration_rows = self.camera_config.getint(f"{self.camera_name}_calibration", "calibration_rows")
        self.__calibration_columns = self.camera_config.getint(
            f"{self.camera_name}_calibration", "calibration_columns"
        )
        self.__calibration_depth_positions = self.camera_config.getint(
            f"{self.camera_name}_calibration", "calibration_depth_positions"
        )
        self.__calibration_rotation_positions = self.camera_config.getint(
            f"{self.camera_name}_calibration", "calibration_rotation_positions"
        )
        self.__max_roll = self.camera_config.getfloat(f"{self.camera_name}_calibration", "max_roll")
        self.__max_pitch = self.camera_config.getfloat(f"{self.camera_name}_calibration", "max_pitch")
        self.__max_yaw = self.camera_config.getfloat(f"{self.camera_name}_calibration", "max_yaw")
        self.__depth_step_divisor = self.camera_config.getint(f"{self.camera_name}_calibration", "depth_step_divisor")
        self.__move_time = self.camera_config.getfloat(f"{self.camera_name}_calibration", "move_time")
        self.__move_time_start = self.camera_config.getfloat(f"{self.camera_name}_calibration", "move_time_start")
        self.__move_time_start_depth = self.camera_config.getfloat(
            f"{self.camera_name}_calibration", "move_time_start_depth"
        )
        self.__wait_time = self.camera_config.getfloat(f"{self.camera_name}_calibration", "wait_time")

        # Extra calibration positions
        self.__extra_pos1_z = self.camera_config.getfloat(f"{self.camera_name}_calibration", "extra_pos1_z")
        self.__extra_pos1_ry = self.camera_config.getfloat(f"{self.camera_name}_calibration", "extra_pos1_ry")
        self.__extra_pos2_z = self.camera_config.getfloat(f"{self.camera_name}_calibration", "extra_pos2_z")
        self.__extra_pos2_ry = self.camera_config.getfloat(f"{self.camera_name}_calibration", "extra_pos2_ry")
        self.__extra_pos3_x = self.camera_config.getfloat(f"{self.camera_name}_calibration", "extra_pos3_x")
        self.__extra_pos3_rz = self.camera_config.getfloat(f"{self.camera_name}_calibration", "extra_pos3_rz")
        self.__extra_pos4_x = self.camera_config.getfloat(f"{self.camera_name}_calibration", "extra_pos4_x")
        self.__extra_pos4_rz = self.camera_config.getfloat(f"{self.camera_name}_calibration", "extra_pos4_rz")

        # Diagonal calibration positions
        self.__diag_pos1_x = self.camera_config.getfloat(f"{self.camera_name}_calibration", "diag_pos1_x")
        self.__diag_pos1_z = self.camera_config.getfloat(f"{self.camera_name}_calibration", "diag_pos1_z")
        self.__diag_pos1_rx = self.camera_config.getfloat(f"{self.camera_name}_calibration", "diag_pos1_rx")
        self.__diag_pos1_ry = self.camera_config.getfloat(f"{self.camera_name}_calibration", "diag_pos1_ry")
        self.__diag_pos1_rz = self.camera_config.getfloat(f"{self.camera_name}_calibration", "diag_pos1_rz")
        self.__diag_pos2_x = self.camera_config.getfloat(f"{self.camera_name}_calibration", "diag_pos2_x")
        self.__diag_pos2_z = self.camera_config.getfloat(f"{self.camera_name}_calibration", "diag_pos2_z")
        self.__diag_pos2_rx = self.camera_config.getfloat(f"{self.camera_name}_calibration", "diag_pos2_rx")
        self.__diag_pos2_ry = self.camera_config.getfloat(f"{self.camera_name}_calibration", "diag_pos2_ry")
        self.__diag_pos2_rz = self.camera_config.getfloat(f"{self.camera_name}_calibration", "diag_pos2_rz")
        self.__diag_pos3_x = self.camera_config.getfloat(f"{self.camera_name}_calibration", "diag_pos3_x")
        self.__diag_pos3_z = self.camera_config.getfloat(f"{self.camera_name}_calibration", "diag_pos3_z")
        self.__diag_pos3_rx = self.camera_config.getfloat(f"{self.camera_name}_calibration", "diag_pos3_rx")
        self.__diag_pos3_ry = self.camera_config.getfloat(f"{self.camera_name}_calibration", "diag_pos3_ry")
        self.__diag_pos3_rz = self.camera_config.getfloat(f"{self.camera_name}_calibration", "diag_pos3_rz")
        self.__diag_pos4_x = self.camera_config.getfloat(f"{self.camera_name}_calibration", "diag_pos4_x")
        self.__diag_pos4_z = self.camera_config.getfloat(f"{self.camera_name}_calibration", "diag_pos4_z")
        self.__diag_pos4_rx = self.camera_config.getfloat(f"{self.camera_name}_calibration", "diag_pos4_rx")
        self.__diag_pos4_ry = self.camera_config.getfloat(f"{self.camera_name}_calibration", "diag_pos4_ry")
        self.__diag_pos4_rz = self.camera_config.getfloat(f"{self.camera_name}_calibration", "diag_pos4_rz")

        # Base position of the root (orthogonal to the target pattern plane)
        self.__base_x = self.camera_config.getfloat(f"{self.camera_name}_position", "base_x")
        self.__base_y = self.camera_config.getfloat(f"{self.camera_name}_position", "base_y")
        self.__base_z = self.camera_config.getfloat(f"{self.camera_name}_position", "base_z")

        # Compensate mounting offsets
        self.__base_x += self.__positional_offset_x

        # Base orientation of the root (orthogonal to the target pattern plane)
        self.__base_rx = self.camera_config.getfloat(f"{self.camera_name}_orientation", "base_rx")
        self.__base_ry = self.camera_config.getfloat(f"{self.camera_name}_orientation", "base_ry")
        self.__base_rz = self.camera_config.getfloat(f"{self.camera_name}_orientation", "base_rz")

        # Futher attributes to be calculated
        self.__sensor_width = 0.0
        self.__sensor_height = 0.0
        self.__horizontal_fov_deg = 0.0
        self.__vertical_fov_deg = 0.0
        self.__horizontal_fov_rad = 0.0
        self.__vertical_fov_rad = 0.0
        self.__target_width = 0.0
        self.__target_height = 0.0
        self.__scene_width = 0.0
        self.__scene_height = 0.0
        self.__midpoint_x = 0.0
        self.__midpoint_z = 0.0
        self.__min_depth_position = 0.0
        self.__max_depth_position = 0.0
        self.__step_movement_x = 0.0
        self.__step_movement_y = 0.0
        self.__step_movement_z = 0.0
        self.__step_movement_rx = 0.0
        self.__step_movement_ry = 0.0
        self.__step_movement_rz = 0.0
        self.__min_rotation_position = 0.0
        self.__max_rotation_position = 0.0

        # Aggregated parameter dictionary
        self.__parameter_dict = {}

        # Final script to be run
        self.__ur_script = ""

        # Do the calulations in advance
        self._calculate_camera_properties()
        self._calculate_scene()
        self._calculate_robot_step_movements()
        self._generate_parameter_dict()
        self._generate_ur_script()

    # ##### GETTER #####
    @property
    def sensor_width(self) -> float:
        """
        Getter for the attribute '__sensor_width'.

        Args:
            ():

        Returns:
            sensor_width (float): The attribute '__sensor_width'.
        """

        return self.__sensor_width

    @property
    def sensor_height(self) -> float:
        """
        Getter for the attribute '__sensor_height'.

        Args:
            ():

        Returns:
            sensor_height (float): The attribute '__sensor_height'.
        """

        return self.__sensor_height

    @property
    def horizontal_fov_deg(self) -> float:
        """
        Getter for the attribute '__horizontal_fov_deg'.

        Args:
            ():

        Returns:
            horizontal_fov_deg (float): The attribute '__horizontal_fov_deg'.
        """

        return self.__horizontal_fov_deg

    @property
    def vertical_fov_deg(self) -> float:
        """
        Getter for the attribute '__vertical_fov_deg'.

        Args:
            ():

        Returns:
            vertical_fov_deg (float): The attribute '__vertical_fov_deg'.
        """

        return self.__vertical_fov_deg

    @property
    def horizontal_fov_rad(self) -> float:
        """
        Getter for the attribute '__horizontal_fov_rad'.

        Args:
            ():

        Returns:
            horizontal_fov_rad (float): The attribute '__horizontal_fov_rad'.
        """

        return self.__horizontal_fov_rad

    @property
    def vertical_fov_rad(self) -> float:
        """
        Getter for the attribute '__vertical_fov_rad'.

        Args:
            ():

        Returns:
            vertical_fov_rad (float): The attribute '__vertical_fov_rad'.
        """

        return self.__vertical_fov_rad

    @property
    def target_width(self) -> float:
        """
        Getter for the attribute '__target_width'.

        Args:
            ():

        Returns:
            target_width (float): The attribute '__target_width'.
        """

        return self.__target_width

    @property
    def target_height(self) -> float:
        """
        Getter for the attribute '__target_height'.

        Args:
            ():

        Returns:
            target_height (float): The attribute '__target_height'.
        """

        return self.__target_height

    @property
    def scene_width(self) -> float:
        """
        Getter for the attribute '__scene_width'.

        Args:
            ():

        Returns:
            scene_width (float): The attribute '__scene_width'.
        """

        return self.__scene_width

    @property
    def scene_height(self) -> float:
        """
        Getter for the attribute '__scene_height'.

        Args:
            ():

        Returns:
            scene_height (float): The attribute '__scene_height'.
        """

        return self.__scene_height

    @property
    def midpoint_x(self) -> float:
        """
        Getter for the attribute '__midpoint_x'.

        Args:
            ():

        Returns:
            midpoint_x (float): The attribute '__midpoint_x'.
        """

        return self.__midpoint_x

    @property
    def midpoint_z(self) -> float:
        """
        Getter for the attribute '__midpoint_z'.

        Args:
            ():

        Returns:
            midpoint_z (float): The attribute '__midpoint_z'.
        """

        return self.__midpoint_z

    @property
    def min_depth_position(self) -> int:
        """
        Getter for the attribute '__min_depth_position'.

        Args:
            ():

        Returns:
            min_depth_position (int): The attribute '__min_depth_position'.
        """

        return self.__min_depth_position

    @property
    def max_depth_position(self) -> int:
        """
        Getter for the attribute '__max_depth_position'.

        Args:
            ():

        Returns:
            max_depth_position (int): The attribute '__max_depth_position'.
        """

        return self.__max_depth_position

    @property
    def step_movement_x(self) -> float:
        """
        Getter for the attribute '__step_movement_x'.

        Args:
            ():

        Returns:
            step_movement_x (float): The attribute '__step_movement_x'.
        """

        return self.__step_movement_x

    @property
    def step_movement_y(self) -> float:
        """
        Getter for the attribute '__step_movement_y'.

        Args:
            ():

        Returns:
            step_movement_y (float): The attribute '__step_movement_y'.
        """

        return self.__step_movement_y

    @property
    def step_movement_z(self) -> float:
        """
        Getter for the attribute '__step_movement_z'.

        Args:
            ():

        Returns:
            step_movement_z (float): The attribute '__step_movement_z'.
        """

        return self.__step_movement_z

    @property
    def step_movement_rx(self) -> float:
        """
        Getter for the attribute '__step_movement_rx'.

        Args:
            ():

        Returns:
            step_movement_rx (float): The attribute '__step_movement_rx'.
        """

        return self.__step_movement_rx

    @property
    def step_movement_ry(self) -> float:
        """
        Getter for the attribute '__step_movement_ry'.

        Args:
            ():

        Returns:
            step_movement_ry (float): The attribute '__step_movement_ry'.
        """

        return self.__step_movement_ry

    @property
    def step_movement_rz(self) -> float:
        """
        Getter for the attribute '__step_movement_rz'.

        Args:
            ():

        Returns:
            step_movement_rz (float): The attribute '__step_movement_rz'.
        """

        return self.__step_movement_rz

    @property
    def step_movement_rz(self) -> float:
        """
        Getter for the attribute '__step_movement_rz'.

        Args:
            ():

        Returns:
            step_movement_rz (float): The attribute '__step_movement_rz'.
        """

        return self.__step_movement_rz

    @property
    def min_rotation_position(self) -> int:
        """
        Getter for the attribute '__min_rotation_position'.

        Args:
            ():

        Returns:
            min_rotation_position (int): The attribute '__min_rotation_position'.
        """

        return self.__min_rotation_position

    @property
    def max_rotation_position(self) -> int:
        """
        Getter for the attribute '__max_rotation_position'.

        Args:
            ():

        Returns:
            max_rotation_position (int): The attribute '__max_rotation_position'.
        """

        return self.__max_rotation_position

    @property
    def parameter_dict(self) -> dict:
        """
        Getter for the attribute '__parameter_dict'.

        Args:
            ():

        Returns:
            parameter_dict (dict): The attribute '__parameter_dict'.
        """

        return self.__parameter_dict

    @property
    def ur_script(self) -> str:
        """
        Getter for the attribute '__ur_script'.

        Args:
            ():

        Returns:
            ur_script (str): The attribute '__ur_script'.
        """

        return self.__ur_script

    # ##### SETTER #####
    @sensor_width.setter
    def sensor_width(self, value: float) -> None:
        """
        Setter for the attribute '__sensor_width'.

        Args:
            value (float): The new value for the attribute '__sensor_width'.

        Returns:
            ():
        """

        self.__sensor_width = value

        return

    @sensor_height.setter
    def sensor_height(self, value: float) -> None:
        """
        Setter for the attribute '__sensor_height'.

        Args:
            value (float): The new value for the attribute '__sensor_height'.

        Returns:
            ():
        """

        self.__sensor_height = value

        return

    @horizontal_fov_deg.setter
    def horizontal_fov_deg(self, value: float) -> None:
        """
        Setter for the attribute '__horizontal_fov_deg'.

        Args:
            value (float): The new value for the attribute '__horizontal_fov_deg'.

        Returns:
            ():
        """

        self.__horizontal_fov_deg = value

        return

    @vertical_fov_deg.setter
    def vertical_fov_deg(self, value: float) -> None:
        """
        Setter for the attribute '__vertical_fov_deg'.

        Args:
            value (float): The new value for the attribute '__vertical_fov_deg'.

        Returns:
            ():
        """

        self.__vertical_fov_deg = value

        return

    @horizontal_fov_rad.setter
    def horizontal_fov_rad(self, value: float) -> None:
        """
        Setter for the attribute '__horizontal_fov_rad'.

        Args:
            value (float): The new value for the attribute '__horizontal_fov_rad'.

        Returns:
            ():
        """

        self.__horizontal_fov_rad = value

        return

    @vertical_fov_rad.setter
    def vertical_fov_rad(self, value: float) -> None:
        """
        Setter for the attribute '__vertical_fov_rad'.

        Args:
            value (float): The new value for the attribute '__vertical_fov_rad'.

        Returns:
            ():
        """

        self.__vertical_fov_rad = value

        return

    @target_width.setter
    def target_width(self, value: float) -> None:
        """
        Setter for the attribute '__target_width'.

        Args:
            value (float): The new value for the attribute '__target_width'.

        Returns:
            ():
        """

        self.__target_width = value

        return

    @target_height.setter
    def target_height(self, value: float) -> None:
        """
        Setter for the attribute '__target_height'.

        Args:
            value (float): The new value for the attribute '__target_height'.

        Returns:
            ():
        """

        self.__target_height = value

        return

    @scene_width.setter
    def scene_width(self, value: float) -> None:
        """
        Setter for the attribute '__scene_width'.

        Args:
            value (float): The new value for the attribute '__scene_width'.

        Returns:
            ():
        """

        self.__scene_width = value

        return

    @scene_height.setter
    def scene_height(self, value: float) -> None:
        """
        Setter for the attribute '__scene_height'.

        Args:
            value (float): The new value for the attribute '__scene_height'.

        Returns:
            ():
        """

        self.__scene_height = value

        return

    @midpoint_x.setter
    def midpoint_x(self, value: float) -> None:
        """
        Setter for the attribute '__midpoint_x'.

        Args:
            value (float): The new value for the attribute '__midpoint_x'.

        Returns:
            ():
        """

        self.__midpoint_x = value

        return

    @midpoint_z.setter
    def midpoint_z(self, value: float) -> None:
        """
        Setter for the attribute '__midpoint_z'.

        Args:
            value (float): The new value for the attribute '__midpoint_z'.

        Returns:
            ():
        """

        self.__midpoint_z = value

        return

    @min_depth_position.setter
    def min_depth_position(self, value: int) -> None:
        """
        Setter for the attribute '__min_depth_position'.

        Args:
            value (int): The new value for the attribute '__min_depth_position'.

        Returns:
            ():
        """

        self.__min_depth_position = value

        return

    @max_depth_position.setter
    def max_depth_position(self, value: int) -> None:
        """
        Setter for the attribute '__max_depth_position'.

        Args:
            value (int): The new value for the attribute '__max_depth_position'.

        Returns:
            ():
        """

        self.__max_depth_position = value

        return

    @step_movement_x.setter
    def step_movement_x(self, value: float) -> None:
        """
        Setter for the attribute '__step_movement_x'.

        Args:
            value (float): The new value for the attribute '__step_movement_x'.

        Returns:
            ():
        """

        self.__step_movement_x = value

        return

    @step_movement_y.setter
    def step_movement_y(self, value: float) -> None:
        """
        Setter for the attribute '__step_movement_y'.

        Args:
            value (float): The new value for the attribute '__step_movement_y'.

        Returns:
            ():
        """

        self.__step_movement_y = value

        return

    @step_movement_z.setter
    def step_movement_z(self, value: float) -> None:
        """
        Setter for the attribute '__step_movement_z'.

        Args:
            value (float): The new value for the attribute '__step_movement_z'.

        Returns:
            ():
        """

        self.__step_movement_z = value

        return

    @step_movement_rx.setter
    def step_movement_rx(self, value: float) -> None:
        """
        Setter for the attribute '__step_movement_rx'.

        Args:
            value (float): The new value for the attribute '__step_movement_rx'.

        Returns:
            ():
        """

        self.__step_movement_rx = value

        return

    @step_movement_ry.setter
    def step_movement_ry(self, value: float) -> None:
        """
        Setter for the attribute '__step_movement_ry'.

        Args:
            value (float): The new value for the attribute '__step_movement_ry'.

        Returns:
            ():
        """

        self.__step_movement_ry = value

        return

    @step_movement_rz.setter
    def step_movement_rz(self, value: float) -> None:
        """
        Setter for the attribute '__step_movement_rz'.

        Args:
            value (float): The new value for the attribute '__step_movement_rz'.

        Returns:
            ():
        """

        self.__step_movement_rz = value

        return

    @min_rotation_position.setter
    def min_rotation_position(self, value: int) -> None:
        """
        Setter for the attribute '__min_rotation_position'.

        Args:
            value (int): The new value for the attribute '__min_rotation_position'.

        Returns:
            ():
        """

        self.__min_rotation_position = value

        return

    @max_rotation_position.setter
    def max_rotation_position(self, value: int) -> None:
        """
        Setter for the attribute '__max_rotation_position'.

        Args:
            value (int): The new value for the attribute '__max_rotation_position'.

        Returns:
            ():
        """

        self.__max_rotation_position = value

        return

    @parameter_dict.setter
    def parameter_dict(self, value: dict) -> None:
        """
        Setter for the attribute '__parameter_dict'.

        Args:
            value (dict): The new value for the attribute '__parameter_dict'.

        Returns:
            ():
        """

        self.__parameter_dict = value

        return

    @ur_script.setter
    def ur_script(self, value: str) -> None:
        """
        Setter for the attribute '__ur_script'.

        Args:
            value (str): The new value for the attribute '__ur_script'.

        Returns:
            ():
        """

        self.__ur_script = value

        return

    # ##### PRIVATE METHODS #####
    def _calculate_camera_properties(self) -> None:
        """
        Method to calculate the camera properties (sensor width, horizontal and vertical field of view).

        Args:
            ():

        Returns:
            ():
        """

        # Calculate the sensor dimensions from the resolution and pixel size
        self.sensor_width, self.sensor_height = calculate_sensor_dimensions_m(
            self.__vertical_resolution, self.__horizontal_resolution, self.__pixel_size
        )

        # Calculate the horizontal and vertical field of view from the sensor dimensions
        self.horizontal_fov_deg = calculate_field_of_view_deg(self.__focal_length, self.sensor_width)
        self.vertical_fov_deg = calculate_field_of_view_deg(self.__focal_length, self.sensor_height)
        self.horizontal_fov_rad = radians(self.horizontal_fov_deg)
        self.vertical_fov_rad = radians(self.vertical_fov_deg)

        return

    def _calculate_scene(self) -> None:
        """
        Method to calculate the scene. Required to calculate the expected scene width and height to
        cover by the robot movements.

        Args:
            ():

        Returns:
            ():
        """

        # Calculate the dimensions of the target pattern in meters (increase by one square size to make sure the FOV covers the whole pattern)
        self.target_width = (self.__target_columns + 1) * self.__target_square_size
        self.target_height = (self.__target_rows + 1) * self.__target_square_size

        # Calculate the expected scene width and height at the given distance to the target pattern
        self.scene_width = 2 * self.__distance_to_target * tan(self.horizontal_fov_rad / 2)
        self.scene_height = 2 * self.__distance_to_target * tan(self.vertical_fov_rad / 2)

        # Subtract the target pattern dimensions from the expected scene dimensions to get the required movement range for the robot
        self.scene_width -= self.target_width
        self.scene_height -= self.target_height

        # Calculate the min and max depth positions
        self.min_depth_position = int(-self.__calibration_depth_positions / 2)
        self.max_depth_position = int(self.__calibration_depth_positions / 2)

        # Calculate the min and max rotation positions
        self.min_rotation_position = int(-self.__calibration_rotation_positions / 2)
        self.max_rotation_position = int(self.__calibration_rotation_positions / 2)

        return

    def _calculate_robot_step_movements(self) -> None:
        """
        Method to calculate the required robot step movements in x, y and z direction to cover the expected scene dimensions.

        Args:
            ():

        Returns:
            ():
        """

        # Calculate the required step movements in x, y and z direction
        self.step_movement_x = round(self.scene_width / (self.__calibration_columns - 1), 3)
        self.step_movement_y = self.__distance_to_target / self.__depth_step_divisor
        self.step_movement_z = round(self.scene_height / (self.__calibration_rows - 1), 3)

        # Calculate the rotation step movements in rx, ry and rz direction
        self.step_movement_rx = round(radians(self.__max_roll) / (self.__calibration_rotation_positions - 1), 3)
        self.step_movement_ry = round(radians(self.__max_yaw) / (self.__calibration_rotation_positions - 1), 3)
        self.step_movement_rz = round(radians(self.__max_pitch) / (self.__calibration_rotation_positions - 1), 3)

        # Calculate the midpoint of the scene
        self.midpoint_x = self.__base_x + (self.__calibration_columns - 1) / 2 * self.step_movement_x
        self.midpoint_z = self.__base_z - (self.__calibration_rows - 1) / 2 * self.step_movement_z

        return

    def _generate_parameter_dict(self) -> None:
        """
        Method to generate a parameter dictionary for the URScript generation.

        Args:
            ():

        Returns:
            ():
        """

        self.parameter_dict = {
            "base_x": self.__base_x,
            "base_y": self.__base_y,
            "base_z": self.__base_z,
            "base_rx": self.__base_rx,
            "base_ry": self.__base_ry,
            "base_rz": self.__base_rz,
            "t_move": self.__move_time,
            "t_move_start": self.__move_time_start,
            "t_move_start_depth": self.__move_time_start_depth,
            "t_wait": self.__wait_time,
            "step_x": self.step_movement_x,
            "step_y": self.step_movement_y,
            "step_z": self.step_movement_z,
            "calibration_rows": self.__calibration_rows,
            "calibration_columns": self.__calibration_columns,
            "min_depth_position": self.min_depth_position,
            "max_depth_position": self.max_depth_position,
            "midpoint_x": self.midpoint_x,
            "midpoint_z": self.midpoint_z,
            "min_rotation_position": self.min_rotation_position,
            "max_rotation_position": self.max_rotation_position,
            "step_rx": self.step_movement_rx,
            "step_ry": self.step_movement_ry,
            "step_rz": self.step_movement_rz,
            "extra_pos1_z": self.__extra_pos1_z,
            "extra_pos1_ry": self.__extra_pos1_ry,
            "extra_pos2_z": self.__extra_pos2_z,
            "extra_pos2_ry": self.__extra_pos2_ry,
            "extra_pos3_x": self.__extra_pos3_x,
            "extra_pos3_rz": self.__extra_pos3_rz,
            "extra_pos4_x": self.__extra_pos4_x,
            "extra_pos4_rz": self.__extra_pos4_rz,
            "sweep_steps": self.__sweep_steps,
            "diag_pos1_x": self.__diag_pos1_x,
            "diag_pos1_z": self.__diag_pos1_z,
            "diag_pos1_rx": self.__diag_pos1_rx,
            "diag_pos1_ry": self.__diag_pos1_ry,
            "diag_pos1_rz": self.__diag_pos1_rz,
            "diag_pos2_x": self.__diag_pos2_x,
            "diag_pos2_z": self.__diag_pos2_z,
            "diag_pos2_rx": self.__diag_pos2_rx,
            "diag_pos2_ry": self.__diag_pos2_ry,
            "diag_pos2_rz": self.__diag_pos2_rz,
            "diag_pos3_x": self.__diag_pos3_x,
            "diag_pos3_z": self.__diag_pos3_z,
            "diag_pos3_rx": self.__diag_pos3_rx,
            "diag_pos3_ry": self.__diag_pos3_ry,
            "diag_pos3_rz": self.__diag_pos3_rz,
            "diag_pos4_x": self.__diag_pos4_x,
            "diag_pos4_z": self.__diag_pos4_z,
            "diag_pos4_rx": self.__diag_pos4_rx,
            "diag_pos4_ry": self.__diag_pos4_ry,
            "diag_pos4_rz": self.__diag_pos4_rz,
        }

        return

    def _generate_ur_script(self) -> None:
        """
        Method to generate the URScript for the calibration process.
        It uses a template URScript file and formats it with the calculated parameters.

        Args:
            ():

        Returns:
            ():
        """

        # Open the URScript template file
        t_ur_script_template = open_ur_script_file(Path(__file__).parent / "ur_scripts" / "calibration_ur5e.urs")

        # Format the URScript template with the calculated parameters
        self.ur_script = t_ur_script_template.format(**self.parameter_dict)

        return

    def _run_ur_script(self, position_reached_event: threading.Event | None = None) -> None:
        """
        Method to run the generated URScript on the robot.

        Args:
            position_reached_event (threading.Event | None): Optional event to set on each DO2 rising edge
                                                             (robot reached a calibration position). Cleared on the falling edge.

        Returns:
            ():
        """

        # Open a connection to the robot and send the URScript
        t_rtde_r = RTDEReceiveInterface(self.__robot_ip)

        # Clear any leftover event state from a previous (aborted) run
        if position_reached_event is not None:
            position_reached_event.clear()

        send_urscript(self.ur_script, self.__robot_ip, self.__primary_port)

        # Now wait for DO1 to go HIGH (new script entered its main movement loop)
        while not t_rtde_r.getDigitalOutState(1):
            time.sleep(0.005)

        # Monitor DO2 position-reached pulses while the main loop is running (DO1 HIGH)
        # Initialize from current state to avoid a false rising edge if DO2 is already HIGH
        t_digital_out_2_previous = False
        while t_rtde_r.getDigitalOutState(1):
            t_digital_out_2 = t_rtde_r.getDigitalOutState(2)

            if position_reached_event is not None:
                # Rising edge: robot reached position
                if t_digital_out_2 and not t_digital_out_2_previous:
                    position_reached_event.set()

                # Falling edge: robot starting to move
                elif not t_digital_out_2 and t_digital_out_2_previous:
                    position_reached_event.clear()

            t_digital_out_2_previous = t_digital_out_2
            time.sleep(0.001)

        # Close the connection to the robot
        t_rtde_r.disconnect()

        return

    # ##### PUBLIC METHODS #####
    def perform_calibration(self, position_reached_event: threading.Event | None = None) -> None:
        """
        Method to perform the calibration process.

        Args:
            position_reached_event (threading.Event | None): Optional event to set when the robot
                signals a position-reached state via DO2.

        Returns:
            ():
        """

        self._run_ur_script(position_reached_event)

        return
