from pathlib import Path
import cv2
import numpy as np
from PIL import Image
from loguru import logger

class OpenCValigner:
    """
    A class for performing image alignment using ImageJ and the bUnwarpJ plugin.

    This class is designed to align images based on several different use cases. It generates a macro for ImageJ
    based on the provided configuration and runs ImageJ in headless mode to align images.

    It supports different types of alignment, including:
    - Histology to Histology alignment
    - Histology to brightfield alignment
    - Polarimetry alignment

    Parameters
    ----------
    config : AlignmentConfig
        A dataclass containing the configuration parameters for the alignment process, including paths,
        image types, and processing options.
        
    Usage
    -----
    aligner = ImageJAligner(config)
    aligner.run()
    """

    def __init__(
        self, 
        output_folder: Path,
        input_folder: Path,
        to_propagate: Path,
        fun,
        initial_shape
    ) -> None:
        """
        Initializes the ImageJAligner with the given configuration.

        Parameters
        ----------
        config : AlignmentConfig
            A dataclass containing the configuration parameters for the alignment process.
        """
        self.output_folder = output_folder
        self.input_folder = input_folder
        self.to_propagate = to_propagate
        self.reg_fun = fun
        self.initial_shape = initial_shape

    def run(
        self
    ) -> None:
        """
        Prepares the input files needed for the alignment process.

        It copies the coordinates file into the temporary directory and saves the images for alignment.

        Returns
        -------
        None
        """
        to_propagate_images = {}
        for img_path in self.to_propagate.glob("*.png"):
            to_propagate_images[img_path.name] = cv2.imread(str(img_path), cv2.IMREAD_UNCHANGED)

        warped_images = warp_images_with_fun(
            to_propagate_images,
            self.reg_fun,
            self.initial_shape
        )

        for name, img in warped_images.items():
            Image.fromarray(img).save(self.to_propagate.parent / name.replace(".png", "_warped.png"))


def warp_images_with_fun(images_to_warp, fun, final_shape):
    """
    Warps a list of images to align with a reference image using a provided function.
    If an image is grayscale (H, W) or (H, W, 1), it is converted to 3 channels
    by repeating the single channel.
    """
    warped_images = {}

    for key, img in images_to_warp.items():

        if img is None or np.prod(img.shape) == 0:
            logger.warning("ERROR: Encountered an empty/None image, skipping.")
            continue

        # --- Ensure 3 channels ---
        if img.ndim == 2:
            # (H, W) → (H, W, 3)
            img = np.stack([img] * 3, axis=-1)

        elif img.ndim == 3 and img.shape[2] == 1:
            # (H, W, 1) → (H, W, 3)
            img = np.repeat(img, 3, axis=2)

        # Optional: guard against unexpected shapes
        elif img.ndim != 3 or img.shape[2] not in [3, 4]:
            logger.warning(f"Unexpected image shape {img.shape}, skipping.")
            continue

        # Warp
        _, warped_img = fun(input_image1=img)
        if final_shape is not None:
            warped_img = cv2.resize(warped_img, (final_shape[1], final_shape[0]), interpolation=cv2.INTER_NEAREST)

        warped_images[key] = warped_img

    return warped_images

def warp_images_with_H(reference_image, images_to_warp, H):
    """
    Warps a list of images to align with a reference image using homography H.
    Handles various image formats (4-channel, 3-channel, and 1-channel np.int32).
    """
    
    # Get the target size (width, height) from the reference image
    h, w = reference_image.shape[:2]
    warped_images = {}

    for key, img in images_to_warp.items():
        
        if img is None or np.prod(img.shape) == 0:
            logger.warning("ERROR: Encountered an empty/None image, skipping.")
            continue
            
        # 1. Handle 4-channel (RGBA) images by converting to 3-channel BGR
        if img.ndim == 3 and img.shape[2] == 4:
            img = img[:, :, :3]
            
        img_dtype = img.dtype
        img_ndim = img.ndim
        
        # 2. Handle 2D (Single-Channel) np.int32 image
        if img_ndim == 2 and img_dtype == np.int32:
            warped_img = cv2.warpPerspective(
                img, H, (w, h), 
                flags=cv2.INTER_NEAREST  # Critical change for 2D np.int32
            )
        
        # 3. Handle all other supported images (e.g., 3-channel uint8, or 1-channel uint8/float32)
        elif img_ndim >= 2:
            # Use default interpolation (typically INTER_LINEAR)
            warped_img = cv2.warpPerspective(img, H, (w, h), flags=cv2.INTER_NEAREST)
        
        else:
            # Catch any other unexpected scenario
            logger.warning(f"ERROR: Unhandled image format encountered. Shape: {img.shape}, Dtype: {img_dtype}. Skipping warp.")
            continue
            
        warped_images[key] = warped_img
        
    return warped_images