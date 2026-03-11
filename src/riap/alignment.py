"""Alignment and warping utilities for RIAP image registration workflows."""

from pathlib import Path
import pickle
import random
import shutil
import subprocess
import sys

import cv2
from loguru import logger
import numpy as np
from PIL import Image
import SimpleITK as sitk
import tifffile as tiff

from riap.visualization import create_alignment_gif
from riap.manual_steps import semi_automatic_processing

_MAX_VALUE = 2**16 - 1


def write_mp_fp_txt_format(
    mp_fp,
    feature_matching_method: str = None,
) -> str:
    """Format matched feature points as tab-separated text for downstream tools."""
    header = 'Index\txSource\tySource\txTarget\tyTarget\n'
    gen = enumerate(zip(mp_fp[1], mp_fp[0]))
    lines = [
        f"{index}\t{round(fp[0])}\t{round(fp[1])}\t{round(mp[0])}\t{round(mp[1])}\n"
        for index, (fp, mp) in gen
    ]
    return header + ''.join(lines)


def warp_images_with_fun(images_to_warp, fun, final_shape):
    """Warp a mapping of images with a provided callable registration function."""
    warped_images = {}

    for key, img in images_to_warp.items():
        if img is None or np.prod(img.shape) == 0:
            logger.warning("ERROR: Encountered an empty/None image, skipping.")
            continue

        if img.ndim == 2:
            img = np.stack([img] * 3, axis=-1)
        elif img.ndim == 3 and img.shape[2] == 1:
            img = np.repeat(img, 3, axis=2)
        elif img.ndim != 3 or img.shape[2] not in [3, 4]:
            logger.warning(f"Unexpected image shape {img.shape}, skipping.")
            continue

        _, warped_img = fun(input_image1=img)
        if final_shape is not None:
            warped_img = cv2.resize(
                warped_img,
                (final_shape[1], final_shape[0]),
                interpolation=cv2.INTER_NEAREST,
            )

        warped_images[key] = warped_img

    return warped_images


class OpenCVAligner:
    """Apply a callable warping function to a set of images to propagate labels."""

    def __init__(
        self,
        output_folder: Path,
        input_folder: Path,
        to_propagate: Path,
        fun,
        initial_shape,
    ) -> None:
        self.output_folder = output_folder
        self.input_folder = input_folder
        self.to_propagate = to_propagate
        self.reg_fun = fun
        self.initial_shape = initial_shape

    def run(self) -> None:
        to_propagate_images = {}
        for img_path in sorted(self.to_propagate.glob("*.png"), key=lambda path: path.name):
            to_propagate_images[img_path.name] = cv2.imread(str(img_path), cv2.IMREAD_UNCHANGED)

        warped_images = warp_images_with_fun(
            to_propagate_images,
            self.reg_fun,
            self.initial_shape,
        )

        for name, img in warped_images.items():
            Image.fromarray(img).save(self.to_propagate.parent / name.replace(".png", "_warped.png"))


def warp_images_with_H(reference_image, images_to_warp, H):
    h, w = reference_image.shape[:2]
    warped_images = {}

    for key, img in images_to_warp.items():
        if img is None or np.prod(img.shape) == 0:
            logger.warning("ERROR: Encountered an empty/None image, skipping.")
            continue

        if img.ndim == 3 and img.shape[2] == 4:
            img = img[:, :, :3]

        img_dtype = img.dtype
        img_ndim = img.ndim

        if img_ndim == 2 and img_dtype == np.int32:
            warped_img = cv2.warpPerspective(
                img,
                H,
                (w, h),
                flags=cv2.INTER_NEAREST,
            )
        elif img_ndim >= 2:
            warped_img = cv2.warpPerspective(img, H, (w, h), flags=cv2.INTER_NEAREST)
        else:
            logger.warning(
                f"ERROR: Unhandled image format encountered. Shape: {img.shape}, Dtype: {img_dtype}. Skipping warp."
            )
            continue

        warped_images[key] = warped_img

    return warped_images


