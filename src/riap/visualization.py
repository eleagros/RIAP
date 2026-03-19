"""Visualization helpers for plots, GIFs, and simple video generation in RIAP."""

from PIL import Image, ImageDraw, ImageFont
from tqdm import tqdm
import cv2
import imageio
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def _to_rgb(img: np.ndarray) -> np.ndarray:
    if img.ndim == 2:
        return cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)


def create_alignment_gif(
    image1: np.ndarray,
    image2: np.ndarray,
    save_path: str,
    n_frames: int = 20,
    duration: float = 0.1,
    resize_factor: float = 1,
):
    img1_rgb = _to_rgb(image1)
    img2_rgb = _to_rgb(image2)

    if img1_rgb.shape != img2_rgb.shape:
        img2_rgb = cv2.resize(img2_rgb, (img1_rgb.shape[1], img1_rgb.shape[0]))

    if resize_factor != 1:
        new_size = (int(img1_rgb.shape[1] * resize_factor), int(img1_rgb.shape[0] * resize_factor))
        img1_rgb = cv2.resize(img1_rgb, new_size)
        img2_rgb = cv2.resize(img2_rgb, new_size)

    forward_frames = [cv2.addWeighted(img1_rgb, 1 - alpha, img2_rgb, alpha, 0) for alpha in np.linspace(0, 1, n_frames)]
    backward_frames = forward_frames[-2:0:-1]
    frames = forward_frames + backward_frames

    imageio.mimsave(save_path, frames, duration=duration, loop=0)


def _resolve_x_values(df: pd.DataFrame, folder_to_time: dict):
    index_values = list(df.index)
    x_values = pd.to_numeric(pd.Series(index_values), errors='coerce')

    if x_values.isna().any():
        x_values = np.arange(len(index_values), dtype=float)
    else:
        x_values = x_values.to_numpy(dtype=float)

    x_tick_labels = [
        str(folder_to_time.get(int(idx), idx)) if str(idx).isdigit() else str(idx)
        for idx in index_values
    ]

    return x_values, x_tick_labels


def _compute_condition_stats(df: pd.DataFrame):
    num_columns = df.shape[1]
    split_index = num_columns // 2

    condition1 = df.iloc[:, :split_index]
    condition2 = df.iloc[:, split_index:]

    n1 = condition1.shape[1]
    n2 = condition2.shape[1]

    mean1 = condition1.mean(axis=1)
    std1 = condition1.std(axis=1)
    sem1 = std1 / np.sqrt(n1)
    ci1 = 1.96 * sem1

    mean2 = condition2.mean(axis=1)
    std2 = condition2.std(axis=1)
    sem2 = std2 / np.sqrt(n2)
    ci2 = 1.96 * sem2

    return mean1, ci1, mean2, ci2


def plot_parameter_comparison(res_path, out_path, folder_to_time, parameter_file="totP_prism_cv.xlsx", parameters_to_name=None, plot_limits=None):
    file_path = res_path / parameter_file
    parameter = parameter_file.split("_prism")[0]
    is_cv = "cv" in parameter_file
    save_path = out_path / f"{parameters_to_name[parameter]}{'_cv' if is_cv else ''}.png"
    print(save_path)

    df = pd.read_excel(file_path, index_col=0)

    x_values, x_tick_labels = _resolve_x_values(df, folder_to_time)
    mean1, ci1, mean2, ci2 = _compute_condition_stats(df)

    plt.figure()

    line1, = plt.plot(x_values, mean1, linestyle='-', label='GM')
    plt.scatter(x_values, mean1, s=35, color=line1.get_color(), zorder=3)
    plt.fill_between(x_values, mean1 - ci1, mean1 + ci1, alpha=0.3)

    line2, = plt.plot(x_values, mean2, linestyle='-', label='WM')
    plt.scatter(x_values, mean2, s=35, color=line2.get_color(), zorder=3)
    plt.fill_between(x_values, mean2 - ci2, mean2 + ci2, alpha=0.3)

    plt.xticks(x_values, x_tick_labels)
    plt.xlabel("Time (mins)")
    plt.ylabel("Value")
    plt.legend()
    plt.tight_layout()
    limits = plot_limits[f"{parameter}{'_cv' if is_cv else ''}"]
    plt.ylim(limits[0], limits[1])
    plt.savefig(save_path)
    plt.savefig(save_path.with_suffix(".pdf"))
    plt.close()


def add_overlay(img, text_image=None):
    img = img.convert("RGB")
    draw = ImageDraw.Draw(img)
    _, h = img.size

    font_size = int(h * 0.05)
    try:
        font = ImageFont.truetype("arial.ttf", size=font_size)
    except Exception:
        font = ImageFont.load_default()

    if text_image:
        draw.text((55, 55), text_image, fill=(255, 255, 255), font=font)

    return img


