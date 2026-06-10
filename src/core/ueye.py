#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Filename: ueye.py
Author: Nico Hessenthaler
Date: 2026-06-05
Version: 1.0
Description:
    Module that provides utilities for working with IDS uEye cameras.
License: Apache License Version 2.0
Contact: nico.hessenthaler@hs-heilbronn.de
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyueye import ueye

try:
    from pyueye import ueye

    IMPORT_UEYE_SUCCESS = True
except ImportError:
    IMPORT_UEYE_SUCCESS = False

import atexit
import configparser
from .image_processing import PNGWriterCV
from multiprocessing.managers import ValueProxy
from multiprocessing.sharedctypes import SynchronizedArray
from multiprocessing.synchronize import Event as EventProxy
from multiprocessing import Queue
import numpy as np
from .operating_system import print_error
from pathlib import Path


class UeyeCamera:
    """Class that provides utilities for working with IDS uEye cameras. It will push a continuous stream of images to the shared memory of the GUI,
    depending on the configuration file. The camera settings can also be configured via the configuration file."""

    def __init__(
        self,
        shared_memory: SynchronizedArray,
        synchronization_queue: Queue,
        rgb_recording_path: ValueProxy[str],
        rgb_recording_active: EventProxy,
        rgb_camera_ready: EventProxy,
        configuration_file_name: str = "camera.ini",
    ) -> None:

        self.__shared_memory = shared_memory
        self.__synchronization_queue = synchronization_queue
        self.__rgb_recording_path = rgb_recording_path
        self.__rgb_recording_active = rgb_recording_active
        self.__rgb_camera_ready = rgb_camera_ready

        self.__camera_available = False
        self._check_camera_availability()

        # Load the configuration file for the camera parameters
        self.__camera_config = configparser.ConfigParser()
        self.__camera_config.read(Path(__file__).parents[2] / "parameter" / "camera.ini")

        # Load additional configuration file if specified (overwrites existing settings)
        if configuration_file_name != "camera.ini":
            self.__camera_config.read(Path(__file__).parents[2] / "parameter" / configuration_file_name)

        # Parse the camera parameters from the configuration file
        self.__continuous_capture = self.__camera_config.getboolean("ueye", "continuous_capture")
        self.__crop_aoi = tuple(map(int, self.__camera_config.get("ueye", "crop_aoi").strip("()").split(",")))
        self.__exposure_time = self.__camera_config.getfloat("ueye", "exposure_time")
        self.__gain_value = self.__camera_config.getint("ueye", "gain_value")
        self.__gamma_value = self.__camera_config.getint("ueye", "gamma_value")
        self.__wb_red_gain = self.__camera_config.getint("ueye", "wb_red_gain")
        self.__wb_green_gain = self.__camera_config.getint("ueye", "wb_green_gain")
        self.__wb_blue_gain = self.__camera_config.getint("ueye", "wb_blue_gain")
        self.__channel = self.__camera_config.getint("ueye", "channel")
        self.__bits_per_pixel = self.__camera_config.getint("ueye", "bits_per_pixel")
        self.__pixel_clock_frequency = self.__camera_config.getint("ueye", "pixel_clock_frequency")
        self.__fps = self.__camera_config.getfloat("ueye", "fps")
        self.__nth_frame = self.__camera_config.getint("ueye", "nth_frame")

        # Initialize the PNG writer
        self.__png_writer: PNGWriterCV | None = None

        # Initialize the camera and store the handle
        if self.__camera_available:
            self.__ueye_handle = ueye.HIDS(0)
            self.__memory_pointer = ueye.c_mem_p()
            self.__memory_id = ueye.int()
            self.__enable_event = None
            t_return = ueye.is_InitCamera(self.__ueye_handle, None)
            if t_return != ueye.IS_SUCCESS:
                self.__camera_available = False
                print_error("Failed to initialize the uEye camera")
                exit(1)
            atexit.register(self._cleanup)

        # Load the current settings
        self.initialize_settings()

        # Setup the event based capture and start capturing frames based on events (new image frame available)
        if self.__camera_available:
            # Signal that the RGB camera is ready
            self.__rgb_camera_ready.set()
            self._setup_event_based_capture()

    # ##### GETTER #####
    @property
    def synchronization_queue(self) -> Queue:
        """
        Getter for the attribute '__synchronization_queue'.

        Args:
            ():

        Returns:
            synchronization_queue (Queue): The attribute '__synchronization_queue'.
        """

        return self.__synchronization_queue

    @property
    def rgb_recording_path(self) -> ValueProxy[str]:
        """
        Getter for the attribute '__rgb_recording_path'.

        Args:
            ():

        Returns:
            rgb_recording_path (ValueProxy[str]): The attribute '__rgb_recording_path'.
        """

        return self.__rgb_recording_path

    @property
    def rgb_recording_active(self) -> EventProxy:
        """
        Getter for the attribute '__rgb_recording_active'.

        Args:
            ():

        Returns:
            rgb_recording_active (EventProxy): The attribute '__rgb_recording_active'.
        """

        return self.__rgb_recording_active

    @property
    def png_writer(self) -> PNGWriterCV | None:
        """
        Getter for the attribute '__png_writer'.

        Args:
            ():

        Returns:
            png_writer (PNGWriterCV | None): The attribute '__png_writer'.
        """

        return self.__png_writer

    @property
    def camera_available(self) -> bool:
        """
        Getter for the attribute '__camera_available'.

        Args:
            ():

        Returns:
            camera_available (bool): The attribute '__camera_available'.
        """

        return self.__camera_available

    @property
    def ueye_handle(self) -> ueye.HIDS:
        """
        Getter for the attribute '__ueye_handle'.

        Args:
            ():

        Returns:
            ueye_handle (ueye.HIDS): The attribute '__ueye_handle'.
        """

        return self.__ueye_handle

    @property
    def memory_pointer(self) -> ueye.c_mem_p:
        """
        Getter for the attribute '__memory_pointer'.

        Args:
            ():

        Returns:
            memory_pointer (ueye.c_mem_p): The attribute '__memory_pointer'.
        """

        return self.__memory_pointer

    @property
    def memory_id(self) -> ueye.int:
        """
        Getter for the attribute '__memory_id'.

        Args:
            ():

        Returns:
            memory_id (ueye.int): The attribute '__memory_id'.
        """

        return self.__memory_id

    @property
    def enable_event(self) -> ueye.c_uint:
        """
        Getter for the attribute '__enable_event'.

        Args:
            ():

        Returns:
            enable_event (ueye.c_uint): The attribute '__enable_event'.
        """

        return self.__enable_event

    @property
    def shared_memory(self) -> SynchronizedArray:
        """
        Getter for the attribute '__shared_memory'.

        Args:
            ():

        Returns:
            shared_memory (SynchronizedArray): The attribute '__shared_memory'.
        """
        return self.__shared_memory

    # ##### SETTER #####
    @synchronization_queue.setter
    def synchronization_queue(self, value: Queue) -> None:
        """
        Setter for the attribute '__synchronization_queue'.

        Args:
            value (Queue): The new value for the attribute '__synchronization_queue'.

        Returns:
            ():
        """

        self.__synchronization_queue = value

        return

    @rgb_recording_path.setter
    def rgb_recording_path(self, value: ValueProxy[str]) -> None:
        """
        Setter for the attribute '__rgb_recording_path'.

        Args:
            value (ValueProxy[str]): The new value for the attribute '__rgb_recording_path'.

        Returns:
            ():
        """

        self.__rgb_recording_path = value

        return

    @rgb_recording_active.setter
    def rgb_recording_active(self, value: EventProxy) -> None:
        """
        Setter for the attribute '__rgb_recording_active'.

        Args:
            value (EventProxy): The new value for the attribute '__rgb_recording_active'.

        Returns:
            ():
        """

        self.__rgb_recording_active = value

        return

    @png_writer.setter
    def png_writer(self, value: PNGWriterCV | None) -> None:
        """
        Setter for the attribute '__png_writer'.

        Args:
            value (PNGWriterCV | None): The new value for the attribute '__png_writer'.

        Returns:
            ():
        """

        self.__png_writer = value

        return

    @camera_available.setter
    def camera_available(self, value: bool) -> None:
        """
        Setter for the attribute '__camera_available'.

        Args:
            value (bool): The new value for the attribute '__camera_available'.

        Returns:
            ():
        """

        self.__camera_available = value

        return

    @ueye_handle.setter
    def ueye_handle(self, value: ueye.HIDS) -> None:
        """
        Setter for the attribute '__ueye_handle'.

        Args:
            value (ueye.HIDS): The new value for the attribute '__ueye_handle'.

        Returns:
            ():
        """

        self.__ueye_handle = value

        return

    @memory_pointer.setter
    def memory_pointer(self, value: ueye.c_mem_p) -> None:
        """
        Setter for the attribute '__memory_pointer'.

        Args:
            value (ueye.c_mem_p): The new value for the attribute '__memory_pointer'.

        Returns:
            ():
        """

        self.__memory_pointer = value

        return

    @memory_id.setter
    def memory_id(self, value: ueye.int) -> None:
        """
        Setter for the attribute '__memory_id'.

        Args:
            value (ueye.int): The new value for the attribute '__memory_id'.

        Returns:
            ():
        """

        self.__memory_id = value

        return

    @enable_event.setter
    def enable_event(self, value: ueye.c_uint) -> None:
        """
        Setter for the attribute '__enable_event'.

        Args:
            value (ueye.c_uint): The new value for the attribute '__enable_event'.

        Returns:
            ():
        """

        self.__enable_event = value

        return

    # ##### PRIVATE METHODS #####
    def _check_camera_availability(self) -> None:
        """
        Method to check the availability of the camera.

        Args:
            ():

        Returns:
            ():
        """

        if IMPORT_UEYE_SUCCESS:
            self.camera_available = True

        else:
            self.camera_available = False
            print_error(
                "RGB camera (uEye) is not available. Please check the connection and the installation of the required uEye drivers"
            )

        return

    def _cleanup(self) -> None:
        """
        Method to clean up the camera resources.

        Args:
            ():

        Returns:
            ():
        """

        if self.camera_available:
            if self.enable_event is not None:
                ueye.is_Event(
                    self.ueye_handle, ueye.IS_EVENT_CMD_DISABLE, self.enable_event, ueye.sizeof(self.enable_event)
                )
                ueye.is_Event(
                    self.ueye_handle, ueye.IS_EVENT_CMD_EXIT, self.enable_event, ueye.sizeof(self.enable_event)
                )
            ueye.is_StopLiveVideo(self.ueye_handle, ueye.IS_FORCE_VIDEO_STOP)
            ueye.is_FreeImageMem(self.ueye_handle, self.memory_pointer, self.memory_id)
            ueye.is_ExitCamera(self.ueye_handle)

        return

    def _check_recording_control(self) -> None:
        """
        Method to check the recording control from the shared memory and start or stop the png writer accordingly.

        Args:
            ():

        Returns:
            ():
        """

        # Check for recording status from shared memory (Value/Event) instead of Queue
        if self.rgb_recording_active.is_set() and self.png_writer is None:
            self.png_writer = PNGWriterCV(
                output_dir=self.rgb_recording_path.value, prefix="", nth_frame=self.__nth_frame
            )
        elif not self.rgb_recording_active.is_set() and self.png_writer is not None:
            self.png_writer.stop()
            self.png_writer = None

        return

    def _check_camera_settings_error(self, t_return: int, setting_name: str) -> None:
        """
        Method to check the return value of a uEye camera settings function and print an error message if the return value indicates an error.

        Args:
            t_return (int): The return value of a uEye camera settings function.
            setting_name (str): The name of the camera setting that was attempted to be set, for better error messages.

        Returns:
            ():
        """

        if t_return != ueye.IS_SUCCESS:
            print_error(f"Failed to set parameter '{setting_name}'. Return value: {t_return}")
            self._cleanup()
            exit(1)

        return

    def _set_color_mode(self, color_mode: int) -> None:
        """
        Method to set the color mode of the uEye camera.
        Options are IS_CM_BGR8_PACKED for color images, IS_CM_MONO8 for grayscale images. More color modes are available in the
        uEye documentation.

        Args:
            color_mode (int): The color mode to set.

        Returns:
            ():
        """

        if self.camera_available:
            t_return = ueye.is_SetColorMode(self.ueye_handle, color_mode)
            self._check_camera_settings_error(t_return, "ColorMode")

        return

    def _set_trigger_mode(self, trigger_mode: int) -> None:
        """
        Method to set the trigger mode of the uEye camera.
        Options are IS_SET_TRIGGER_OFF for free running mode, IS_SET_TRIGGER_SOFTWARE for software trigger.
        More trigger modes are available in the uEye documentation.

        Args:
            trigger_mode (int): The trigger mode to set.

        Returns:
            ():
        """

        if self.camera_available:
            t_return = ueye.is_SetExternalTrigger(self.ueye_handle, trigger_mode)
            self._check_camera_settings_error(t_return, "ExternalTrigger")

        return

    def _set_exposure_time(self, exposure_time: float) -> None:
        """
        Method to set the exposure time of the uEye camera.

        Args:
            exposure_time (float): The exposure time to set in milliseconds.

        Returns:
            ():
        """

        if self.camera_available:
            t_return = ueye.is_Exposure(
                self.ueye_handle,
                ueye.IS_EXPOSURE_CMD_SET_EXPOSURE,
                ueye.c_double(exposure_time),
                ueye.sizeof(ueye.c_double),
            )
            self._check_camera_settings_error(t_return, "ExposureTime")

        return

    def _set_hardware_gain(self, gain_value: int) -> None:
        """
        Method to set the hardware gain of the uEye camera.

        Args:
            gain_value (int): The gain value to set in percent (0-100).

        Returns:
            ():
        """

        if self.camera_available:
            t_return = ueye.is_SetHardwareGain(
                self.ueye_handle,
                gain_value,
                ueye.IS_IGNORE_PARAMETER,
                ueye.IS_IGNORE_PARAMETER,
                ueye.IS_IGNORE_PARAMETER,
            )
            self._check_camera_settings_error(t_return, "HardwareGain")

        return

    def _set_gamma(self, gamma_value: int) -> None:
        """
        Method to set the gamma of the uEye camera.

        Args:
            gamma_value (int): The gamma value to set (0-255).

        Returns:
            ():
        """

        if self.camera_available:
            t_return = ueye.is_Gamma(
                self.ueye_handle, ueye.IS_GAMMA_CMD_SET, ueye.c_uint(gamma_value), ueye.sizeof(ueye.c_uint)
            )
            self._check_camera_settings_error(t_return, "Gamma")

        return

    def _set_auto_white_balance(self) -> None:
        """
        Method to set the auto white balance of the uEye camera für industrial applications (not deterministic!).

        Args:
            ():

        Returns:
            ():
        """

        if self.camera_available:
            t_return = ueye.is_SetAutoParameter(
                self.ueye_handle,
                ueye.IS_SET_ENABLE_AUTO_WHITEBALANCE,
                ueye.c_double(ueye.WB_MODE_DISABLE),
                ueye.c_double(ueye.WB_MODE_DISABLE),
            )
            self._check_camera_settings_error(t_return, "AutoWhiteBalance")

        return

    def _set_manual_white_balance(self, red_value: int, green_value: int, blue_value: int) -> None:
        """
        Method to set the manual white balance of the uEye camera for industrial applications (more deterministic than auto white balance).

        Args:
            red_value (int): The red channel white balance value to set in percent (0-100).
            green_value (int): The green channel white balance value to set in percent (0-100).
            blue_value (int): The blue channel white balance value to set in percent (0-100).

        Returns:
            ():
        """

        if self.camera_available:
            t_return = ueye.is_SetHardwareGain(
                self.ueye_handle,
                ueye.IS_IGNORE_PARAMETER,  # Master Gain unverändert
                red_value,
                green_value,
                blue_value,
            )
            self._check_camera_settings_error(t_return, "ManualWhiteBalance")

        return

    def _set_area_of_interest(self, image_area: tuple[int, int, int, int]) -> None:
        """
        Method to set the area of interest (crop region) of the uEye camera.

        Args:
            image_area (tuple[int, int, int, int]): The image area to set in the format (x, y, width, height).

        Returns:
            ():
        """

        if self.camera_available:
            t_rect_aoi = ueye.IS_RECT()
            t_rect_aoi.s32X = ueye.INT(image_area[0])
            t_rect_aoi.s32Y = ueye.INT(image_area[1])
            t_rect_aoi.s32Width = ueye.INT(image_area[2])
            t_rect_aoi.s32Height = ueye.INT(image_area[3])

            t_return = ueye.is_AOI(self.ueye_handle, ueye.IS_AOI_IMAGE_SET_AOI, t_rect_aoi, ueye.sizeof(t_rect_aoi))
            self._check_camera_settings_error(t_return, "AreaOfInterest")

        return

    def _set_frame_rate(self, fps: float) -> None:
        """
        Method to set the frame rate of the uEye camera.

        Args:
            fps (float): The frame rate to set in frames per second.

        Returns:
            ():
        """

        if self.camera_available:
            t_return = ueye.is_SetFrameRate(self.ueye_handle, fps, ueye.c_double())
            self._check_camera_settings_error(t_return, "FrameRate")

        return

    def _set_pixel_clock_frequency(self, frequency: float) -> None:
        """
        Method to set the pixel clock frequency of the uEye camera.

        Args:
            frequency (float): The pixel clock frequency to set in MHz.

        Returns:
            ():
        """

        if self.camera_available:
            t_return = ueye.is_PixelClock(
                self.ueye_handle, ueye.IS_PIXELCLOCK_CMD_SET, ueye.c_int(frequency), ueye.sizeof(ueye.c_int)
            )
            self._check_camera_settings_error(t_return, "PixelClockFrequency")

        return

    def _allocate_image_memory(self, width: int, height: int, bits_per_pixel: int) -> None:
        """
        Method to allocate image memory for the uEye camera and set it as an active image memory.

        Args:
            width (int): The width of the image in pixels.
            height (int): The height of the image in pixels.
            bits_per_pixel (int): The number of bits per pixel.

        Returns:
            ():
        """
        # Allocate the memory
        t_return = ueye.is_AllocImageMem(
            self.ueye_handle,
            width,
            height,
            bits_per_pixel,
            self.memory_pointer,
            self.memory_id,
        )
        self._check_camera_settings_error(t_return, "AllocImageMemory")

        # Set the allocated memory as active image memory
        t_return = ueye.is_SetImageMem(self.ueye_handle, self.memory_pointer, self.memory_id)
        self._check_camera_settings_error(t_return, "SetImageMemory")

        return

    def _setup_event_based_capture(self) -> None:
        """
        Method to set up the event based capture for the uEye camera (waiting for the next frame of the image).
        This is not related to an event camera, but to the uEye camera itself, which can trigger an event when a new image frame is available.

        Args:
            ():

        Returns:
            ():
        """

        # Register the wait event to wait for the next image and start capturing video in continuous mode
        t_event = ueye.c_uint(ueye.IS_SET_EVENT_FRAME)
        t_init_event = ueye.IS_INIT_EVENT(nEvent=t_event.value, bManualReset=False, bInitialState=False)
        ueye.is_Event(self.ueye_handle, ueye.IS_EVENT_CMD_INIT, t_init_event, ueye.sizeof(t_init_event))

        # Activate the wait event
        self.enable_event = ueye.c_uint(t_event.value)
        ueye.is_Event(self.ueye_handle, ueye.IS_EVENT_CMD_ENABLE, self.enable_event, ueye.sizeof(self.enable_event))

        # Start the video capture in continuous mode
        ueye.is_CaptureVideo(self.ueye_handle, ueye.IS_WAIT)

        return

    def _capture_single(self, width: int, height: int, channel: int, timeout_ms: int = 1000) -> None:
        """
        Method to capture a single frame from the uEye camera and return it as a NumPy array.

        Args:
            width (int): The width of the image in pixels.
            height (int): The height of the image in pixels.
            channel (int): The number of image channels (e.g. 3 for color images, 1 for grayscale images).
            timeout_ms (int): Maximum time to wait for a frame in milliseconds. Default is 1000.

        Returns:
            np.ndarray | None: The captured frame as a NumPy array with shape (height, width, channel),
            or `None` if the camera is unavailable or a timeout/error occurred.
        """

        if not self.camera_available:
            return

        # Wait for a single frame
        t_wait_event = ueye.IS_WAIT_EVENT(
            nEvent=self.enable_event.value, nTimeoutMilliseconds=timeout_ms, nSignaled=0, nSetCount=0
        )
        t_return = ueye.is_Event(self.ueye_handle, ueye.IS_EVENT_CMD_WAIT, t_wait_event, ueye.sizeof(t_wait_event))

        if t_return == ueye.IS_SUCCESS:
            t_array = ueye.get_data(
                self.memory_pointer,
                width,
                height,
                self.__bits_per_pixel,
                width * channel,
                copy=True,
            )

            # Signal the event camera to accumulate events for pseudo frame
            self.synchronization_queue.put(True)
            t_frame = np.reshape(t_array, (height, width, channel))

            # Push the captured frame to the shared memory
            self.shared_memory.put(t_frame)

        return

    def _capture_continuous(self, width: int, height: int, channel: int) -> None:
        """
        Method to capture frames from the uEye camera continuously. The captured frames are triggered based on events of the ueye camera.

        Args:
            width (int): The width of the image in pixels.
            height (int): The height of the image in pixels.
            channel (int): The number of image channels (e.g. 3 for color images, 1 for grayscale images).

        Returns:
            ():
        """

        while True:

            # Check whether recording of video is required
            self._check_recording_control()

            # Register wating for the next frame event
            t_wait_event = ueye.IS_WAIT_EVENT(
                nEvent=self.enable_event.value, nTimeoutMilliseconds=1000, nSignaled=0, nSetCount=0
            )
            t_return = ueye.is_Event(self.ueye_handle, ueye.IS_EVENT_CMD_WAIT, t_wait_event, ueye.sizeof(t_wait_event))

            if t_return == ueye.IS_SUCCESS:
                # Signal the event camera to accumulate events
                self.synchronization_queue.put(True)
                t_array = ueye.get_data(
                    self.memory_pointer, width, height, self.__bits_per_pixel, width * channel, copy=True
                )

                t_frame = np.reshape(t_array, (height, width, channel))

                # Add raw frame to PNG writer if recording is active
                if self.png_writer is not None:
                    self.png_writer.add_frame(t_frame)

                # Push the captured frame to the shared memory
                self.shared_memory.put(t_frame)

        return

    # ##### PUBLIC METHODS #####
    def initialize_settings(self) -> None:
        """
        Method to initialize the settings of the uEye camera based on the parameters from the configuration file.

        Args:
            ():

        Returns:
            ():
        """

        if self.camera_available:
            self._set_color_mode(ueye.IS_CM_BGR8_PACKED)
            self._set_trigger_mode(ueye.IS_SET_TRIGGER_OFF)
            self._set_exposure_time(self.__exposure_time)
            self._set_hardware_gain(self.__gain_value)
            self._set_gamma(self.__gamma_value)
            self._set_area_of_interest(self.__crop_aoi)
            self._set_auto_white_balance()
            self._set_manual_white_balance(self.__wb_red_gain, self.__wb_green_gain, self.__wb_blue_gain)
            self._set_pixel_clock_frequency(self.__pixel_clock_frequency)
            self._set_frame_rate(self.__fps)
            self._allocate_image_memory(self.__crop_aoi[2], self.__crop_aoi[3], self.__bits_per_pixel)

        return

    def capture_manager(self) -> None:
        """
        Manager method to capture frames from the uEye camera. Depending on the configuration,
        it will either capture frames continuously or capture single frames.

        Args:
            ():

        Returns:
            ():
        """

        # Continuously capture frames if enabled in the configuration file, otherwise capture single frames.
        # If no camera is available, do nothing.
        if self.camera_available and self.__continuous_capture:
            self._capture_continuous(self.__crop_aoi[2], self.__crop_aoi[3], self.__channel)

        # Single capture mode can be used for testing and debugging, e.g. to test the camera settings.
        elif self.camera_available and not self.__continuous_capture:
            self._capture_single(self.__crop_aoi[2], self.__crop_aoi[3], self.__channel)

        else:
            pass

        return


