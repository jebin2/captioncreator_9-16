from pathlib import Path
import subprocess
import json
import os
import shutil
import string
from custom_logger import logger_config
import constants
import secrets
from PIL import ImageFont
import cv2
from PIL import Image
import numpy as np

def list_files_recursive(directory):
    file_list = []

    for root, _, files in os.walk(directory):
        for file in files:
            # Get the full path
            file_list.append(os.path.join(root, file))
    
    return file_list

def remove_file(file_path, retry=True):
    try:
        if os.path.exists(file_path):
            Path(file_path).unlink()
            logger_config.success(f"{file_path} has been removed successfully.")
    except Exception as e:
        if retry:
            remove_file(file_path, False)

def remove_directory(directory_path):
    try:
        if os.path.exists(directory_path):
            shutil.rmtree(directory_path, ignore_errors=True)
            logger_config.debug(f'Directory Deleted at: {directory_path}')
    except Exception as e:
        logger_config.warning(f'An error occurred: {e}')

def create_directory(directory_path):
    try:
        os.makedirs(directory_path, exist_ok=True)
        logger_config.debug(f'Directory created at: {directory_path}')
    except Exception as e:
        logger_config.error(f'An error occurred: {e}')

def generate_random_string(length=10):
    characters = string.ascii_letters
    random_string = ''.join(secrets.choice(characters) for _ in range(length))
    return random_string

def write_videofile(video_clip, output_path, fps=constants.FPS):
    video_clip.write_videofile(
        output_path,
        fps=fps,
        codec='libx264',
        preset='veryfast',
        threads=os.cpu_count(),
        ffmpeg_params=[
            '-pix_fmt', 'yuv420p',
            '-movflags', '+faststart',
        ],
        remove_temp=True,
        # Optional
        # temp_audiofile=audio_file,
        # write_logfile=False,
        # bitrate='8000k',
        audio_codec='aac',
    )

def get_video_fps(video_path):
    """Get the actual display frame rate (tbr) from video."""
    try:
        cmd = [
            'ffprobe', '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=r_frame_rate',
            '-of', 'json',
            video_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        data = json.loads(result.stdout)
        r_frame_rate = data['streams'][0]['r_frame_rate']
        num, den = map(int, r_frame_rate.split('/'))
        fps = num / den
        
        print(f"Detected frame rate: {fps} fps")
        return fps
        
    except Exception as e:
        print(f"Error detecting FPS: {e}, using default 30")
        return 30

def apply_zoom_animation(clip, start_scale=0.8, end_scale=1.0, duration=0.3):
    def scale_function(t):
        if t < duration:
            progress = t / duration
            # Ease-out cubic for smooth deceleration
            eased = 1 - (1 - progress) ** 3
            return start_scale + (end_scale - start_scale) * eased
        return end_scale
    
    return clip.resized(scale_function)

def check_if_vfr(video_path):
    try:
        cmd = [
            'ffprobe', '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=r_frame_rate,avg_frame_rate',
            '-of', 'json',
            video_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        data = json.loads(result.stdout)
        stream = data['streams'][0]
        
        r_frame_rate = stream['r_frame_rate']
        avg_frame_rate = stream['avg_frame_rate']

        def parse_rate(rate_str):
            num, den = map(int, rate_str.split('/'))
            return num / den
        
        r_fps = parse_rate(r_frame_rate)
        avg_fps = parse_rate(avg_frame_rate)
        
        # Consider VFR if difference is more than 1 fps
        is_vfr = abs(r_fps - avg_fps) > 1.0
        
        return is_vfr, r_fps, avg_fps
        
    except Exception as e:
        print(f"Warning: Could not detect VFR status: {e}")
        return False, 30.0, 30.0

def get_text_width(text, font_path, font_size):
    """Calculates the pixel width of a given text string."""
    try:
        font = ImageFont.truetype(font_path, font_size)
        return font.getlength(text)
    except IOError:
        print(f"Font file not found at {font_path}. Cannot calculate text width.")
        # Fallback to a rough estimate if font is not found
        return len(text) * font_size * 0.6

def group_words_by_time_and_width(
    word_timestamps,
    max_gap_seconds: float,
    max_width_px: int,
    font_path: str,
    font_size: int,
    max_words_per_group: int = 3,
    max_caption_duration_seconds: int = 0.6
):
    if not word_timestamps:
        return []

    caption_groups = []
    current_group = []

    for word_data in word_timestamps:
        processed_word = word_data["word"].strip().upper()
        if not processed_word:
            continue
        
        word_data["word"] = processed_word

        if not current_group:
            current_group.append(word_data)
            continue

        last_word_in_group = current_group[-1]
        time_gap = word_data["start"] - last_word_in_group["end"]
        total_time = last_word_in_group["end"] - current_group[0]["start"]

        potential_text = " ".join([w["word"] for w in current_group] + [word_data["word"]])
        potential_width = get_text_width(potential_text, font_path, font_size)

        if (len(current_group) < max_words_per_group and 
            time_gap <= max_gap_seconds and 
            potential_width <= max_width_px and
            total_time <= max_caption_duration_seconds
            ):
            current_group.append(word_data)
        else:
            group_text = " ".join([w["word"] for w in current_group])
            start_time = current_group[0]["start"]
            end_time = current_group[-1]["end"]
            
            caption_groups.append({
                "text": group_text,
                "words": current_group,
                "start": start_time,
                "end": end_time
            })

            current_group = [word_data]

    if current_group:
        group_text = " ".join([w["word"] for w in current_group])
        start_time = current_group[0]["start"]
        end_time = current_group[-1]["end"]
        
        caption_groups.append({
            "text": group_text,
            "words": current_group,
            "start": start_time,
            "end": end_time
        })

    return caption_groups

def make_rounded_outline(mask: Image.Image, radius: int) -> Image.Image:
    """
    Create a rounded stroke from a text alpha mask using elliptical dilation.
    This is the key function for universally rounded corners.
    """
    if radius <= 0:
        return mask.copy()
    
    # Convert PIL Image to a NumPy array for OpenCV
    a = np.array(mask)
    
    # Create the elliptical structuring element for perfect rounding
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * radius + 1, 2 * radius + 1))
    
    # Dilate the image - this expands the white areas, creating the stroke shape
    dilated_array = cv2.dilate(a, kernel, iterations=1)
    
    # Convert the NumPy array back to a PIL Image
    return Image.fromarray(dilated_array, mode="L")