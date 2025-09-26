from thorlabs_tsi_sdk.tl_camera import TLCameraSDK, OPERATION_MODE
from thorlabs_tsi_sdk.tl_camera import TLCameraSDK, TLCamera, Frame
from thorlabs_tsi_sdk.tl_camera_enums import SENSOR_TYPE
from thorlabs_tsi_sdk.tl_mono_to_color_processor import MonoToColorProcessorSDK

try:
    # if on Windows, use the provided setup script to add the DLLs folder to the PATH
    from path_setup import configure_path
    configure_path()
except ImportError:
    configure_path = None

from PIL import Image
import threading
import queue
from PyQt6.QtCore import pyqtSignal, QObject

from src.com import ConfigurationManager
from main import ImageUpdateSignal

class ImageUpdateSignal(QObject):
    new_image = pyqtSignal(bool)

class CameraNotFoundError(Exception):
    def __init__(self, message="Camera not found"):
        super().__init__(message)

class ImageAcquisitionThread(threading.Thread):
    """ ImageAcquisitionThread

    This class derives from threading.Thread and is given a TLCamera instance during initialization. When started, the 
    thread continuously acquires frames from the camera and converts them to PIL Image objects. These are placed in a 
    queue.Queue object that can be retrieved using get_output_queue(). The thread doesn't do any arming or triggering, 
    so users will still need to setup and control the camera from a different thread. Be sure to call stop() when it is 
    time for the thread to stop.

    This class is a modified version of Thorlabs own ImageAcquisitionThread which can be found in 
    Scientific_Camera_Interfaces/SDK/Python_Toolkit/examples/tkinter_camera_live_view.py. This folder can be downloaded 
    from Thorlabs software page under the Programming Interfaces tab or by following the link:
    https://www.thorlabs.com/software_pages/ViewSoftwarePage.cfm?Code=ThorCam 

    """
    def __init__(self, camera, shared_queue: queue.Queue|None, signal):
        # type: (TLCamera, queue.Queue|None, ImageUpdateSignal|None) -> ImageAcquisitionThread
        super(ImageAcquisitionThread, self).__init__()
        self._camera = camera
        self._previous_timestamp = 0
        self._signal = signal

        if shared_queue != None:
            self._image_queue = shared_queue
        else:
            self._image_queue = queue.Queue(maxsize=2)

        # setup color processing if necessary
        if self._camera.camera_sensor_type != SENSOR_TYPE.BAYER:
            # Sensor type is not compatible with the color processing library
            self._is_color = False
        else:
            self._mono_to_color_sdk = MonoToColorProcessorSDK()
            self._image_width = self._camera.image_width_pixels
            self._image_height = self._camera.image_height_pixels
            self._mono_to_color_processor = self._mono_to_color_sdk.create_mono_to_color_processor(
                SENSOR_TYPE.BAYER,
                self._camera.color_filter_array_phase,
                self._camera.get_color_correction_matrix(),
                self._camera.get_default_white_balance_matrix(),
                self._camera.bit_depth
            )
            self._is_color = True

        self._bit_depth = camera.bit_depth
        self._camera.image_poll_timeout_ms = 0  # Do not want to block for long periods of time
        self._stop_event = threading.Event()

    def get_output_queue(self):
        # type: ignore # type: (type(None)) -> queue.Queue
        return self._image_queue

    def stop(self):
        self._stop_event.set()

    def _get_color_image(self, frame):
        # type: (Frame) -> Image
        # verify the image size
        width = frame.image_buffer.shape[1]
        height = frame.image_buffer.shape[0]
        if (width != self._image_width) or (height != self._image_height):
            self._image_width = width
            self._image_height = height
            print("Image dimension change detected, image acquisition thread was updated")
        # color the image. transform_to_24 will scale to 8 bits per channel
        color_image_data = self._mono_to_color_processor.transform_to_24(frame.image_buffer,
                                                                         self._image_width,
                                                                         self._image_height)
        color_image_data = color_image_data.reshape(self._image_height, self._image_width, 3)
        # return PIL Image object
        return Image.fromarray(color_image_data, mode='RGB')

    def _get_image(self, frame):
        # type: (Frame) -> Image
        scaled_image = frame.image_buffer
        return Image.fromarray(scaled_image)

    def run(self):
        nr = 0 # number of images in queue
        # If signal not given, just keep acquireing 
        emit_signal = True if self._signal != None else False
        while not self._stop_event.is_set():
            try:
                frame = self._camera.get_pending_frame_or_null()
                if frame is not None:
                    nr += 1
                    if self._is_color:
                        pil_image = self._get_color_image(frame)
                    else:
                        pil_image = self._get_image(frame)
                    self._image_queue.put_nowait(pil_image)
                    # only update live view when pair of images acquired
                    if nr == 2: 
                        if emit_signal:
                            self._signal.new_image.emit(True)
                        nr = 0
            except queue.Full:
                # No point in keeping this image around when the queue is full, let's skip to the next one
                nr = 0
                pass
            except Exception as error:
                print("Encountered error: {error}, image acquisition will stop.".format(error=error))
                break
            
        print("Image acquisition has stopped")
        if self._is_color:
            self._mono_to_color_processor.dispose()
            self._mono_to_color_sdk.dispose()

