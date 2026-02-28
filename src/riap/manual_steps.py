"""
Manual parameter adjustment module for histology-polarimetry image alignment.

This module provides an interactive GUI for users to manually adjust alignment parameters
including rotation, flipping, shrinkage, and offset adjustments.
"""
import pickle
import shutil
from typing import List, Tuple, Optional, Union
from PIL import Image
from loguru import logger
import cv2
import numpy as np

from riap.io_utils import write_mp_fp_txt_format

def semi_automatic_processing(folder, image0, image1, force_recompute: bool = False) -> None:
    """
    semi_automatic_processing is called to ask the pairs of landmarks points to the user using matlab
    
    Parameters
    ----------
    alignment_measurements : list
        the list of FolderAlignHistology containing the information and the images about the measurements
    """
    coordinates_path_histo_folder = folder / 'annotation' / 'coordinates_manual.txt'
    if coordinates_path_histo_folder.exists() and not force_recompute:
        logger.info(f"Coordinates file already exists at {coordinates_path_histo_folder}. Skipping manual point selection.")
        pts = pickle.load(coordinates_path_histo_folder.open("rb"))
        return pts
        
    selector = PointSelector(image0, image1)
    pts = selector.run()

    with open(coordinates_path_histo_folder, "wb") as f:
        pickle.dump(pts, f)

    return pts