def run_alignment_pipeline(cfg, folder, image0, image1, invreg_dir, output_folder):
    if (folder / "annotation" / "override.txt").exists():
        points_moving, points_reference = semi_automatic_processing(folder, image0, image1, force_recompute=False)
        points_reference = np.array(points_reference)
        points_moving = np.array(points_moving)
    else:
        if str(cfg.paths.match_anything_path) not in sys.path:
            sys.path.append(str(cfg.paths.match_anything_path))
        from imcui.ui.utils import run_matching

        random.seed(42)
        ransac_reproj_threshold = 12

        results = run_matching(
            image0,
            image1,
            match_threshold=0.15,
            extract_max_keypoints=5000,
            keypoint_threshold=0.015,
            key="matchanything_roma",
            ransac_method="CV2_RANSAC",
            ransac_reproj_threshold=ransac_reproj_threshold,
            ransac_confidence=0.999,
            ransac_max_iter=10000,
            choice_geometry_type="Homography",
            matcher_zoo=get_matcher_zoo(cfg),
            force_resize=False,
            image_width=640,
            image_height=480,
            use_cached_model=False,
            model=None,
            matcher=None,
            use_ransac=True,
        )

        points_reference, points_moving = results[3][0], results[3][1]
        dst = invreg_dir / f"match_anything_output_{folder.stem}.png"
        Image.fromarray(results[2]).save(dst)
        dst = invreg_dir / f"match_anything_output_full_{folder.stem}.png"
        Image.fromarray(results[1]).save(dst)

    with open(output_folder / "matched_points.pickle", "wb") as file_obj:
        pickle.dump((points_reference, points_moving), file_obj)

    return points_reference, points_moving, results


def get_matcher_zoo(cfg) -> dict:
    if str(cfg.paths.match_anything_path) not in sys.path:
        sys.path.append(str(cfg.paths.match_anything_path))
    from imcui.ui.utils import parse_match_config

    base_conf = {
        "matchanything_eloftr": {
            "dense": True,
            "matcher": "matchanything_eloftr",
        },
        "matchanything_roma": {
            "dense": True,
            "matcher": "matchanything_roma",
        },
    }

    zoo = {}
    for key, conf in base_conf.items():
        zoo[key] = parse_match_config(conf)
    return zoo


def align_with_sitk(fixed_arr, to_propagate, matching_points):
    fixed_image = sitk.GetImageFromArray(fixed_arr)

    fixed_points = matching_points[1]
    moving_points = matching_points[0]
    fixed_landmarks = fixed_points.astype(np.uint16).flatten().tolist()
    moving_landmarks = moving_points.astype(np.uint16).flatten().tolist()

    transform = sitk.BSplineTransformInitializer(fixed_image, (3, 3), 3)
    landmark_initializer = sitk.LandmarkBasedTransformInitializerFilter()
    landmark_initializer.SetFixedLandmarks(fixed_landmarks)
    landmark_initializer.SetMovingLandmarks(moving_landmarks)
    landmark_initializer.SetReferenceImage(fixed_image)
    landmark_initializer.Execute(transform)
    output_transform = landmark_initializer.Execute(transform)

    interpolator = sitk.sitkNearestNeighbor
    moving_images = [sitk.GetImageFromArray(to_propagate), sitk.GetImageFromArray(fixed_arr)]
    resampled_images = []
    for moving_img in moving_images:
        resampled_images.append(
            sitk.GetArrayFromImage(sitk.Resample(moving_img, fixed_image, output_transform, interpolator, 0))
        )

    return resampled_images


def recover_and_reconstruct_labels(cfg, path_output, mask):
    registered_x = tiff.imread(path_output / "registered_x.tif") / _MAX_VALUE * cfg.settings.shape_imgs[0]
    registered_y = tiff.imread(path_output / "registered_y.tif") / _MAX_VALUE * cfg.settings.shape_imgs[1]

    mask_aligned = reconstruct_labels(cfg, [registered_x, registered_y], mask)
    Image.fromarray(mask_aligned).save(path_output / "mask_registered.png")

    image_aligned = reconstruct_labels(
        cfg,
        [registered_x, registered_y],
        cv2.imread(str(path_output / "fixed.png"), cv2.IMREAD_GRAYSCALE),
    )
    Image.fromarray(image_aligned).save(path_output / "image_registered.png")


def reconstruct_labels(cfg, maps, original_labels):
    [registered_x, registered_y] = maps
    reconstructed_labels = np.zeros((cfg.settings.shape_imgs[1], cfg.settings.shape_imgs[0]), dtype=np.uint8)

    for idx, row in enumerate(registered_x):
        for idy, y in enumerate(row):
            idy_original_image = round(y)
            idx_original_image = round(registered_y[idx, idy])
            if idx_original_image == cfg.settings.shape_imgs[1] or idy_original_image == cfg.settings.shape_imgs[0]:
                continue
            reconstructed_labels[idx, idy] = original_labels[idx_original_image, idy_original_image]

    return reconstructed_labels


