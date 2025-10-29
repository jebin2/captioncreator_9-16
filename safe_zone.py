from dataclasses import dataclass
from typing import Tuple, Literal

@dataclass
class SafeZone:
    STANDARD_WIDTH = 1080
    STANDARD_HEIGHT = 1920
    
    # Safe zone measurements from edges (in pixels for standard dimensions)
    # mockup was 540x960 (half size), measurements doubled here
    TOP_SAFE_ZONE = 252      # 126px * 2 from top
    BOTTOM_SAFE_ZONE = 756   # 378px * 2 from bottom
    LEFT_SAFE_ZONE = 120     # 60px * 2 from left
    RIGHT_SAFE_ZONE = 240    # 120px * 2 from right
    
    @staticmethod
    def get_caption_position(
        video_width: int,
        video_height: int,
        caption_height: int,
        position: Literal["top", "center", "bottom"] = "bottom",
        padding: int = 20
    ) -> Tuple[str, int]:
        # Scale safe zones proportionally to actual video dimensions
        scale_y = video_height / SafeZone.STANDARD_HEIGHT
        # scale_x = video_width / SafeZone.STANDARD_WIDTH
        
        top_safe = int(SafeZone.TOP_SAFE_ZONE * scale_y)
        bottom_safe = int(SafeZone.BOTTOM_SAFE_ZONE * scale_y)
        
        if position == "top":
            y_position = top_safe + padding
            
        elif position == "center":
            safe_area_height = video_height - top_safe - bottom_safe
            y_position = top_safe + (safe_area_height - caption_height) // 2
            
        else:
            y_position = video_height - bottom_safe - caption_height - padding
        
        return ("center", y_position)
    
    @staticmethod
    def get_safe_area_bounds(
        video_width: int,
        video_height: int
    ) -> dict:
        scale_y = video_height / SafeZone.STANDARD_HEIGHT
        scale_x = video_width / SafeZone.STANDARD_WIDTH
        
        top = int(SafeZone.TOP_SAFE_ZONE * scale_y)
        bottom = video_height - int(SafeZone.BOTTOM_SAFE_ZONE * scale_y)
        left = int(SafeZone.LEFT_SAFE_ZONE * scale_x)
        right = video_width - int(SafeZone.RIGHT_SAFE_ZONE * scale_x)
        
        return {
            'top': top,
            'bottom': bottom,
            'left': left,
            'right': right,
            'width': right - left,
            'height': bottom - top
        }