class PointSelector:
    """
    Allows the user to interactively select corresponding point pairs between two images:
    a fixed image and a moving image.

    Parameters:
    -----------
    path_fixed_img : str or PIL.Image
        Path to the fixed image or a PIL Image object (typically the histology image).
    path_moving_img : str or PIL.Image
        Path to the moving image or a PIL Image object (typically the polarimetry image).
    bounds : tuple or None
        Tuple of (x_min, x_max, y_min, y_max) to crop the moving image. If None, full image is used.
    histology : bool
        Whether the fixed image is a histology image (downsampled by factor 3, rotated).

    Usage:
    ------
    selector = PointSelector(path_fixed_img, path_moving_img, bounds=bounds, histology=True)
    fixed_pts, moving_pts = selector.run()
    """

    def __init__(
            self,
            path_fixed_img: Union[str, np.ndarray],
            path_moving_img: Union[str, np.ndarray],
            bounds: Optional[Tuple[int, int, int, int]] = None,
            histology: bool = False,
            path_selection: Optional[str] = None
    ) -> None:
        """
        Initializes the PointSelector with images and configuration.

        Loads and optionally processes images for display and interaction.
        """
        # Initialize attributes
        self.fixed_pts = []
        self.moving_pts = []
        self.colors = []

        self.pending_fixed = None
        self.pending_moving = None
        self.current_color = None

        self.histology = histology

        if bounds is None:
            self.x_min = 0
            self.y_min = 0



            self.x_max = path_fixed_img.shape[0]
            self.y_max = path_fixed_img.shape[1]

        else:
            self.x_min, self.x_max, self.y_min, self.y_max = bounds

        self.fixed_img = self._load_fixed_image(path_fixed_img)
        self.moving_img = self._load_moving_image(path_moving_img)
        self.fixed_img_copy = None
        self.moving_img_copy = None

        self.path_selection = path_selection

    def _load_fixed_image(
            self,
            img_input
    ) -> np.ndarray:
        """
        Loads and preprocesses the fixed image.

        Parameters
        ----------
        img_input : str or PIL.Image
            Path or image object.

        Returns
        -------
        np.ndarray
            Processed image as NumPy array.
        """
        self.zoom_level = 1.0

        if isinstance(img_input, str):
            self.full_res_fixed_img = cv2.imread(str(img_input))
            height, width = self.full_res_fixed_img.shape[:2]
            full_res_img = cv2.resize(self.full_res_fixed_img, (2 * width, 2 * height), interpolation=cv2.INTER_CUBIC)
            self.full_res_fixed_img = Image.fromarray(full_res_img)

            return full_res_img

        else:

            self.full_res_fixed_img = Image.fromarray(img_input).convert("RGB")
            return img_input

    def _rescale_fixed_image(
            self
    ) -> np.ndarray:
        """
        Returns the current fixed image based on zoom level.

        Returns
        -------
        PIL.Image
            Rescaled fixed image.
        """
        width, height = self.full_res_fixed_img.size
        new_size = (int(width * self.zoom_level), int(height * self.zoom_level))
        return self.full_res_fixed_img.resize(new_size)

    def _load_moving_image(
            self,
            img_input
    ) -> np.ndarray:
        """
        Loads and crops the moving image.

        Parameters
        ----------
        img_input : str or PIL.Image
            Path or image object.

        Returns
        -------
        np.ndarray
            Cropped image as NumPy array.
        """

        if isinstance(img_input, str):
            return cv2.imread(img_input)[self.x_min:self.x_max, self.y_min:self.y_max]
        else:
            return np.array(Image.fromarray(img_input).convert("RGB"))[self.x_min:self.x_max, self.y_min:self.y_max]

    def _get_unique_color(
            self,
            index: int
    ) -> Tuple[int, int, int]:
        """
        Generates a visually distinct color for indexing point pairs.

        Parameters
        ----------
        index : int
            Index of the point pair.

        Returns
        -------
        tuple
            BGR color tuple.
        """
        # Use golden angle to generate more perceptually distinct hues
        golden_angle = 137.508  # degrees
        hue_deg = (index * golden_angle) % 360
        hue_opencv = int(hue_deg / 2)  # OpenCV hue range: 0–179
        hsv_color = np.array([[[hue_opencv, 255, 255]]], dtype=np.uint8)
        bgr_color = cv2.cvtColor(hsv_color, cv2.COLOR_HSV2BGR)[0][0]
        return tuple(int(c) for c in bgr_color)

    def _redraw_images(
            self
    ) -> None:
        """
        Redraws the fixed and moving images with point overlays,
        adapting to the current zoom level for the fixed image.

        Returns
        -------
        None
        """
        # Rescale fixed image based on current zoom level
        rescaled_pil = self._rescale_fixed_image()
        self.fixed_img = np.array(rescaled_pil)

        # Compute current scale factor
        width_full, height_full = self.full_res_fixed_img.size
        width_scaled, height_scaled = rescaled_pil.size
        scale_x = width_scaled / width_full
        scale_y = height_scaled / height_full

        fi = self.fixed_img.copy()
        mi = self.moving_img.copy()

        for fp, mp, col in zip(self.fixed_pts, self.moving_pts, self.colors):
            # Adjust fixed image points for zoom
            fx = int(fp[0] * scale_x)
            fy = int(fp[1] * scale_y)

            # Adjust moving image points (cropping only)
            mx = mp[0] - self.y_min
            my = mp[1] - self.x_min

            cv2.circle(fi, (fx, fy), 8, col, -1)
            cv2.circle(mi, (mx, my), 8, col, -1)

        if self.pending_fixed is not None:
            fx = int(self.pending_fixed[0] * scale_x)
            fy = int(self.pending_fixed[1] * scale_y)
            cv2.circle(fi, (fx, fy), 4, (0, 255, 255), 1)

        if self.pending_moving is not None:
            mx = self.pending_moving[0] - self.y_min
            my = self.pending_moving[1] - self.x_min
            cv2.circle(mi, (mx, my), 4, (0, 255, 255), 1)

        cv2.namedWindow("Fixed Image", cv2.WINDOW_GUI_EXPANDED)
        cv2.namedWindow("Moving Image", cv2.WINDOW_GUI_EXPANDED)
        cv2.resizeWindow("Fixed Image", min(1200, self.fixed_img.shape[1]), min(1200, self.fixed_img.shape[0]))
        cv2.resizeWindow("Moving Image", min(1200, self.moving_img.shape[1]), min(1200, self.moving_img.shape[0]))
        cv2.imshow("Fixed Image", fi)
        cv2.imshow("Moving Image", mi)

        self.fixed_img_copy = fi
        self.moving_img_copy = mi

    def _try_complete_pair(
            self
    ) -> None:
        """
        If both pending points are selected, adds them as a pair.

        Returns
        -------
        None
        """
        if self.pending_fixed is not None and self.pending_moving is not None:
            self.fixed_pts.append(self.pending_fixed)
            self.moving_pts.append(self.pending_moving)
            self.colors.append(self.current_color or self.get_unique_color(len(self.fixed_pts)))
            self.pending_fixed = None
            self.pending_moving = None
            self.current_color = None

    def click_event_fixed(
            self,
            event: int,
            x: int,
            y: int,
            flags: int,
            param: object
    ) -> None:
        """
        Mouse callback for fixed image.

        Left click defines a point, right click undoes the last pair.

        Parameters
        ----------
        event : int
        x : int
        y : int
        flags : int
        param : any

        Returns
        -------
        None
        """
        if event == cv2.EVENT_LBUTTONDOWN:
            scaled_x = int(x / self.zoom_level)
            scaled_y = int(y / self.zoom_level)
            point = (scaled_x, scaled_y) if self.histology else (x, y)
            self.pending_fixed = point
            if self.current_color is None:
                self.current_color = self._get_unique_color(len(self.fixed_pts))
            self._try_complete_pair()
        elif event == cv2.EVENT_RBUTTONDOWN:
            if self.fixed_pts and self.moving_pts:
                self.fixed_pts.pop()
                self.moving_pts.pop()
                self.colors.pop()
            self.pending_fixed = None
            self.pending_moving = None
            self.current_color = None
        self._redraw_images()

    def click_event_moving(
            self,
            event: int,
            x: int,
            y: int,
            flags: int,
            param: object
    ) -> None:
        """
        Mouse callback for moving image.

        Left click defines a point, right click undoes the last pair.

        Parameters
        ----------
        event : int
        x : int
        y : int
        flags : int
        param : any

        Returns
        -------
        None
        """
        if event == cv2.EVENT_LBUTTONDOWN:
            point = (x + self.y_min, y + self.x_min)
            self.pending_moving = point
            if self.current_color is None:
                self.current_color = self._get_unique_color(len(self.fixed_pts))
            self._try_complete_pair()
        elif event == cv2.EVENT_RBUTTONDOWN:
            if self.fixed_pts and self.moving_pts:
                self.fixed_pts.pop()
                self.moving_pts.pop()
                self.colors.pop()
            self.pending_fixed = None
            self.pending_moving = None
            self.current_color = None
        self._redraw_images()

    def run(
            self
    ) -> Tuple[List[Tuple[int, int]], List[Tuple[int, int]]]:
        """
        Launches the interactive point selection GUI.

        Returns
        -------
        fixed_pts : list of tuple
            List of (x, y) coordinates in the fixed image.
        moving_pts : list of tuple
            List of (x, y) coordinates in the moving image.
        """
        self._redraw_images()
        cv2.setMouseCallback("Fixed Image", self.click_event_fixed)
        cv2.setMouseCallback("Moving Image", self.click_event_moving)
        print("Left-click anywhere to define a pair (any order). Right-click to undo last. Press any key to finish.")

        while True:
            key = cv2.waitKey(0)
            if key == ord('+') or key == ord('='):
                self.zoom_level *= 1.2
                self.fixed_img = np.array(self._rescale_fixed_image())
                self._redraw_images()
            elif key == ord('-') or key == ord('_'):
                self.zoom_level /= 1.2
                self.fixed_img = np.array(self._rescale_fixed_image())
                self._redraw_images()
            else:
                break

        cv2.destroyAllWindows()

        return self.moving_pts, self.fixed_pts
