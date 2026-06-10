#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Filename: multiprocessing.py
Author: Nico Hessenthaler
Date: 2026-06-05
Version: 1.0
Description:
    Module that provides utilities for interacting with multiprocessing in the event vision pipeline.
License: Apache License Version 2.0
Contact: nico.hessenthaler@hs-heilbronn.de
"""

from multiprocessing.synchronize import Lock as LockType
from multiprocessing import shared_memory, Lock
import numpy as np
from .operating_system import print_error
from typing import Optional


class B64SharedMemory:
    """
    Class implementing a very small single-slot shared-memory buffer for UTF-8 base64 JPEG frames.

    This class exposes a tiny queue-like API used elsewhere in the codebase:
    - `put` / `put_nowait(frame_b64)` to write the latest frame (overwrites).
    - `get_nowait()` to read and consume the latest frame (returns None if empty).
    - `empty()` to check whether there's a frame available.

    Implementation details:
    - First 4 bytes of the shared memory store the uint32 length (little-endian).
    - Remaining bytes store the payload (UTF-8 encoded base64 string).
    - A `multiprocessing.Lock` synchronizes access.
    """

    def __init__(self, size: int = 2_000_000):

        # The size should be large enough to hold the largest expected base64-encoded JPEG frame, plus 4 bytes for the length.
        self.__size = size
        self.__shm = shared_memory.SharedMemory(create=True, size=self.__size)

        # Initialize length to 0
        self.__shm.buf[:4] = (0).to_bytes(4, "little")
        self.__owns_shm = True

        self.__lock = Lock()

    # ##### GETTER #####
    @property
    def size(self) -> int:
        """
        Getter for the attribute '__size'.

        Args:
            ():

        Returns:
            size (int): The attribute '__size'.
        """
        return self.__size

    @property
    def shm(self) -> shared_memory.SharedMemory:
        """
        Getter for the attribute '__shm'.

        Args:
            ():

        Returns:
            shm (shared_memory.SharedMemory): The attribute '__shm'.
        """

        return self.__shm

    @property
    def owns_shm(self) -> bool:
        """
        Getter for the attribute '__owns_shm'.

        Args:
            ():

        Returns:
            owns_shm (bool): The attribute '__owns_shm'.
        """

        return self.__owns_shm

    @property
    def lock(self) -> LockType:
        """
        Getter for the attribute '__lock'.

        Args:
            ():

        Returns:
            lock (LockType): The attribute '__lock'.
        """

        return self.__lock

    # ##### PRIVATE METHODS #####

    # ##### PUBLIC METHODS #####
    def put_nowait(self, t_img_base64: str) -> None:
        """
        Method to write a base64-encoded JPEG frame into the shared buffer. If the frame is too large, a ValueError is raised.
        This method overwrites any existing frame in the buffer.

        Args:
            t_img_base64 (str): The base64-encoded JPEG frame to be written into the shared buffer.

        Returns:
            ():
        """

        t_bytes = t_img_base64.encode("utf-8")
        t_length = len(t_bytes)
        if t_length + 4 > self.size:
            print_error(f"Frame too large for shared buffer (size {t_length} bytes, max {self.size - 4} bytes)")
            raise ValueError()
        with self.lock:
            self.shm.buf[:4] = t_length.to_bytes(4, "little")
            self.shm.buf[4 : 4 + t_length] = t_bytes

    # Compatibility alias
    put = put_nowait

    def get_nowait(self) -> Optional[str]:
        """
        Method to read and consume the latest frame from the shared buffer. If the buffer is empty, None is returned.

        Args:
            ():

        Returns:
            bytes (Optional[str]): The latest base64-encoded JPEG frame from the shared buffer, or None if the buffer is empty.
        """

        with self.lock:
            t_length = int.from_bytes(self.shm.buf[:4], "little")
            if t_length == 0:
                return None
            t_bytes = bytes(self.shm.buf[4 : 4 + t_length])
            self.shm.buf[:4] = (0).to_bytes(4, "little")

            return t_bytes.decode("utf-8")

    def empty(self) -> bool:
        """
        Method to check whether the shared buffer is empty (i.e., contains no frame).

        Args:
            ():

        Returns:
            is_empty (bool): True if the buffer is empty, False otherwise.
        """

        with self.lock:
            t_length = int.from_bytes(self.shm.buf[:4], "little")
            return t_length == 0

    def close(self) -> None:
        """
        Method to properly close the shared memory segment. If this instance created the shared memory, it also unlinks it to free resources.

        Args:
            ():

        Returns:
            ():
        """

        try:
            self.shm.close()
        except Exception:
            pass
        if self.owns_shm:
            try:
                self.shm.unlink()
            except Exception:
                pass

        return


class RawSharedMemory:
    """
    Class implementing a single-slot shared-memory buffer for raw NumPy (BGR8/MONO8) images.

    Implementation:
    - First 4 bytes: img width (uint32)
    - Next 4 bytes: img height (uint32)
    - Next 4 bytes: img channels (uint32)
    - Next 4 bytes: data length (uint32)
    - Remaining bytes: raw NumPy array data
    """

    def __init__(self, size: int = 10_000_000):

        # The size should be large enough to hold the largest expected raw image frame, plus 16 bytes for the header.
        self.__size = size
        self.__shm = shared_memory.SharedMemory(create=True, size=self.__size)

        # Initialize lengths to 0
        self.__shm.buf[:16] = (0).to_bytes(16, "little")
        self.__owns_shm = True
        self.__lock = Lock()

    # ##### GETTER #####
    @property
    def size(self) -> int:
        """
        Getter for the attribute '__size'.

        Args:
            ():

        Returns:
            size (int): The attribute '__size'.
        """

        return self.__size

    @property
    def shm(self) -> shared_memory.SharedMemory:
        """
        Getter for the attribute '__shm'.

        Args:
            ():

        Returns:
            shm (shared_memory.SharedMemory): The attribute '__shm'.
        """

        return self.__shm

    @property
    def owns_shm(self) -> bool:
        """
        Getter for the attribute '__owns_shm'.

        Args:
            ():

        Returns:
            owns_shm (bool): The attribute '__owns_shm'.
        """

        return self.__owns_shm

    @property
    def lock(self) -> LockType:
        """
        Getter for the attribute '__lock'.

        Args:
            ():

        Returns:
            lock (LockType): The attribute '__lock'.
        """

        return self.__lock

    # ##### PRIVATE METHODS #####

    # ##### PUBLIC METHODS #####
    def put(self, frame: np.ndarray) -> None:
        """
        Method to put a raw numpy array into shared memory. Overwrites existing data.

        Args:
            frame (np.ndarray): The raw image frame to be written into shared memory.

        Returns:
            ():
        """

        if frame is None:
            return

        t_height, t_width = frame.shape[:2]
        t_channels = frame.shape[2] if len(frame.shape) == 3 else 1
        t_data = frame.tobytes()
        t_length = len(t_data)

        if t_length + 16 > self.size:
            print_error(f"Image too large for shared buffer ({t_length + 16} > {self.size})")
            return

        with self.lock:
            self.shm.buf[0:4] = t_width.to_bytes(4, "little")
            self.shm.buf[4:8] = t_height.to_bytes(4, "little")
            self.shm.buf[8:12] = t_channels.to_bytes(4, "little")
            self.shm.buf[12:16] = t_length.to_bytes(4, "little")
            self.shm.buf[16 : 16 + t_length] = t_data

        return

    def get(self) -> Optional[np.ndarray]:
        """
        Method to get the latest image from shared memory and CLEARS it (sets data length to 0).

        Args:
            ():

        Returns:
            frame (Optional[np.ndarray]): The latest image frame from shared memory, or None if the buffer is empty.
        """

        with self.lock:
            t_width = int.from_bytes(self.shm.buf[0:4], "little")
            t_height = int.from_bytes(self.shm.buf[4:8], "little")
            t_channels = int.from_bytes(self.shm.buf[8:12], "little")
            t_length = int.from_bytes(self.shm.buf[12:16], "little")

            if t_length == 0:
                return None

            t_data = bytes(self.shm.buf[16 : 16 + t_length])

            # Clear it
            self.shm.buf[12:16] = (0).to_bytes(4, "little")
            t_shape = (t_height, t_width, t_channels) if t_channels > 1 else (t_height, t_width)

            return np.frombuffer(t_data, dtype=np.uint8).reshape(t_shape)

    def empty(self) -> bool:
        """
        Method to check whether the shared memory buffer is empty (i.e., contains no image).

        Args:
            ():

        Returns:
            is_empty (bool): True if the buffer is empty, False otherwise.
        """

        with self.lock:
            return int.from_bytes(self.shm.buf[12:16], "little") == 0

        return

    def close(self) -> None:
        """
        Method to close the shared memory segment.
        If this instance created the shared memory, it also unlinks it to free resources.

        Args:
            ():

        Returns:
            ():
        """

        try:
            self.shm.close()
        except:
            pass
        if self.owns_shm:
            try:
                self.shm.unlink()
            except:
                pass

        return
