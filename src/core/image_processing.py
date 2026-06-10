#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Filename: image_processing.py
Author: Nico Hessenthaler
Date: 2026-06-05
Version: 1.0
Description:
    Module that provides utilities for general image processing.
License: Apache License Version 2.0
Contact: nico.hessenthaler@hs-heilbronn.de
"""

import base64
import configparser
import cv2
import numpy as np
from multiprocessing import Process, Queue
from .operating_system import create_directory
from pathlib import Path
from turbojpeg import TurboJPEG


def background_worker(queue: Queue) -> None:
    """
    Worker function that runs in a separate process, waiting for tasks to write frames.
    Tasks are passed as a tuple: (output_dir, prefix, nth_frame, frames, start_counter)

    Args:
        queue (Queue): The multiprocessing queue to receive tasks.

    Returns:
        ():
    """

    while True:

        # Wait until a task is available in the queue
        t_task = queue.get()

        # Check if the task is a termination signal
        if t_task is None:
            break

        # Extract the task
        t_output_dir, t_prefix, t_nth_frame, t_frames, t_start_counter = t_task

        # Ensure output directory exists (per task)
        create_directory(t_output_dir)

        for t_local_counter, t_frame in enumerate(t_frames):
            if t_local_counter % t_nth_frame == 0:
                if t_prefix != "":
                    t_filename = t_output_dir / f"{t_prefix}_{t_start_counter + t_local_counter:06d}.png"
                else:
                    t_filename = t_output_dir / f"{t_start_counter + t_local_counter:06d}.png"
                cv2.imwrite(str(t_filename), t_frame, [cv2.IMWRITE_PNG_COMPRESSION, 0])

    return


class PNGWriterCV:
    """Class for writing PNG image files to disk using OpenCV."""

    _worker_process = None
    _queue = None

    @classmethod
    def _start_worker(cls):
        """
        Class method to start the background worker process if it is not already running.
        """
        if cls._worker_process is None or not cls._worker_process.is_alive():
            cls._queue = Queue()
            cls._worker_process = Process(target=background_worker, args=(cls._queue,), daemon=True)
            cls._worker_process.start()

    def __init__(self, output_dir: str, prefix: str, nth_frame: int) -> None:
        self.__output_dir = Path(output_dir)
        self.__prefix = prefix
        self.__nth_frame = nth_frame
        self.__counter = 0
        self.__frames_buffer = []

        # Ensure the global worker is running
        self._start_worker()

        # Create the directory if it doesn't exist (in main process for early feedback)
        create_directory(self.__output_dir)

    # ##### GETTER #####
    @property
    def output_dir(self) -> Path:
        """
        Getter for the attribute '__output_dir'.

        Args:
            ():

        Returns:
            output_dir (Path): The attribute '__output_dir'.
        """

        return self.__output_dir

    @property
    def prefix(self) -> str:
        """
        Getter for the attribute '__prefix'.

        Args:
            ():

        Returns:
            prefix (str): The attribute '__prefix'.
        """

        return self.__prefix

    @property
    def nth_frame(self) -> int:
        """
        Getter for the attribute '__nth_frame'.

        Args:
            ():

        Returns:
            nth_frame (int): The attribute '__nth_frame'.
        """

        return self.__nth_frame

    @property
    def counter(self) -> int:
        """
        Getter for the attribute '__counter'.

        Args:
            ():

        Returns:
            counter (int): The attribute '__counter'.
        """

        return self.__counter

    @property
    def frames_buffer(self) -> list:
        """
        Getter for the attribute '__frames_buffer'.

        Args:
            ():

        Returns:
            frames_buffer (list): The attribute '__frames_buffer'.
        """

        return self.__frames_buffer

    # ##### SETTER #####
    @counter.setter
    def counter(self, value: int) -> None:
        """
        Setter for the attribute '__counter'.

        Args:
            value (int): The new value for the attribute '__counter'.

        Returns:
            ():
        """

        self.__counter = value

        return

    @frames_buffer.setter
    def frames_buffer(self, value: list) -> None:
        """
        Setter for the attribute '__frames_buffer'.

        Args:
            value (list): The new value for the attribute '__frames_buffer'.

        Returns:
            ():
        """

        self.__frames_buffer = value

        return

    # ##### PRIVATE METHODS #####
    def _write_buffered_frames_async(self) -> None:
        """
        Method to feed the buffered frames to the background worker process for writing to disk asynchronously.
        This call is non-blocking. Note: This clears the buffer for new captures.

        Args:
            ():

        Returns:
            ():
        """

        # Terminate if no frames to write
        if not self.frames_buffer:
            return

        # Put the frames into the class-level queue as a task tuple
        t_task = (self.output_dir, self.prefix, self.nth_frame, self.frames_buffer.copy(), self.counter)
        self._queue.put(t_task)

        # Update counter for the next batch
        self.counter += len(self.frames_buffer)

        # Clear the buffer in the main process
        self.frames_buffer = []

        return

    # ##### PUBLIC METHODS #####
    def add_frame(self, frame: np.ndarray) -> None:
        """
        Method to add a frame to the RAM buffer.

        Args:
            frame (np.ndarray): The frame to buffer.

        Returns:
            ():
        """

        # Store a copy
        self.frames_buffer.append(frame.copy())

        return

    def stop(self) -> None:
        """
        Method to stop the PNG writer and ensure all buffered frames are written to disk.
        Note: The shared worker process remains alive for future recordings.

        Args:
            ():

        Returns:
            ():
        """

        self._write_buffered_frames_async()

        return


class RgbUndistortHandlerCV:
    """
    Class to handle camera undistortion efficiently for frame based RGB images by pre-calculating
    remap matrices once and applying them to incoming frames.
    """

    def __init__(
        self, camera_matrix: np.ndarray, distortion_coefficients: np.ndarray, image_shape: tuple[int, int]
    ) -> None:

        # Extract frame dimensions
        self.__height, self.__width = image_shape

        # Calculate the optimal new camera matrix once, which can be used for undistortion
        # 0 means no free scaling, so the undistorted image will have the same size as the input image
        self.__new_camera_matrix, _ = cv2.getOptimalNewCameraMatrix(
            camera_matrix, distortion_coefficients, (self.__width, self.__height), 0, (self.__width, self.__height)
        )

        # Pre-calculate the maps for cv2.remap
        # Using CV_16SC2 provides a good balance between speed and sub-pixel accuracy
        self.__map_x, self.__map_y = cv2.initUndistortRectifyMap(
            camera_matrix,
            distortion_coefficients,
            np.eye(3),
            self.__new_camera_matrix,
            (self.__width, self.__height),
            cv2.CV_16SC2,
        )

    # ##### GETTER #####
    @property
    def map_x(self) -> np.ndarray:
        """
        Getter for the attribute '__map_x'.

        Args:
            ():

        Returns:
            map_x (np.ndarray): The attribute '__map_x'.
        """

        return self.__map_x

    @property
    def map_y(self) -> np.ndarray:
        """
        Getter for the attribute '__map_y'.

        Args:
            ():

        Returns:
            map_y (np.ndarray): The attribute '__map_y'.
        """

        return self.__map_y

    # ##### PUBLIC METHODS #####
    def apply(self, image: np.ndarray, interpolation: int = cv2.INTER_NEAREST) -> np.ndarray:
        """
        Method to apply the pre-calculated undistortion maps to an input image.
        Defaults to nearest neighbor interpolation for speed, which is often sufficient for event-based vision applications where
        preserving the original pixel noise is important.

        Args:
            image (np.ndarray): The input distorted image to be undistorted.
            interpolation (int, optional): The interpolation method to be used. Defaults to cv2.INTER_NEAREST for speed.

        Returns:
            undistorted_image (np.ndarray): The resulting undistorted image.
        """

        return cv2.remap(image, self.map_x, self.map_y, interpolation)


def resize_image_cv(
    image: np.ndarray,
    target_width: int,
    target_height: int,
    interpolation: int = cv2.INTER_NEAREST,
) -> np.ndarray:
    """
    Function to resize the given image to the specified target width and height using OpenCV.
    Defaults to nearest neighbor interpolation to preserve the original pixel noise, which is often desirable in event-based vision applications.

    Args:
        image (np.ndarray): The input image to be resized.
        target_width (int): The desired width of the output image.
        target_height (int): The desired height of the output image.
        interpolation (int, optional): The interpolation method to be used for resizing. Defaults to cv2.INTER_NEAREST to preserve the original pixel noise.

    Returns:
        resized_image (np.ndarray): The resized image as a NumPy array.
    """

    return cv2.resize(image, (target_width, target_height), interpolation=interpolation)


def bgr2gray_cv(image: np.ndarray) -> np.ndarray:
    """
    Function to convert a BGR image to grayscale using OpenCV.

    Args:
        image (np.ndarray): The input BGR image to be converted.

    Returns:
        gray_image (np.ndarray): The grayscale image as a NumPy array.
    """

    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def gray2bgr_cv(image: np.ndarray) -> np.ndarray:
    """
    Function to convert a grayscale image to BGR using OpenCV.

    Args:
        image (np.ndarray): The input grayscale image to be converted.

    Returns:
        bgr_image (np.ndarray): The BGR image as a NumPy array.
    """

    return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)


def binary_threshold_cv(image: np.ndarray, threshold: int, max_value: int = 255) -> np.ndarray:
    """
    Function to apply binary thresholding to a grayscale image using OpenCV.

    Args:
        image (np.ndarray): The input grayscale image to be thresholded.
        threshold (int): The threshold value.
        max_value (int, optional): The value to set for pixels above the threshold. Defaults to 255.

    Returns:
        mask (np.ndarray): The binary mask as a NumPy array.
    """

    # Initial return is not required since it will be the same as the input threshold for binary
    _, t_mask = cv2.threshold(image, threshold, max_value, cv2.THRESH_BINARY)

    return t_mask


def morphological_closing_cv(image: np.ndarray, kernel_size: int) -> np.ndarray:
    """
    Function to apply morphological closing to a binary image using OpenCV.

    Args:
        image (np.ndarray): The input binary image to be processed.
        kernel_size (int): The size of the structuring element (kernel) for closing.

    Returns:
        closed_image (np.ndarray): The image after morphological closing as a NumPy array.
    """

    t_kernel = np.ones((kernel_size, kernel_size), np.uint8)

    return cv2.morphologyEx(image, cv2.MORPH_CLOSE, t_kernel)


def morphological_opening_cv(image: np.ndarray, kernel_size: int) -> np.ndarray:
    """
    Function to apply morphological opening to a binary image using OpenCV.

    Args:
        image (np.ndarray): The input binary image to be processed.
        kernel_size (int): The size of the structuring element (kernel) for opening.

    Returns:
        opened_image (np.ndarray): The image after morphological opening as a NumPy array.
    """

    t_kernel = np.ones((kernel_size, kernel_size), np.uint8)

    return cv2.morphologyEx(image, cv2.MORPH_OPEN, t_kernel)


def find_external_contours_cv(image: np.ndarray) -> list:
    """
    Function to find external contours in a binary image using OpenCV.

    Args:
        image (np.ndarray): The input binary image to find contours in.

    Returns:
        contours (list): A list of contours found in the image.
    """

    t_contours, _ = cv2.findContours(image, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    return t_contours


def contour_to_bbox_cv(contour: np.ndarray, sam_format: bool = True) -> list[int]:
    """
    Function to create a bounding box from a given contour using OpenCV.

    Args:
        contour (np.ndarray): The contour for which to compute the bounding box.
        sam_format (bool): Whether to return the bounding box in SAM format (x1, y1, x2, y2) or OpenCV format (x, y, w, h). Defaults to True (SAM format).

    Returns:
        bbox (list[int]): The bounding box as (x, y, w, h) or (x1, y1, x2, y2).
    """

    t_x, t_y, t_w, t_h = cv2.boundingRect(contour)

    if sam_format:
        return [t_x, t_y, t_x + t_w, t_y + t_h]

    return [t_x, t_y, t_w, t_h]


def add_weighted_overlay_cv(
    image: np.ndarray, overlay: np.ndarray, alpha: float, beta: float, gamma: float = 0
) -> np.ndarray:
    """
    Function that blends two images together using basic linear multiplication.
    The resulting image is calculated as follows:
    dst = src1 * alpha + src2 * beta + gamma

    Args:
        image (np.ndarray): The first input image.
        overlay (np.ndarray): The second input image of the same size and channel number as the first input image.
        alpha (float): Weight of the first image (image).
        beta (float): Weight of the second image (overlay).
        gamma (float): Scalar added to each sum. Defaults to 0.

    Returns:
        blended_image (np.ndarray): The output image after blending.
    """

    # Ensure that both images have the same size and channel number
    if image.shape != overlay.shape:
        overlay = cv2.resize(overlay, (image.shape[1], image.shape[0]))

    # Blend the images using OpenCV implementation
    t_blended_image = cv2.addWeighted(image, alpha, overlay, beta, gamma)

    return t_blended_image


class Cv2ToBase64Converter:
    """Class for converting OpenCV images to base64 strings using TurboJPEG."""

    def __init__(self):

        # Load the configuration file for the flet parameters
        self.__flet_config = configparser.ConfigParser()
        self.__flet_config.read(Path(__file__).parents[2] / "parameter" / "flet.ini")

        # Parse the camera parameters from the configuration file
        self.__image_quality = self.__flet_config.getint("flet", "image_quality")
        self.__turbojpeg_dll_path = self.__flet_config.get("flet", "turbojpeg_dll_path")

        # Initialize the TurboJPEG encoder with the specified dll path
        self.__turbojpeg_instance = TurboJPEG(self.__turbojpeg_dll_path)

    # ##### GETTER #####
    @property
    def turbojpeg_instance(self) -> TurboJPEG:
        """
        Getter for the attribute '__turbojpeg_instance'.

        Args:
            ():

        Returns:
            turbojpeg_instance (TurboJPEG): The attribute '__turbojpeg_instance'.
        """

        return self.__turbojpeg_instance

    # ##### PUBLIC METHODS #####
    def convert(self, image: np.ndarray) -> str:
        """
        Function to convert an OpenCV image to a base64 string.
        Requires the TurboJPEG library for fast jpeg compression on CPU.

        Args:
            image (np.ndarray): The image to be converted.

        Returns:
            img_base64 (str): The base64 encoded string of the image.
        """

        t_buffer = self.turbojpeg_instance.encode(image, quality=self.__image_quality)
        t_img_base64 = base64.b64encode(t_buffer).decode("utf-8")

        return t_img_base64


def create_image_placeholder(width: int, height: int, annotation: str = "No image", color: str = "#2b2b2b") -> str:
    """
    Function to create a simple SVG placeholder image with given dimensions and annotation text, returned as a base64 data URI.

    Args:
        width (int): The width of the placeholder image.
        height (int): The height of the placeholder image.
        annotation (str): The text to display in the placeholder.
        color (str): The background color of the placeholder image.

    Returns:
        img_base64 (str): The base64-encoded data URI of the SVG placeholder image.
    """

    t_svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">'
        f'<rect width="100%" height="100%" fill="{color}" />'
        f'<text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" '
        f'fill="#cccccc" font-family="Arial, Helvetica, sans-serif" font-size="18">{annotation}</text>'
        "</svg>"
    )

    return "data:image/svg+xml;base64," + base64.b64encode(t_svg.encode("utf-8")).decode("utf-8")
