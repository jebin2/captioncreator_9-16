from moviepy import ColorClip, CompositeVideoClip
from moviepy.video.fx import Crop
import subprocess
import json

class AspectRatioValidator:
    TARGET_ASPECT = 9 / 16  # 0.5625
    TOLERANCE = 0.02  # Allow 2% variance
    
    @staticmethod
    def get_video_dimensions(video_path):
        """Get video dimensions using ffprobe."""
        cmd = [
            'ffprobe', '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height',
            '-of', 'json',
            video_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        data = json.loads(result.stdout)
        stream = data['streams'][0]
        
        width = int(stream['width'])
        height = int(stream['height'])
        
        return width, height
    
    @staticmethod
    def check_aspect_ratio(width, height):
        actual_ratio = width / height
        target_ratio = AspectRatioValidator.TARGET_ASPECT
        tolerance = AspectRatioValidator.TOLERANCE

        is_valid = abs(actual_ratio - target_ratio) <= tolerance

        if actual_ratio < 0.7:
            orientation = "portrait"
        elif actual_ratio > 1.3:
            orientation = "landscape"
        else:
            orientation = "square"
        
        return is_valid, actual_ratio, orientation
    
    @staticmethod
    def calculate_crop_dimensions(width, height, target_ratio=9/16):
        current_ratio = width / height
        
        if current_ratio > target_ratio:
            # Video is too wide -> crop width
            new_width = int(height * target_ratio)
            new_height = height
            x1 = (width - new_width) // 2
            y1 = 0
            x2 = x1 + new_width
            y2 = height
        else:
            # Video is too tall -> crop height
            new_width = width
            new_height = int(width / target_ratio)
            x1 = 0
            y1 = (height - new_height) // 2
            x2 = width
            y2 = y1 + new_height
        
        return x1, y1, x2, y2
    
    @staticmethod
    def crop_to_9_16(video_clip):
        width, height = video_clip.size
        x1, y1, x2, y2 = AspectRatioValidator.calculate_crop_dimensions(width, height)

        cropped = video_clip.with_effects([
            Crop(x1=x1, y1=y1, x2=x2, y2=y2)
        ])
        
        return cropped
    
    @staticmethod
    def resize_and_pad_to_9_16(video_clip, target_width=1080, target_height=1920, bg_color=(0, 0, 0)):
        current_width, current_height = video_clip.size
        current_ratio = current_width / current_height
        target_ratio = target_width / target_height

        if current_ratio > target_ratio:
            # Video is wider -> fit to width, add top/bottom bars (letterbox)
            new_width = target_width
            new_height = int(target_width / current_ratio)
            x_offset = 0
            y_offset = (target_height - new_height) // 2
        else:
            # Video is taller -> fit to height, add left/right bars (pillarbox)
            new_height = target_height
            new_width = int(target_height * current_ratio)
            x_offset = (target_width - new_width) // 2
            y_offset = 0

        resized_video = video_clip.resized((new_width, new_height))

        background = ColorClip(
            size=(target_width, target_height),
            color=bg_color,
            duration=video_clip.duration
        )

        resized_video = resized_video.with_position((x_offset, y_offset))

        final_video = CompositeVideoClip([background, resized_video])
        
        return final_video
    
    @staticmethod
    def calculate_fit_dimensions(width, height, target_width, target_height):
        current_ratio = width / height
        target_ratio = target_width / target_height
        
        if current_ratio > target_ratio:
            # Wider -> fit to width
            new_width = target_width
            new_height = int(target_width / current_ratio)
            x_offset = 0
            y_offset = (target_height - new_height) // 2
        else:
            # Taller -> fit to height
            new_height = target_height
            new_width = int(target_height * current_ratio)
            x_offset = (target_width - new_width) // 2
            y_offset = 0
        
        return new_width, new_height, x_offset, y_offset