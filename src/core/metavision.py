#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Filename: metavision.py
Author: Nico Hessenthaler
Date: 2026-06-05
Version: 1.0
Description:
    Module that provides utilities for interacting with Metavision cameras and event data.
License: Apache License Version 2.0
Contact: nico.hessenthaler@hs-heilbronn.de
"""

from __future__ import annotations
from typing import TYPE_CHECKING

import numpy as np
from .operating_system import print_error, check_file_exists
from pathlib import Path

# Prevent type checking errors
if TYPE_CHECKING:
    from metavision_core.event_io import EventsIterator
    from metavision_hal import DeviceDiscovery, Device
    from metavision_sdk_core import OnDemandFrameGenerationAlgorithm
    from metavision_sdk_stream import Camera, CameraStreamSlicer, HDF5EventFileWriter
    from metavision_sdk_ui import MTWindow, BaseWindow, UIKeyEvent

# Try importing Metavision SDK modules and handle ImportError gracefully
try:
    from metavision_core.event_io import EventsIterator
    from metavision_hal import DeviceDiscovery, Device
    from metavision_sdk_core import OnDemandFrameGenerationAlgorithm
    from metavision_sdk_stream import Camera, CameraStreamSlicer, HDF5EventFileWriter
    from metavision_sdk_ui import MTWindow, BaseWindow, UIKeyEvent
except ImportError:
    print_error(
        "Metavision SDK is not installed or could not be imported. Please ensure that the Metavision SDK is properly installed and configured."
    )


def get_available_prophesee_devices() -> list[str]:
    """
    Function that returns all serial numbers of connected Prophesee devices.
    Alternatively, the serial number is also available on the sticker on the device itself,
    but in slightly different format. Format on sticker: "P50271".

    Args:
        ():

    Returns:
        t_serial_numbers (list[str]): List of serial numbers of connected Prophesee devices.
    """

    # List method returns a list of strings containing information about connected devices.
    # E.g., "Prophesee:hal_plugin_prophesee:00050271".
    t_devices = DeviceDiscovery.list()

    # The serial number is the last part after the last colon.
    # Extract the serial numbers from the device strings.
    t_serial_numbers = [t_device.split(":")[-1] for t_device in t_devices]

    return t_serial_numbers


def check_serial_number_validity(serial: str) -> bool:
    """
    Function that checks if a given serial number corresponds to a connected Prophesee device.

    Args:
        serial (str): Serial number to check.

    Returns:
        is_valid (bool): True if the serial number is valid, False otherwise.
    """

    t_serial_numbers = get_available_prophesee_devices()
    t_is_valid = serial in t_serial_numbers

    return t_is_valid


def open_events_iterator(prophesee_device: Device | None, file_path: str | Path | None) -> EventsIterator | None:
    """
    Function that opens an EventsIterator for a given event file or a live stream from a Prophesee device.
    If both file_path and serial are provided, the function prioritizes opening the device.

    Args:
        prophesee_device (Device | None): Handle of the Prophesee device to open a live stream from. If None, no live stream is opened.
        file_path (str | Path | None): Path to the event file. Supported formats are .raw and .hdf5. If None, no file is opened.


    Returns:
        events_iterator (EventsIterator | None): EventsIterator object for the opened event stream, or None if neither a valid file nor a valid serial number is provided.
    """

    # Prioritize opening the device if both parameters are provided
    if prophesee_device is not None:
        return EventsIterator.from_device(prophesee_device)

    if file_path is not None and check_file_exists(file_path):
        return EventsIterator(str(file_path))

    print_error("No valid prophesee device handle or file path provided - Can't open event stream iterator")

    return None


def open_camera_from_serial(serial: str) -> Camera | None:
    """
    Function that opens a camera stream from a given serial number.
    Required format of the serial number is the one returned by get_available_prophesee_devices().
    Valid serial number example: e.g. "00050271". Function returns None if the serial number is invalid.

    Args:
        serial (str): Serial number of the Prophesee device.

    Returns:
        camera (Camera | None): Camera object representing the opened stream, or None if the serial number is invalid.
    """

    if not check_serial_number_validity(serial):
        print_error(f"Camera with serial number {serial} is not connected. Can't open camera stream")
        return None

    return Camera.from_serial(serial)


def open_device_from_serial(serial: str) -> Device | None:
    """
    Function that opens a Prophesee device from a given serial number.
    Required format of the serial number is the one returned by get_available_prophesee_devices().
    Valid serial number example: e.g. "00050271". Function returns None if the serial number is invalid.

    Args:
        serial (str): Serial number of the Prophesee device.

    Returns:
        device (Device | None): Device object representing the opened Prophesee device, or None if the serial number is invalid.
    """

    if not check_serial_number_validity(serial):
        print_error(f"Camera with serial number {serial} is not connected. Can't open camera stream")
        return None

    return DeviceDiscovery.open(serial)


def open_stream_from_file(file_path: str | Path) -> Camera | None:
    """
    Function that opens a camera stream from a given event file.
    Supported file formats are .raw or .hdf5. Function returns None if the file does not exist.

    Args:
        file_path (str | Path): Path to the event file.

    Returns:
        camera (Camera | None): Camera object representing the opened stream, or None if the file does not exist.
    """

    if not check_file_exists(file_path):
        print_error(f"Event file {Path(file_path).name} does not exist. Can't open event stream")
        return None

    return Camera.from_file(file_path)


def get_camera_dimension(camera: Camera) -> tuple[int, int]:
    """
    Function that returns the width and height of a given camera (resulution of 'virtual' sensor).
    Returns (0, 0) if no camera is connected.

    Args:
        camera (Camera): Camera object.

    Returns:
        dimensions (tuple[int, int]): Tuple containing the width and height of the camera (width, height).
    """

    if camera is None:
        print_error("Camera is not initialized. Can't get camera dimensions")
        return 0, 0

    t_width = camera.width()
    t_height = camera.height()

    return t_width, t_height


def get_on_demand_frame_generation(
    frame_width: int, frame_height: int, accumulation_time_us: int = 0
) -> OnDemandFrameGenerationAlgorithm | None:
    """
    Function that creates and returns an OnDemandFrameGenerationAlgorithm for generating frames on demand from event data.
    The algorithm generates frames by accumulating events over a specified time window (accumulation_time_us).
    If accumulation_time_us is set to 0, the algorithm generates frames based on the latest events without any accumulation.

    Args:
        frame_width (int): Width of the generated frames.
        frame_height (int): Height of the generated frames.
        accumulation_time_us (int): Time window in microseconds for accumulating events to generate a frame. Default is 0 (no accumulation).

    Returns:
        algorithm (OnDemandFrameGenerationAlgorithm | None): OnDemandFrameGenerationAlgorithm object for generating frames, or None if the provided dimensions are invalid.
    """

    if frame_width <= 0 or frame_height <= 0:
        print_error("Invalid frame dimensions provided. Can't create OnDemandFrameGenerationAlgorithm")
        return None

    return OnDemandFrameGenerationAlgorithm(frame_width, frame_height, accumulation_time_us=accumulation_time_us)


def get_camera_slicer(camera: Camera) -> CameraStreamSlicer | None:
    """
    Function that returns a CameraStreamSlicer for the given camera.

    Args:
        camera (Camera): Camera object.

    Returns:
        slicer (CameraStreamSlicer | None): CameraStreamSlicer object for the given camera.
    """

    if camera is None:
        print_error("Camera is not initialized. Can't get camera slicer")
        return None

    return CameraStreamSlicer(camera.move())


def load_camera_settings(camera: Camera, settings_file_path: str | Path) -> bool:
    """
    Function that loads camera settings from a given file path.
    Supported file formats are .json or .yaml. Returns True if the settings were loaded successfully, False otherwise.

    Args:
        camera (Camera): Camera object to load the settings into.
        settings_file_path (str | Path): Path to the settings file.

    Returns:
        success (bool): True if the settings were loaded successfully, False otherwise.
    """

    if camera is None:
        print_error("Camera is not initialized. Can't load camera settings")
        return False

    if not check_file_exists(settings_file_path):
        print_error(f"Settings file {Path(settings_file_path).name} does not exist. Can't load camera settings")
        return False

    try:
        return camera.load(str(settings_file_path))

    except Exception as e:
        print_error(f"Failed to load camera settings from {Path(settings_file_path).name}: {e}")
        return False


def get_frame_window_threaded(camera: Camera, title: str, width: int, height: int) -> MTWindow | None:
    """
    Function that creates and returns a MTWindow for displaying frames from the given camera.
    MTWindow uses a separate thread for rendering, yielding better performance.

    Args:
        camera (Camera): Camera object.
        title (str): Title of the window.
        width (int): Width of the window.
        height (int): Height of the window.

    Returns:
        window (MTWindow | None): MTWindow object for displaying frames, or None if the camera is not initialized.
    """

    if camera is None:
        print_error("Camera is not initialized. Can't create frame window")
        return None

    return MTWindow(title=title, width=width, height=height, mode=BaseWindow.RenderMode.BGR, open_directly=True)


def register_window_keyboard_callback(window: MTWindow, key_events: list[UIKeyEvent]) -> None:
    """
    Function that registers a keyboard callback for the given MTWindow.
    The callback closes the window when the registered key event occurs.

    Args:
        window (MTWindow): MTWindow object.
        key_events (list[UIKeyEvent]): List of key events that trigger the window to close.

    Returns:
        ():
    """

    # Register keyboard callback to close the window on specific key event
    def keyboard_cb(key, scancode, action, mods):
        if key in key_events:
            window.set_close_flag()

    window.set_keyboard_callback(keyboard_cb)

    return


def get_hdf5_event_file_writer() -> HDF5EventFileWriter | None:
    """
    Function that creates and returns an HDF5EventFileWriter for recording event data to a file.

    Args:
        ():

    Returns:
        writer (HDF5EventFileWriter | None): HDF5EventFileWriter object for recording event data, or None if the writer could not be created.
    """

    try:
        return HDF5EventFileWriter()

    except Exception as e:
        print_error(f"Failed to create HDF5EventFileWriter: {e}")
        return None


def add_metadata_to_recording(
    writer: HDF5EventFileWriter,
    date: str,
    firmware_version: str,
    generation: str,
    geometry: str,
    integrator_name: str,
    serial_number: str,
) -> bool:
    """
    Function that adds metadata to the event recording file using the HDF5EventFileWriter.
    Metadata includes relevant information of the arguments of this function.

    Args:
        writer (HDF5EventFileWriter): HDF5 event file writer object to add metadata to.
        date (str): Date of the recording.
        firmware_version (str): Version of the camera firmware.
        generation (str): Generation of the camera.
        geometry (str): Geometry of the camera.
        integrator_name (str): Name of the camera integrator.
        serial_number (str): Serial number of the camera.

    Returns:
        success (bool): True if the metadata was added successfully, False otherwise.
    """

    if writer is None:
        print_error("Event file writer is not initialized. Can't add metadata to recording")
        return False

    try:
        # Adding all required metadata fields to the recording file
        writer.add_metadata(key="Date", value=date)
        writer.add_metadata(key="firmware_version", value=firmware_version)
        writer.add_metadata(key="generation", value=generation)
        writer.add_metadata(key="geometry", value=geometry)
        writer.add_metadata(key="integrator_name", value=integrator_name)
        writer.add_metadata(key="serial_number", value=serial_number)
        writer.add_metadata(key="version", value="1.0")
        return True

    except Exception as e:
        print_error(f"Failed to add metadata to recording: {e}")
        return False


def start_event_recording(
    writer: HDF5EventFileWriter,
    file_path: str | Path,
    date: str,
    firmware_version: str,
    generation: str,
    geometry: str,
    integrator_name: str,
    serial_number: str,
) -> bool:
    """
    Function that starts recording event data to a file.
    Only supports .raw or .hdf5 (but generally .raw for live cameras).
    Arguments for metadata are also required to be added to the recording.

    Args:
        writer (HDF5EventFileWriter): HDF5 event file writer object.
        file_path (str | Path): Path to the output file.
        date (str): Date of the recording.
        firmware_version (str): Version of the camera firmware.
        generation (str): Generation of the camera.
        geometry (str): Geometry of the camera.
        integrator_name (str): Name of the camera integrator.
        serial_number (str): Serial number of the camera.

    Returns:
        success (bool): True if the recording was started successfully, False otherwise.
    """

    if writer is None:
        print_error("Event file writer is not initialized. Can't start event recording")
        return False

    try:

        writer.open(str(file_path))
        add_metadata_to_recording(writer, date, firmware_version, generation, geometry, integrator_name, serial_number)
        return True

    except Exception as e:
        print_error(f"Failed to start event recording to {Path(file_path).name}: {e}")
        return False


def add_events_to_recording(writer: HDF5EventFileWriter, events: np.ndarray) -> bool:
    """
    Function that adds events to the current recording.

    Args:
        writer (HDF5EventFileWriter): HDF5 event file writer object to add events to.
        events (np.ndarray): Numpy array containing the events to add.

    Returns:
        success (bool): True if the events were added successfully, False otherwise.
    """

    if writer is None or not writer.is_open():
        print_error("Event file writer is not initialized or not open. Can't add events to recording")
        return False

    try:
        writer.add_cd_events(events)
        return True

    except Exception as e:
        print_error(f"Failed to add events to recording: {e}")
        return False


def stop_event_recording(writer: HDF5EventFileWriter) -> bool:
    """
    Function that stops the current event recording.

    Args:
        writer (HDF5EventFileWriter): HDF5 event file writer object to stop the recording.

    Returns:
        success (bool): True if the recording was stopped successfully, False otherwise.
    """

    if writer is None or not writer.is_open():
        print_error("Event file writer is not initialized. Can't stop event recording")
        return False

    try:
        writer.flush()
        writer.close()
        return True

    except Exception as e:
        print_error(f"Failed to stop event recording: {e}")
        return False


def save_events_as_evreal_npy(
    events: np.ndarray,
    output_dir: str | Path,
    frame_width: int,
    frame_height: int,
    frame_rate: float = 25.0,
) -> bool:
    """
    Function that saves a Metavision structured event array in the EVREAL .npy format.

    The output directory will contain:
        events_xy.npy            — (N, 2)       uint16  array of [x, y] pixel coordinates
        events_ts.npy            — (N,)          float64 array of timestamps in seconds
        events_p.npy             — (N,)          uint8   array of polarities (0 or 1)
        images.npy               — (F, H, W, 1)  uint8   dummy black frames
        images_ts.npy            — (F, 1)        float64 synthetic frame timestamps in seconds
        image_event_indices.npy  — (F, 1)        int64   event index at each frame timestamp
        metadata.json            — {"sensor_resolution": [height, width]}

    Args:
        events (np.ndarray): Metavision structured event array with fields x (uint16),
            y (uint16), t (int64, microseconds), p (uint8).
        output_dir (str | Path): Directory to write the EVREAL files into. Created if absent.
        frame_width (int): Sensor width in pixels (written to metadata.json).
        frame_height (int): Sensor height in pixels (written to metadata.json).
        frame_rate (float): Synthetic frame rate in Hz used to generate image timestamps. Default is 25.0.

    Returns:
        success (bool): True if all files were saved successfully, False otherwise.
    """

    import json

    if events is None or events.size == 0:
        print_error("No events provided. Can't save EVREAL npy data")
        return False

    if frame_width <= 0 or frame_height <= 0:
        print_error("Invalid frame dimensions provided. Can't save EVREAL npy data")
        return False

    try:
        t_output_path = Path(output_dir)
        t_output_path.mkdir(parents=True, exist_ok=True)

        # Convert Metavision structured array fields
        t_events_xy = np.column_stack((events["x"], events["y"])).astype(np.uint16)
        t_events_ts = events["t"].astype(np.float64) * 1e-6  # µs → seconds
        t_events_p = events["p"].astype(np.uint8)

        # Generate synthetic image timestamps and corresponding event indices
        t_start, t_end = t_events_ts[0], t_events_ts[-1]
        t_frame_interval = 1.0 / frame_rate
        t_image_timestamps = np.arange(t_start, t_end, t_frame_interval)
        t_image_indices = np.searchsorted(t_events_ts, t_image_timestamps)

        # Dummy black frames required by the EVREAL format
        t_images = np.zeros((len(t_image_timestamps), frame_height, frame_width, 1), dtype=np.uint8)

        # Save all npy files
        np.save(t_output_path / "events_xy.npy", t_events_xy)
        np.save(t_output_path / "events_ts.npy", t_events_ts)
        np.save(t_output_path / "events_p.npy", t_events_p)
        np.save(t_output_path / "images.npy", t_images)
        np.save(t_output_path / "images_ts.npy", t_image_timestamps.reshape(-1, 1))
        np.save(t_output_path / "image_event_indices.npy", t_image_indices.reshape(-1, 1))

        # Save metadata
        t_metadata = {"sensor_resolution": [frame_height, frame_width]}
        with open(t_output_path / "metadata.json", "w", encoding="utf-8") as f:
            json.dump(t_metadata, f)

        return True

    except Exception as e:
        print_error(f"Failed to save EVREAL npy data to {Path(output_dir).name}: {e}")
        return False
