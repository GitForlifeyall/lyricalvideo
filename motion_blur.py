"""
Motion Blur Module for LyricalVideo
Based on TonyAssi/Motion-Blur (https://github.com/TonyAssi/Motion-Blur)

Provides:
- Directional linear motion blur using OpenCV 2D convolution kernel (filter2D)
- Configurable distance (kernel size), angle (direction in degrees), and blend amount
- Video and Image processing support
"""

import os
import cv2
import numpy as np
from PIL import Image
from typing import Union, Optional, Tuple


def create_motion_blur_kernel(distance: int = 30, angle: float = 0.0) -> np.ndarray:
    """
    Generate a normalized directional motion blur convolution kernel.
    
    :param distance: Length of the blur streak (kernel dimension, must be >= 1).
    :param angle: Direction of motion blur in degrees (0 = horizontal, 90 = vertical).
    :return: Normalized 2D numpy array kernel.
    """
    k_size = max(3, int(distance))
    # Ensure kernel dimension is odd for symmetry
    if k_size % 2 == 0:
        k_size += 1

    kernel = np.zeros((k_size, k_size), dtype=np.float32)
    center = k_size // 2

    # Horizontal streak on center row
    kernel[center, :] = 1.0

    # Rotate kernel for arbitrary motion angle
    if angle % 180 != 0:
        rot_mat = cv2.getRotationMatrix2D((center, center), angle, 1.0)
        kernel = cv2.warpAffine(kernel, rot_mat, (k_size, k_size))

    # Normalize kernel so total weight equals 1.0 (preserves brightness)
    k_sum = np.sum(kernel)
    if k_sum > 0:
        kernel /= k_sum
    else:
        kernel[center, center] = 1.0

    return kernel


def motion_blur(
    image: Union[Image.Image, np.ndarray],
    distance: int = 25,
    angle: float = 0.0,
    amount: float = 0.85
) -> Union[Image.Image, np.ndarray]:
    """
    Apply directional linear motion blur to an image or frame.
    
    :param image: PIL Image or OpenCV NumPy array (RGB, RGBA, BGR, or BGRA).
    :param distance: Intensity / length of the motion streak.
    :param angle: Direction angle in degrees (0 = horizontal, 90 = vertical, 45 = diagonal).
    :param amount: Blend factor between blurred (amount) and original (1 - amount) [0.0 - 1.0].
    :return: Blurred image in same format as input.
    """
    if distance <= 1 or amount <= 0:
        return image

    is_pil = isinstance(image, Image.Image)
    if is_pil:
        img_np = np.array(image)
    else:
        img_np = image.copy()

    kernel = create_motion_blur_kernel(distance, angle)

    # Handle RGBA transparent channel if present
    if len(img_np.shape) == 3 and img_np.shape[2] == 4:
        # Blur RGB and Alpha channels separately or together
        blurred = cv2.filter2D(img_np, -1, kernel)
    else:
        blurred = cv2.filter2D(img_np, -1, kernel)

    # Linear blend between original and blurred frame
    if amount < 1.0:
        result = cv2.addWeighted(blurred, float(amount), img_np, float(1.0 - amount), 0)
    else:
        result = blurred

    if is_pil:
        return Image.fromarray(result)
    return result


def background_motion_blur(
    image: Union[Image.Image, np.ndarray],
    mask: Optional[np.ndarray] = None,
    distance_blur: int = 40,
    angle_blur: float = 0.0,
    amount_blur: float = 0.9,
    amount_subject: float = 1.0
) -> Union[Image.Image, np.ndarray]:
    """
    Apply directional motion blur to the background while keeping foreground/subject sharp.
    
    :param image: Input image.
    :param mask: Optional binary/alpha mask (255 = foreground subject, 0 = background).
    :param distance_blur: Blur streak length for background.
    :param angle_blur: Blur direction in degrees.
    :param amount_blur: Background blur intensity.
    :param amount_subject: Subject clarity factor.
    """
    is_pil = isinstance(image, Image.Image)
    img_np = np.array(image) if is_pil else image.copy()

    bg_blurred = motion_blur(img_np, distance=distance_blur, angle=angle_blur, amount=amount_blur)

    if mask is not None:
        if len(mask.shape) == 2 and len(img_np.shape) == 3:
            mask_3ch = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR) / 255.0
        elif mask.shape == img_np.shape:
            mask_3ch = mask / 255.0
        else:
            mask_3ch = np.ones_like(img_np, dtype=np.float32)

        composite = (img_np * mask_3ch * amount_subject + bg_blurred * (1.0 - mask_3ch)).astype(np.uint8)
    else:
        composite = bg_blurred

    if is_pil:
        return Image.fromarray(composite)
    return composite


def process_video_motion_blur(
    input_video_path: str,
    output_video_path: str,
    distance: int = 30,
    angle: float = 0.0,
    amount: float = 0.85
) -> str:
    """
    Process an entire video file applying frame-by-frame directional motion blur.
    """
    cap = cv2.VideoCapture(input_video_path)
    if not cap.isOpened():
        raise IOError(f"Cannot open video file {input_video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    temp_out = output_video_path + ".tmp.mp4"
    out = cv2.VideoWriter(temp_out, fourcc, fps, (width, height))

    kernel = create_motion_blur_kernel(distance, angle)

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        blurred_frame = cv2.filter2D(frame, -1, kernel)
        if amount < 1.0:
            frame_final = cv2.addWeighted(blurred_frame, float(amount), frame, float(1.0 - amount), 0)
        else:
            frame_final = blurred_frame
        out.write(frame_final)

    cap.release()
    out.release()
    cv2.destroyAllWindows()

    if os.path.exists(temp_out):
        if os.path.exists(output_video_path):
            os.remove(output_video_path)
        os.rename(temp_out, output_video_path)

    return output_video_path
