#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Filename: prophesee.py
Author: Nico Hessenthaler
Date: 2026-06-05
Version: 1.0
Description:
    Module that provides utilities for working with Prophesee cameras.
License: Apache License Version 2.0
Contact: nico.hessenthaler@hs-heilbronn.de
"""

import atexit
import configparser
from .metavision import (
    open_camera_from_serial,
    get_on_demand_frame_generation,
    get_camera_dimension,
    get_camera_slicer,
    load_camera_settings,
    start_event_recording,
    stop_event_recording,
    get_hdf5_event_file_writer,
    add_events_to_recording,
)
from metavision_sdk_core import OnDemandFrameGenerationAlgorithm
from metavision_sdk_stream import Camera, CameraStreamSlicer, HDF5EventFileWriter
from multiprocessing.managers import ValueProxy
from multiprocessing.sharedctypes import SynchronizedArray
from multiprocessing.synchronize import Event as EventProxy
from multiprocessing import Queue
import numpy as np
from .operating_system import print_error, generate_current_timestamp_string
from pathlib import Path


class PropheseeCamera:
    """Class that provides utilities for working with Prophesee even-based cameras."""

    def __init__(
        self,
        shared_memory: SynchronizedArray,
        synchronization_queue: Queue,
        rgb_camera_ready: EventProxy,
        event_recording_path: ValueProxy,
        event_recording_active: EventProxy,
        configuration_file_name: str = "camera.ini",
    ) -> None:

        self.__shared_memory = shared_memory
        self.__synchronization_queue = synchronization_queue
        self.__rgb_camera_ready = rgb_camera_ready
        self.__event_recording_path = event_recording_path
        self.__event_recording_active = event_recording_active
        self.__is_recording = False

        # Sync for rgb camera thread
        self.__capture_synced_frame = False

        # Load the configuration file for the camera parameters
        self.__camera_config = configparser.ConfigParser()
        self.__camera_config.read(Path(__file__).parents[2] / "parameter" / "camera.ini")

        # Load additional configuration file if specified (overwrites existing settings)
        if configuration_file_name != "camera.ini":
            self.__camera_config.read(Path(__file__).parents[2] / "parameter" / configuration_file_name)

        # Parse the camera parameters from the configuration file
        self.__serial_number = self.__camera_config.get("prophesee", "serial_number")
        self.__channels = self.__camera_config.getint("prophesee", "channels")
        self.__settings_file_name = self.__camera_config.get("prophesee", "settings_file_name")
        self.__firmware_version = self.__camera_config.get("prophesee", "firmware_version")
        self.__hardware_generation = self.__camera_config.get("prophesee", "hardware_generation")
        self.__integrator_name = self.__camera_config.get("prophesee", "integrator_name")

        # Generate full path for the camera settings file
        self.__settings_file_path = Path(__file__).parents[2] / "parameter" / self.__settings_file_name

        # Initialize the camera
        self.__prophesee_camera: Camera | None = None
        self.__frame_width: int = 0
        self.__frame_height: int = 0
        self.__image_frame: np.ndarray | None = None
        self.__on_demand_frame_generation: OnDemandFrameGenerationAlgorithm | None = None
        self.__camera_slicer: CameraStreamSlicer | None = None
        self._initialize_prophesee_camera()

        # Get the file writer and append camera metadata
        self.__event_file_writer: HDF5EventFileWriter | None = get_hdf5_event_file_writer()

        # Check if the camera was initialized successfully, otherwise print error message and exit
        self.__camera_available = False
        self._check_camera_availability()

        # Register cleanup function to be called on shutdown
        if self.__camera_available:
            atexit.register(self._cleanup)

    # ##### GETTER #####
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
    def event_recording_path(self) -> ValueProxy:
        """
        Getter for the attribute '__event_recording_path'.

        Args:
            ():

        Returns:
            event_recording_path (ValueProxy): The attribute '__event_recording_path'.
        """

        return self.__event_recording_path

    @property
    def event_recording_active(self) -> EventProxy:
        """
        Getter for the attribute '__event_recording_active'.

        Args:
            ():

        Returns:
            event_recording_active (EventProxy): The attribute '__event_recording_active'.
        """

        return self.__event_recording_active

    @property
    def is_recording(self) -> bool:
        """
        Getter for the attribute '__is_recording'.

        Args:
            ():

        Returns:
            is_recording (bool): The attribute '__is_recording'.
        """

        return self.__is_recording

    @property
    def capture_synced_frame(self) -> bool:
        """
        Getter for the attribute '__capture_synced_frame'.

        Args:
            ():

        Returns:
            capture_synced_frame (bool): The attribute '__capture_synced_frame'.
        """

        return self.__capture_synced_frame

    @property
    def prophesee_camera(self) -> Camera | None:
        """
        Getter for the attribute '__prophesee_camera'.

        Args:
            ():

        Returns:
            prophesee_camera (Camera | None): The attribute '__prophesee_camera'.
        """

        return self.__prophesee_camera

    @property
    def frame_width(self) -> int:
        """
        Getter for the attribute '__frame_width'.

        Args:
            ():

        Returns:
            frame_width (int): The attribute '__frame_width'.
        """

        return self.__frame_width

    @property
    def frame_height(self) -> int:
        """
        Getter for the attribute '__frame_height'.

        Args:
            ():

        Returns:
            frame_height (int): The attribute '__frame_height'.
        """

        return self.__frame_height

    @property
    def image_frame(self) -> np.ndarray | None:
        """
        Getter for the attribute '__image_frame'.

        Args:
            ():

        Returns:
            image_frame (np.ndarray | None): The attribute '__image_frame'.
        """

        return self.__image_frame

    @property
    def on_demand_frame_generation(self) -> OnDemandFrameGenerationAlgorithm | None:
        """
        Getter for the attribute '__on_demand_frame_generation'.

        Args:
            ():

        Returns:
            on_demand_frame_generation (OnDemandFrameGenerationAlgorithm | None): The attribute '__on_demand_frame_generation'.
        """

        return self.__on_demand_frame_generation

    @property
    def camera_slicer(self) -> CameraStreamSlicer | None:
        """
        Getter for the attribute '__camera_slicer'.

        Args:
            ():

        Returns:
            camera_slicer (CameraStreamSlicer | None): The attribute '__camera_slicer'.
        """

        return self.__camera_slicer

    @property
    def event_file_writer(self) -> HDF5EventFileWriter | None:
        """
        Getter for the attribute '__event_file_writer'.

        Args:
            ():

        Returns:
            event_file_writer (HDF5EventFileWriter | None): The attribute '__event_file_writer'.
        """

        return self.__event_file_writer

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
    def settings_file_path(self) -> Path:
        """
        Getter for the attribute '__settings_file_path'.

        Args:
            ():

        Returns:
            settings_file_path (Path): The attribute '__settings_file_path'.
        """

        return self.__settings_file_path

    # ##### SETTER #####
    @shared_memory.setter
    def shared_memory(self, value: SynchronizedArray) -> None:
        """
        Setter for the attribute '__shared_memory'.

        Args:
            value (SynchronizedArray): The new value for the attribute '__shared_memory'.

        Returns:
            ():
        """

        self.__shared_memory = value

        return

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

    @event_recording_path.setter
    def event_recording_path(self, value: ValueProxy) -> None:
        """
        Setter for the attribute '__event_recording_path'.

        Args:
            value (ValueProxy): The new value for the attribute '__event_recording_path'.

        Returns:
            ():
        """

        self.__event_recording_path = value

        return

    @event_recording_active.setter
    def event_recording_active(self, value: EventProxy) -> None:
        """
        Setter for the attribute '__event_recording_active'.

        Args:
            value (EventProxy): The new value for the attribute '__event_recording_active'.

        Returns:
            ():
        """

        self.__event_recording_active = value

        return

    @is_recording.setter
    def is_recording(self, value: bool) -> None:
        """
        Setter for the attribute '__is_recording'.

        Args:
            value (bool): The new value for the attribute '__is_recording'.

        Returns:
            ():
        """

        self.__is_recording = value

        return

    @capture_synced_frame.setter
    def capture_synced_frame(self, value: bool) -> None:
        """
        Setter for the attribute '__capture_synced_frame'.

        Args:
            value (bool): The new value for the attribute '__capture_synced_frame'.

        Returns:
            ():
        """

        self.__capture_synced_frame = value

        return

    @prophesee_camera.setter
    def prophesee_camera(self, value: Camera | None) -> None:
        """
        Setter for the attribute '__prophesee_camera'.

        Args:
            value (Camera | None): The new value for the attribute '__prophesee_camera'.

        Returns:
            ():
        """

        self.__prophesee_camera = value

        return

    @frame_width.setter
    def frame_width(self, value: int) -> None:
        """
        Setter for the attribute '__frame_width'.

        Args:
            value (int): The new value for the attribute '__frame_width'.

        Returns:
            ():
        """

        self.__frame_width = value

        return

    @frame_height.setter
    def frame_height(self, value: int) -> None:
        """
        Setter for the attribute '__frame_height'.

        Args:
            value (int): The new value for the attribute '__frame_height'.

        Returns:
            ():
        """

        self.__frame_height = value

        return

    @image_frame.setter
    def image_frame(self, value: np.ndarray | None) -> None:
        """
        Setter for the attribute '__image_frame'.

        Args:
            value (np.ndarray | None): The new value for the attribute '__image_frame'.

        Returns:
            ():
        """

        self.__image_frame = value

        return

    @on_demand_frame_generation.setter
    def on_demand_frame_generation(self, value: OnDemandFrameGenerationAlgorithm | None) -> None:
        """
        Setter for the attribute '__on_demand_frame_generation'.

        Args:
            value (OnDemandFrameGenerationAlgorithm | None): The new value for the attribute '__on_demand_frame_generation'.

        Returns:
            ():
        """

        self.__on_demand_frame_generation = value

        return

    @camera_slicer.setter
    def camera_slicer(self, value: CameraStreamSlicer | None) -> None:
        """
        Setter for the attribute '__camera_slicer'.

        Args:
            value (CameraStreamSlicer | None): The new value for the attribute '__camera_slicer'.

        Returns:
            ():
        """

        self.__camera_slicer = value

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

    @event_file_writer.setter
    def event_file_writer(self, value: HDF5EventFileWriter | None) -> None:
        """
        Setter for the attribute '__event_file_writer'.

        Args:
            value (HDF5EventFileWriter | None): The new value for the attribute '__event_file_writer'.

        Returns:
            ():
        """

        self.__event_file_writer = value

        return

    @settings_file_path.setter
    def settings_file_path(self, value: Path) -> None:
        """
        Setter for the attribute '__settings_file_path'.

        Args:
            value (Path): The new value for the attribute '__settings_file_path'.

        Returns:
            ():
        """

        self.__settings_file_path = value

        return

    # ##### PRIVATE METHODS #####
    def _initialize_prophesee_camera(self) -> None:
        """
        Method to initialize the Prophesee camera. This includes:
        - Opening the camera stream
        - Opening the events iterator
        - Getting the image dimensions
        - Initializing the image frame

        Args:
            ():

        Returns:
            ():
        """

        # Wait for the RGB camera to be ready to avoid memory overflow
        self.__rgb_camera_ready.wait()

        self.prophesee_camera = open_camera_from_serial(self.__serial_number)
        t_settings_loading_success = load_camera_settings(self.prophesee_camera, self.settings_file_path)

        if self.prophesee_camera is not None and t_settings_loading_success:
            self.frame_width, self.frame_height = get_camera_dimension(self.prophesee_camera)
            self.image_frame = np.zeros((self.frame_height, self.frame_width, self.__channels), dtype=np.uint8)
            self.on_demand_frame_generation = get_on_demand_frame_generation(self.frame_width, self.frame_height)
            self.camera_slicer = get_camera_slicer(self.prophesee_camera)

            if self.on_demand_frame_generation is not None:
                self.on_demand_frame_generation.set_colors(
                    background_color=[255, 249, 248],  # Default light background color from flet
                    on_color=[158, 79, 0],  # Blue color
                    off_color=[125, 157, 29],  # Green color
                    colored=True,
                )

        return

    def _check_camera_availability(self) -> None:
        """
        Method to check the availability of the camera.

        Args:
            ():

        Returns:
            ():
        """

        if (
            self.prophesee_camera is not None
            and self.frame_width != 0
            and self.frame_height != 0
            and self.on_demand_frame_generation is not None
            and self.camera_slicer is not None
        ):
            self.camera_available = True

        else:
            self.camera_available = False
            print_error("Prophesee camera is not available. Please check the error messages above for more details")

        return

    def _cleanup(self) -> None:
        """
        Method to clean up the camera resources on shutdown.

        Args:
            ():

        Returns:
            ():
        """

        return

    def _read_synchronization_queue(self) -> None:
        """
        Method to read the synchronization queue for the Prophesee camera.
        This is used to synchronize the frame generation with the RGB camera thread.

        Args:
            ():

        Returns:
            ():
        """

        if not self.synchronization_queue.empty():
            t_message = self.synchronization_queue.get()
            if t_message:
                self.capture_synced_frame = True

        return

    def _check_recording_control(self) -> None:
        """
        Method to check the recording control from the shared memory event and start/stop recording accordingly.

        Args:
            ():

        Returns:
            ():
        """

        # Check if recording should be active
        if self.event_recording_active.is_set():
            if not self.is_recording:
                t_success = start_event_recording(
                    self.event_file_writer,
                    self.event_recording_path.value,
                    generate_current_timestamp_string("%Y-%m-%d %H:%M:%S"),
                    self.__firmware_version,
                    self.__hardware_generation,
                    f"{self.frame_width}x{self.frame_height}",
                    self.__integrator_name,
                    self.__serial_number,
                )
                if t_success:
                    self.is_recording = True

        else:
            if self.is_recording:
                t_success = stop_event_recording(self.event_file_writer)
                if t_success:
                    self.is_recording = False

        return

    def _capture_continuous(self) -> None:
        """
        Function to capture frames continuously from the Prophesee camera, generate image frames on demand and push them to shared memory.

        Args:
            ():

        Returns:
            ():
        """

        # Initialize a timestamp to track the previous slice's end, ensuring we don't go backwards
        t_last_timestamp = 0

        for t_slice in self.camera_slicer:

            # Process events if they exist
            if t_slice.events.size != 0:

                t_events = t_slice.events

                # Always feed the raw events to the frame generation for low-latency buffer management
                self.on_demand_frame_generation.process_events(t_events)

                # Record raw events whenever recording is active
                if self.is_recording:
                    add_events_to_recording(self.event_file_writer, t_events)

                # Update the last known timestamp
                t_last_timestamp = t_events["t"][-1]

            # Check if event recording should be started or stopped
            self._check_recording_control()

            # Read the synchronization queue for new frame request
            self._read_synchronization_queue()

            if self.capture_synced_frame:
                # Handle visualization - use the last known continuous timestamp to avoid backward jumps
                self.on_demand_frame_generation.generate(t_last_timestamp, self.image_frame)
                self.shared_memory.put(self.image_frame)

                # Reset the flag to capture the next frame on demand
                self.capture_synced_frame = False

        return

    # ##### PUBLIC METHODS #####
    def capture_manager(self) -> None:
        """
        Method to capture frames from the Prophesee camera.

        Args:
            ():

        Returns:
            ():
        """

        if self.camera_available:
            self._capture_continuous()

        return


def prophesee_worker(
    shared_memory: SynchronizedArray,
    synchronization_queue: Queue,
    rgb_camera_ready: EventProxy,
    event_recording_path: ValueProxy,
    event_recording_active: EventProxy,
    configuration_file_name: str = "camera.ini",
) -> None:
    """
    Worker function to capture frames from the Prophesee camera and push them to shared memory.
    This function is intended to be run in a separate process.

    Args:
        shared_memory (SynchronizedArray): The shared memory object that is used to store the captured frames.
        synchronization_queue (Queue): The queue used for synchronization between the Prophesee camera and the RGB camera threads.
        rgb_camera_ready (EventProxy): Shared memory event for signaling that the RGB camera and YOLO model are ready.
        event_recording_path (ValueProxy): Shared memory value for the recording file path.
        event_recording_active (EventProxy): Shared memory event for signaling that recording is active.
        configuration_file_name (str): The name of the configuration file to load.

    Returns:
        ():
    """

    try:
        t_prophesee_camera_instance = PropheseeCamera(
            shared_memory,
            synchronization_queue,
            rgb_camera_ready,
            event_recording_path,
            event_recording_active,
            configuration_file_name,
        )
        t_prophesee_camera_instance.capture_manager()

    # Handle shutdown of the worker process gracefully
    except KeyboardInterrupt:
        pass

    return