class Camera():
    """Camera
    
    This creates a TLCamera instance that do the main communication with the Thorlabs camera. This instance is
    handled and activated through the ThorlabsCameraHandler class 

    Parameters
    `config_manager` : ConfigurationManager object
        This is a seperate class that is not currently published. However, it is more or less an dict
        containing the camera settings. Can manually be adjusted below.
    Returns
    `Object` : TLCamera
        TLCamera object that is used for accessing the camera 
    """
    def __init__(self, config_manager):
        # type: (ConfigurationManager) -> TLCamera
        self.config_manager = config_manager
        self.connected = False
        self.initialize_camera()
    
    def initialize_camera(self):
        """Initialize the camera with current settings."""
        try:
            self.sdk = TLCameraSDK() 
            available_cameras = self.sdk.discover_available_cameras()
            if len(available_cameras) < 1:
                raise CameraNotFoundError("Unable to access the camera.")
            # Open the first avalible camera found
            camera = self.sdk.open_camera(available_cameras[0])
            settings = self.config_manager.get('settings')
            # Exposure time
            camera.exposure_time_us = settings.get("exposureTime_us")
            # Amount of frames aquired per trigger, zero for unlimitated
            camera.frames_per_trigger_zero_for_unlimited = 1 
            # Set operation mode to HARDWARE_TRIGGERED
            camera.operation_mode = 1
            # Trigger on LOW, (0 trigger on HIGH)
            camera.trigger_polarity = 1
            # Arm camera buffer with 2 images
            camera.arm(2)
            
            self.camera = camera
            self.connected = True
        
        except CameraNotFoundError as e:
            self.camera = None
            # Print the error message
            print(f"Error caught: {e}")
        
        except Exception as error:
            print("Encountered error: {error}, image acquisition will stop.".format(error=error))

    @property
    def is_connected(self):
        """Return True if camera is connected to computer"""
        return self.connected

    def dispose(self):
        """Dispose both TLCamera and TLCameraSDK instance"""
        # Dispose the TLCamera instance
        self.camera.disarm()
        self.camera.dispose()
        # Dispose the TLCameraSDK instance
        self.sdk.dispose()
            

class ThorlabsCameraHandler():
    """ThorlabsCameraHandler
    
    Handler class for the Thorlabs TLCamera instance

    Parameters
    `config_manager` : ConfigurationManager object
        This is a seperate class that is not currently published. However, it is more or less an dict
        containing the camera settings. Can manually be adjusted in Camera class.
    `shared_queue` : queue.Queue|None
        Image queue that is shared between ImageAcquisitionThread and whatever part collecting the images
    `signal` : ImageUpdateSignal|None
        Signals another part of software that 2 images has been aquired (can me modified in ImageAcquisitionThread).
  
    """
    def __init__(self, config_manager, shared_queue: queue.Queue|None, signal):
        # type: (ConfigurationManager, queue.Queue|None, ImageUpdateSignal|None) -> ThorlabsCameraHandler
        self.config = config_manager
        self.signal = signal
        self.shared_queue = shared_queue
        self.connected = False
        self.is_alive = False
        self.initialize_camera()

    def initialize_camera(self):
        """Initialize the camera through the Camera class. If successful, also set up the 
        ImageAcquisitionThread class for image aqusition"""
        try:
            self._camera = Camera(self.config)
            self.connected = self._camera.is_connected
            if self.connected:
                self.image_acquisition_thread = ImageAcquisitionThread(self._camera.camera, self.shared_queue, self.signal)
        except Exception as e:
            print(f'Encountered error: {e}')
            self._camera = None

    @property
    def camera_state(self):
        """Return True is camera is active and can be trigger"""
        return self.is_alive
    
    def activate_camera_instance(self):
        """Starting a ImageAcquisitionThread which collect images from the Thorlab camera."""
        print("Starting image acquisition thread...\n")
        self.is_alive = True
        self.image_acquisition_thread.start()
        print(f'Image thred alive: {self.image_acquisition_thread.is_alive()}')

    def reinitialize(self):
        """Reinitialize the camera to apply updated settings."""
        if self.connected:
            # Dispose camera instance
            self.dispose_camera_instance()
            # Empty image queue
            with self.shared_queue.mutex:
                self.shared_queue.queue.clear()
            # Initialize camera instance 
            self.initialize_camera()
            # Activate camera aqusition
            self.activate_camera_instance()
            
    def dispose_camera_instance(self):
        """If ImageAcquisitionThread is alive, it stop the thread and dispose the camera instance."""
        if self.is_alive:
            # Stop image acquisition thread 
            self.image_acquisition_thread.stop()
            self.image_acquisition_thread.join()
            print(f'Image thred alive: {self.image_acquisition_thread.is_alive()}')
            self.is_alive = False
        # Dispose camera instance
        self._camera.dispose()
        