def ueye_worker(
    shared_memory: SynchronizedArray,
    synchronization_queue: Queue,
    rgb_recording_path: ValueProxy[str],
    rgb_recording_active: EventProxy,
    rgb_camera_ready: EventProxy,
    configuration_file_name: str = "camera.ini",
) -> None:
    """
    Worker function to capture frames from the uEye camera and push them to the shared memory of the GUI.
    This function is intended to be run in a separate process.

    Args:
        shared_memory (SynchronizedArray): The shared memory object that is used to store the captured frames.
        synchronization_queue (Queue): The queue used for synchronization between the uEye camera and other threads.
        rgb_recording_path (ValueProxy[str]): Shared memory value for the RGB recording path.
        rgb_recording_active (EventProxy): Shared memory event for triggering RGB recording.
        rgb_camera_ready (EventProxy): Shared memory event for signaling that the RGB camera and YOLO model are ready.
        configuration_file_name (str): The name of the configuration file to load.

    Returns:
        ():
    """

    try:
        t_ueye_camera_instance = UeyeCamera(
            shared_memory,
            synchronization_queue,
            rgb_recording_path,
            rgb_recording_active,
            rgb_camera_ready,
            configuration_file_name,
        )
        t_ueye_camera_instance.capture_manager()

    # Handle shutdown of the worker process gracefully
    except KeyboardInterrupt:
        pass

    return
