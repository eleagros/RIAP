import numpy as np
import cv2
import imageio

def write_mp_fp_txt_format(
    mp_fp, 
    feature_matching_method: str = None
) -> str:
    """
    Formats matched feature points to tab-separated string format for saving.
    """
    # Define the header for the output file
    header = 'Index\txSource\tySource\txTarget\tyTarget\n'
    gen = enumerate(zip(mp_fp[1], mp_fp[0])) # automatic

    # Prepare the lines to be written to the file
    lines = [
        f"{index}\t{round(fp[0])}\t{round(fp[1])}\t{round(mp[0])}\t{round(mp[1])}\n"
        for index, (fp, mp) in gen
    ]
    
    return header + ''.join(lines)

def create_alignment_gif(
        image1: np.ndarray,
        image2: np.ndarray,
        save_path: str,
        n_frames: int = 20,
        duration: float = 0.1,
        resize_factor: float = 1
    ):
    """
    Creates a looping GIF showing alignment by blending image1 to image2 and back.

    Parameters:
    - image1: np.array, first image (e.g. reference)
    - image2: np.array, second image (e.g. registered)
    - save_path: str, path to save GIF
    - n_frames: int, number of frames in one direction (total frames = 2*n_frames - 2)
    - duration: float, seconds per frame in GIF
    """
    # Convert to RGB for GIF
    def to_rgb(img):
        if img.ndim == 2:
            return cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
        else:
            return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    img1_rgb = to_rgb(image1)
    img2_rgb = to_rgb(image2)

    # Resize img2 to match img1 if needed
    if img1_rgb.shape != img2_rgb.shape:
        img2_rgb = cv2.resize(img2_rgb, (img1_rgb.shape[1], img1_rgb.shape[0]))

    # Resize both images to half their original size
    if resize_factor != 1:
        new_size = (int(img1_rgb.shape[1] * resize_factor), int(img1_rgb.shape[0] * resize_factor))
        img1_rgb = cv2.resize(img1_rgb, new_size)
        img2_rgb = cv2.resize(img2_rgb, new_size)
    
    # Blend forward frames (image1 -> image2)
    forward_frames = [cv2.addWeighted(img1_rgb, 1 - alpha, img2_rgb, alpha, 0) for alpha in np.linspace(0, 1, n_frames)]

    # Blend backward frames (image2 -> image1), exclude first and last frames to avoid duplicate frames at the ends
    backward_frames = forward_frames[-2:0:-1]

    frames = forward_frames + backward_frames

    frames_rgb = [cv2.cvtColor(frame, cv2.COLOR_BGR2RGB) for frame in frames]
    imageio.mimsave(save_path, frames_rgb, duration=duration, loop=0)