def align_imgs_ImgJ(cfg, folder, path_output, mask):
    save_imgs_alignment(cfg, path_output)
    macro = generate_macro(path_output)
    macro_path = Path(path_output) / "macro.ijm"
    with open(macro_path, "w") as file_obj:
        file_obj.write(macro)
    subprocess.run(["xvfb-run", "-a", str(cfg.paths.fiji_path), "--console", "-macro", macro_path], check=True)
    recover_and_reconstruct_labels(cfg, path_output, mask)
    move_the_alignment_results(path_output, folder)


def save_imgs_alignment(cfg, path_output) -> None:
    img_to_propagate = create_propagation_img(cfg)
    for idx, suffix in enumerate(["x", "y"]):
        path_img_tmp = path_output / f"img_brightfield_{suffix}.tif"
        cv2.imwrite(str(path_img_tmp), img_to_propagate[idx])
    return img_to_propagate


def create_propagation_img(cfg):
    x_coords = np.arange(cfg.settings.shape_imgs[1])
    y_coords = np.arange(cfg.settings.shape_imgs[0])
    to_propagate = [
        np.tile(x_coords, (cfg.settings.shape_imgs[0], 1)),
        np.tile(y_coords, (cfg.settings.shape_imgs[1], 1)).T,
    ]

    scale = _MAX_VALUE
    max_ = _MAX_VALUE
    img_to_propagate = [
        np.clip(((to_propagate[1] / np.max(np.abs(to_propagate[1]))) * scale).T.astype("uint16"), 0, max_),
        np.clip(((to_propagate[0] / np.max(np.abs(to_propagate[0]))) * scale).T.astype("uint16"), 0, max_),
    ]
    return img_to_propagate


def move_the_alignment_results(path_output, folder):
    output_folder = folder / "annotation" / "alignment_results"
    output_folder.mkdir(parents=True, exist_ok=True)

    shutil.copy(path_output / "mask_registered.png", output_folder / "mask_registered.png")
    shutil.copy(path_output / "image_registered.png", output_folder / "image_registered.png")

    create_alignment_gif(
        np.array(Image.open(path_output / "moving.png")),
        np.array(Image.open(path_output / "image_registered.png")),
        output_folder / "gif_registered.gif",
        n_frames=20,
        duration=0.1,
    )


def generate_macro(measurement_folder) -> str:
    path_tmp = '"' + str(measurement_folder)
    path_tmp_no_start = path_tmp.replace('"', '')

    macro = """
    open(""" + path_tmp + """/fixed.png");
    open(""" + path_tmp + """/moving.png");
    call("bunwarpj.bUnwarpJ_.loadLandmarks", """ + path_tmp + """/coordinates.txt");
    run("bUnwarpJ", "load=""" + path_tmp_no_start + """/coordinates.txt source_image=moving.png target_image=fixed.png registration=Accurate image_subsample_factor=0 initial_deformation=[Very Coarse] final_deformation=[Coarse] divergence_weight=0.1 curl_weight=0.1 landmark_weight=1.5 image_weight=0 consistency_weight=10 stop_threshold=0.01 save_transformations save_direct_transformation=""" + path_tmp_no_start + """/global_img_direct_transf.txt save_inverse_transformation=""" + path_tmp_no_start + """/intensity_img_inverse_transf.txt");
    close();
    close();
    close();
    open(""" + path_tmp + """/fixed.png");
    open(""" + path_tmp + """/img_brightfield_x.tif");
    selectImage("img_brightfield_x.tif");
    call("bunwarpj.bUnwarpJ_.loadElasticTransform", """ + path_tmp + """/intensity_img_inverse_transf.txt", "fixed.png", "img_brightfield_x.tif");
    saveAs("Tiff", """ + path_tmp + """/registered_x.tif");
    close();
    close();
    open(""" + path_tmp + """/fixed.png");
    open(""" + path_tmp + """/img_brightfield_y.tif");
    selectImage("img_brightfield_y.tif");
    call("bunwarpj.bUnwarpJ_.loadElasticTransform", """ + path_tmp + """/intensity_img_inverse_transf.txt", "fixed.png", "img_brightfield_y.tif");
    saveAs("Tiff", """ + path_tmp + """/registered_y.tif");
    close();
    close();
    run("Quit");
    """
    return macro
