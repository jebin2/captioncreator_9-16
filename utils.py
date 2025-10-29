from pathlib import Path
import subprocess
import json
import os
import shutil
import string
from custom_logger import logger_config
import constants
import secrets

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
        logger_config.warning(f"Error occurred while trying to remove the file: {e}")
        if retry:
            logger_config.debug("retrying after 10 seconds", seconds=10)
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
        # audio_codec='aac',
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