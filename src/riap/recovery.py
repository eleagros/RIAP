from PIL import Image, ImageDraw, ImageFont
from tqdm import tqdm
import cv2
import numpy as np

def create_drying_video(data_path, output_path, time_base="TW_0", text_mins=None):

    folders_measurement = []
    combined_imgs = {}

    for folder in data_path.iterdir():
        
        if time_base in folder.name:
            combined_base_img = Image.open(folder / "polarimetry" / "550nm" / "Combined.png")
        else:
            folders_measurement.append(folder)
            
    for measurement in tqdm(folders_measurement):
        if not measurement.exists():
            continue
        if not measurement.is_dir():
            continue
        combined_imgs[measurement.name] = add_overlay(Image.open(measurement / "polarimetry" / "550nm" / "Combined.png"), text_image = text_mins["TW" + measurement.name.split("TW")[-1]])

    frames = []

    base_img = np.array(combined_base_img.convert("RGB"))
    h, w = base_img.shape[:2]

    for name, drying_img in combined_imgs.items():
        img = np.array(drying_img.convert("RGB"))
        img_resized = cv2.resize(img, (w, h))
        frames.append(img_resized[:, :, ::-1])

    # Output path
    fps = 1 
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(str(output_path), fourcc, fps, (w, h))

    for frame in frames:
        out.write(frame)
    out.release()

    print(f"✅ MP4 saved to: {output_path}")


def add_overlay(img, text_image=None):
    """
    Adds optional text directly on the image (no top band).

    Parameters:
        img (PIL.Image): Input image
        text (str): Unused here (kept for backward compatibility)
        text_image (str): Text to overlay on the image

    Returns:
        PIL.Image: Modified image with text overlay
    """
    img = img.convert("RGB")
    draw = ImageDraw.Draw(img)
    w, h = img.size

    # Choose font size proportional to image height
    font_size = int(h * 0.05)
    try:
        font = ImageFont.truetype("arial.ttf", size=font_size)
    except:
        font = ImageFont.load_default()

    # Draw only the keyword text if provided
    if text_image:
        # You can adjust position (x, y) here
        x, y = 55, 55
        draw.text((x, y), text_image, fill=(255, 255, 255), font=font)

    return img