def create_drying_video(data_path, output_path, time_base="TW_0", text_mins=None):
    folders_measurement = []
    combined_imgs = {}

    for folder in sorted(data_path.iterdir(), key=lambda p: p.name):
        if time_base in folder.name:
            combined_base_img = Image.open(folder / "polarimetry" / "550nm" / "Combined.png")
        elif folder.exists() and folder.is_dir():
            folders_measurement.append(folder)

    for measurement in tqdm(folders_measurement):
        image_text = None
        if text_mins is not None:
            image_text = text_mins.get("TW" + measurement.name.split("TW")[-1])
        combined_imgs[measurement.name] = add_overlay(
            Image.open(measurement / "polarimetry" / "550nm" / "Combined.png"),
            text_image=image_text,
        )

    frames = []

    base_img = np.array(combined_base_img.convert("RGB"))
    h, w = base_img.shape[:2]

    for _, drying_img in sorted(combined_imgs.items(), key=lambda item: item[0]):
        img = np.array(drying_img.convert("RGB"))
        img_resized = cv2.resize(img, (w, h))
        frames.append(img_resized[:, :, ::-1])

    fps = 1
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(str(output_path), fourcc, fps, (w, h))

    for frame in frames:
        out.write(frame)
    out.release()

    print(f"✅ MP4 saved to: {output_path}")


def plot_parameter_comparison_multi_solution(
    solutions_paths: dict,
    output_path,
    folder_to_time: dict,
    parameter_file: str = "totP_prism_cv.xlsx",
    parameters_to_name: dict = None,
    plot_limits: dict = None
):
    """
    Plot parameter comparison for multiple solutions on separate GM and WM figures.

    Parameters
    ----------
    solutions_paths : dict
        Dictionary mapping solution names (e.g., "Solution 1", "Solution 2") to their result directories.
        Example: {"Solution 1": Path(...), "Solution 2": Path(...)}
    output_path : Path
        Directory where the plots will be saved.
    folder_to_time : dict
        Mapping from folder IDs to time points for x-axis labeling.
    parameter_file : str
        Name of the Excel file to load (default: "totP_prism_cv.xlsx").
    """
    output_path.mkdir(parents=True, exist_ok=True)

    parameter = parameter_file.split("_prism")[0]
    is_cv = "cv" in parameter_file
    base_name = f"{parameters_to_name[parameter]}{'_cv' if is_cv else ''}"

    # Colors for different solutions
    colors = plt.cm.tab10(np.linspace(0, 1, len(solutions_paths)))

    x_tick_labels = None
    x_values = None

    # Create separate figures for GM and WM
    fig_gm, ax_gm = plt.subplots(figsize=(10, 6))
    fig_wm, ax_wm = plt.subplots(figsize=(10, 6))

    for idx, (solution_name, sol_path) in enumerate(solutions_paths.items()):
        file_path = sol_path / parameter_file
        if not file_path.exists():
            print(f"⚠️  {file_path} not found, skipping {solution_name}")
            continue

        df = pd.read_excel(file_path, index_col=0)

        # Resolve x values and labels (same for all solutions)
        if x_values is None:
            x_values, x_tick_labels = _resolve_x_values(df, folder_to_time)

        mean1, ci1, mean2, ci2 = _compute_condition_stats(df)

        # Plot GM
        ax_gm.plot(
            x_values,
            mean1,
            linestyle='-',
            color=colors[idx],
            label=solution_name,
            linewidth=2.5
        )
        ax_gm.fill_between(x_values, mean1 - ci1, mean1 + ci1, alpha=0.2, color=colors[idx])

        # Plot WM
        ax_wm.plot(
            x_values,
            mean2,
            linestyle='-',
            color=colors[idx],
            label=solution_name,
            linewidth=2.5
        )
        ax_wm.fill_between(x_values, mean2 - ci2, mean2 + ci2, alpha=0.2, color=colors[idx])

    limits = plot_limits[f"{parameter}{'_cv' if is_cv else ''}"]

    # Configure GM plot
    ax_gm.set_xticks(x_values)
    ax_gm.set_xticklabels(x_tick_labels)
    ax_gm.set_xlabel("Time (mins)")
    ax_gm.set_ylabel("Value")
    ax_gm.set_title("GM - Multi-Solution Comparison")
    ax_gm.legend(fontsize=10, loc='best')
    ax_gm.grid(True, alpha=0.3)
    ax_gm.set_ylim(limits[0], limits[1])
    fig_gm.tight_layout()

    # Configure WM plot
    ax_wm.set_xticks(x_values)
    ax_wm.set_xticklabels(x_tick_labels)
    ax_wm.set_xlabel("Time (mins)")
    ax_wm.set_ylabel("Value")
    ax_wm.set_title("WM - Multi-Solution Comparison")
    ax_wm.legend(fontsize=10, loc='best')
    ax_wm.grid(True, alpha=0.3)
    ax_wm.set_ylim(limits[0], limits[1])
    fig_wm.tight_layout()

    # Save plots    
    gm_output = output_path / f"{base_name}_gm.pdf"
    fig_gm.savefig(gm_output)
    fig_gm.savefig(output_path / f"{base_name}_gm.png", dpi=300)
    plt.close(fig_gm)
    print(f"✅ GM plot saved to: {gm_output}")

    wm_output = output_path / f"{base_name}_wm.pdf"
    fig_wm.savefig(wm_output, dpi=300)
    fig_wm.savefig(output_path / f"{base_name}_wm.png", dpi=300)
    plt.close(fig_wm)
    print(f"✅ WM plot saved to: {wm_output}")
