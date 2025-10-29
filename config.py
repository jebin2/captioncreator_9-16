from dataclasses import dataclass, field, asdict, fields
from typing import List, Tuple, Literal
import utils
import json
import constants

@dataclass
class WordTimestamp:
    word: str
    start_offset: int
    end_offset: int
    start: float
    end: float

@dataclass
class Config:
    """A single configuration class to style captions."""

    # --- Font and Color ---
    font_path: List[str] = field(default_factory=lambda: [
        "Fonts/Archivo_Black,Bungee/Archivo_Black/ArchivoBlack-Regular.ttf"
    ])
    color_palette: List[str] = field(default_factory=lambda: [
        "#E74747", "#FF6B6B", "#4ECDC4", "#2AA0BB", "#36AF77",
        "#C565C5", "#58310B", "#6C5CE7", "#1C533F", "#BB394C"
    ])

    # --- General Text Properties ---
    font_size: int = 80
    standard_video_width: int = 1080
    use_dynamic_font_size: bool = True
    text_color: str = "#FFFFFF"
    stroke_color: str = "#000000"
    stroke_width: int = 10
    stroke_corner_radius: int = 6
    line_spacing: int = 10
    vertical_align: str = "center"
    horizontal_align: str = "center"
    
    # --- Positioning ---
    use_safe_zones: bool = True
    vertical_position: Literal["top", "center", "bottom"] = "bottom"
    safe_zone_padding: int = 20
    
    # --- Animation (for word-by-word) ---
    use_fade_and_scale: bool = False
    fade_duration: float = 0.2
    scale_effect_intensity: float = 0.15
    
    # --- Zoom Animation ---
    use_zoom_animation: bool = True
    zoom_start_scale: float = 0.8
    zoom_end_scale: float = 1.0
    zoom_duration: float = 0.3

    # --- Text Properties ---
    word_count: int = 1
    line_spacing: int = 10
    caption_width_ratio: float = 0.9
    bg_color: str = "#6C5CE7"

    # --- Caption Grouping ---
    use_word_grouping: bool = True
    grouping_max_gap_seconds: float = 0.2  # Max gap between words to be in the same group
    use_safe_zone_for_width: bool = True
    grouping_left_padding: int = 60      # Left safe margin in pixels
    grouping_right_padding: int = 120     # Right safe margin in pixels
    split_long_captions: bool = True
    max_caption_duration_seconds: int = 1
    
    # --- Highlighting (for grouped) ---
    highlight_text: bool = False
    highlight_text_color: str = "white"
    highlight_bg_color: str = "#5846DD"
    highlight_padding: Tuple[int, int] = (10, 5)  # (horizontal, vertical)

    # --- NEW: Drop Shadow Properties ---
    use_drop_shadow: bool = True
    shadow_color: str = "#000000E6"  # Darker shadow (90% opacity)
    shadow_offset: Tuple[int, int] = (6, 6)  # Subtle offset
    shadow_blur_radius: int = 20
    shadow_style: Literal["drop_shadow", "block_shadow"] = "block_shadow"

    # --- Aspect Ratio Validation ---
    auto_crop_to_9_16: bool = False
    enforce_9_16: bool = True
    fit_method: Literal["crop", "pad"] = "pad"
    reject_invalid_aspect: bool = False
    padding_color: Tuple[int, int, int] = (0, 0, 0)

    # --- Output Path ---
    word_timestamps: List[WordTimestamp] = field(default_factory=list)
    output_path: str = f'{constants.OUTPUT_FOLDER}/{utils.generate_random_string()}.mp4'

    @staticmethod
    def from_json(json_path: str) -> "Config":
        """Load Config from JSON, merging with defaults."""
        with open(json_path, "r") as f:
            json_data = json.load(f)

        # Get default config as dict
        default_values = asdict(Config())

        # Filter json_data to only keys present in Config fields
        field_names = {f.name for f in fields(Config)}
        filtered_data = {k: v for k, v in json_data.items() if k in field_names}

        # Merge filtered JSON data into defaults
        merged = {**default_values, **filtered_data}

        return Config(**merged)

    def to_json(self, json_path: str, indent: int = 4) -> None:
        """Export current Config instance to a JSON file."""
        with open(json_path, "w") as f:
            json.dump(asdict(self), f, indent=indent)
        print(f"✅ Config saved to {json_path}")