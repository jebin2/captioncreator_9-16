import warnings
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)
import logging
logging.getLogger().setLevel(logging.ERROR)

import argparse
from moviepy import VideoFileClip, CompositeVideoClip, ImageClip
from moviepy.video.fx import FadeIn, FadeOut
from stt.fasterwhispher import FasterWhispherSTTProcessor
import utils
from custom_logger import logger_config
from typing import List, Dict, Tuple, Optional
import random
import os
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import numpy as np
from config import Config
import constants
import subprocess
from aspect_validator import AspectRatioValidator
from pathlib import Path
from safe_zone import SafeZone

class CaptionCreator:
	def __init__(self, video_path: str = None, config: Optional[Config] = None):
		"""Initialize the caption generator."""
		self._setup_required_folder()
		self.config = config or Config()
		self.video = None
		self.cfr_video_path = None
		self.needs_cleanup = False
		self.needs_crop = False
		chosen_font = random.choice(self.config.font_path)
		self.font_path = os.path.abspath(chosen_font)
		logger_config.info(f"Using font: {os.path.basename(self.font_path)}")
		self.word_timestamps = self.config.word_timestamps
		self.fps = None
		self.active_font_size = None
		self.active_stroke_width = None
		self.active_line_spacing = None
		self.active_shadow_offset = None
		self.active_shadow_blur = None
		self.active_stroke_corner_radius = None 

	def _setup_required_folder(self):
		utils.create_directory(constants.INPUT_FOLDER)
		utils.create_directory(constants.OUTPUT_FOLDER)
		utils.remove_directory(constants.TEMP_OUTPUT)
		utils.create_directory(constants.TEMP_OUTPUT)

	def set_video(self, video_path):
		if video_path:
			self.video_path = os.path.abspath(video_path)

			if self.config.enforce_9_16:
				width, height = AspectRatioValidator.get_video_dimensions(self.video_path)
				is_valid, actual_ratio, orientation = AspectRatioValidator.check_aspect_ratio(
					width, height
				)
				
				logger_config.info(
					f"Video dimensions: {width}x{height} "
					f"({orientation}, ratio: {actual_ratio:.4f})"
				)
				
				if not is_valid:
					target_ratio = AspectRatioValidator.TARGET_ASPECT
					logger_config.warning(
						f"Video is not 9:16! Current: {actual_ratio:.4f}, "
						f"Target: {target_ratio:.4f}"
					)
					
					if self.config.reject_invalid_aspect:
						raise ValueError(
							f"Video must be 9:16 aspect ratio. "
							f"Current: {width}x{height} ({actual_ratio:.4f})"
						)
					
					if self.config.auto_crop_to_9_16:
						logger_config.info("Auto-cropping to 9:16...")
						self.needs_crop = True
					else:
						logger_config.warning(
							"Video will be processed as-is (auto_crop disabled)"
						)
						self.needs_crop = False
				else:
					logger_config.success(f"✓ Video is 9:16 aspect ratio")
					self.needs_crop = False
			else:
				self.needs_crop = False

			self._load_video_data()

	def _convert_to_cfr_if_needed(self, input_path, target_fps):
		is_vfr, r_fps, avg_fps = utils.check_if_vfr(input_path)
		
		if is_vfr:
			logger_config.warning(
				f"Video is VFR (r_fps: {r_fps:.2f}, avg_fps: {avg_fps:.2f}). "
				f"Converting to CFR to prevent stuttering..."
			)
			
			cfr_path = f'{constants.TEMP_OUTPUT}/cfr_{utils.generate_random_string()}.mp4'
			
			cmd = [
				'ffmpeg', '-y',
				'-i', input_path,
				'-c:v', 'libx264',
				'-preset', 'veryfast',
				'-crf', '18',
				'-r', str(int(target_fps)),
				'-vsync', 'cfr',
				'-pix_fmt', 'yuv420p',
				'-c:a', 'aac',
				'-b:a', '192k',
				'-movflags', '+faststart',
				cfr_path
			]
			
			result = subprocess.run(cmd, text=True)
			
			if result.returncode != 0:
				logger_config.error(f"FFmpeg conversion failed: {result.stderr}")
				raise RuntimeError("Failed to convert video to CFR")
			
			logger_config.success(f"CFR video created: {cfr_path}")
			return cfr_path, True
		
		else:
			logger_config.info(
				f"Video is already CFR (fps: {r_fps:.2f}). Skipping conversion."
			)
			return input_path, False

	def _load_video_data(self) -> None:
		"""Load video file and extract word timestamps."""
		try:
			self.fps = utils.get_video_fps(self.video_path)

			video_to_load, was_converted = self._convert_to_cfr_if_needed(
				self.video_path, 
				self.fps
			)

			if was_converted:
				self.cfr_video_path = video_to_load
				self.needs_cleanup = True
			else:
				self.cfr_video_path = None
				self.needs_cleanup = False

			self.video = VideoFileClip(video_to_load)
			original_size = self.video.size
			
			logger_config.info(f"Original video: {original_size[0]}x{original_size[1]}")

			if self.needs_crop:
				logger_config.info("Cropping to 9:16 (center crop)...")
				self.video = AspectRatioValidator.crop_to_9_16(self.video)
				logger_config.success(
					f"✓ Cropped to {self.video.size[0]}x{self.video.size[1]}"
				)
			else:
				current_w, current_h = self.video.size
				x1, y1, x2, y2 = AspectRatioValidator.calculate_crop_dimensions(
					current_w, current_h
				)
				target_w, target_h = x2 - x1, y2 - y1
				logger_config.info(f"Padding to {target_w}x{target_h} with bars...")

				self.video = AspectRatioValidator.resize_and_pad_to_9_16(
					self.video,
					target_width=target_w,
					target_height=target_h,
					bg_color=self.config.padding_color
				)
				logger_config.success(
					f"✓ Padded to {self.video.size[0]}x{self.video.size[1]}"
				)

			if not self.word_timestamps:
				with FasterWhispherSTTProcessor() as STT:
					self.word_timestamps = STT.transcribe({
						"model": "fasterwhispher", 
						"input": self.video_path
					})["segments"]["word"]
			
			logger_config.info(f"Video loaded: {self.video.duration:.2f}s @ {self.fps} fps")
			logger_config.info(f"Final size: {self.video.size[0]}x{self.video.size[1]}")
			logger_config.info(f"Total words: {len(self.word_timestamps)}")
			
		except Exception as e:
			raise ValueError(f"Failed to load video: {str(e)}")

	def _clean_word(self, word: str) -> str:
		return word.strip('.,!?;:"""''').upper()
	
	def _calculate_word_duration(self, word_index: int) -> Tuple[float, float, float]:
		word_data = self.word_timestamps[word_index]
		start_time = word_data["start"]

		if word_index < len(self.word_timestamps) - 1:
			end_time = self.word_timestamps[word_index + 1]["start"]
		else:
			end_time = word_data["end"]

		end_time = min(end_time, self.video.duration)
		duration = end_time - start_time
		
		return start_time, end_time, duration

	def _create_text_clip(self,
						words_data: List[Dict],
						highlight_word_index: int,
						start_time: float,
						duration: float,
						group_start_index: int = 0) -> ImageClip:

		font = ImageFont.truetype(self.font_path, self.active_font_size)
		caption_width = int(self.video.size[0] * self.config.caption_width_ratio)
		space_width = font.getlength(" ")
		
		caption_parts = []
		for j, word_data in enumerate(words_data):
			word = self._clean_word(word_data["word"])
			color = self.config.highlight_text_color if self.config.highlight_text and (group_start_index + j == highlight_word_index) else self.config.text_color
			caption_parts.append((word, color))

		ascent, descent = font.getmetrics()
		line_height_from_font = ascent + descent
		lines, total_height = [], 0
		current_line, current_line_width = [], 0
		for word, color in caption_parts:
			word_width = font.getlength(word)
			if current_line and current_line_width + word_width > caption_width:
				lines.append((current_line, current_line_width - space_width))
				total_height += line_height_from_font + self.active_line_spacing
				current_line, current_line_width = [], 0
			current_line.append((word, color, word_width))
			current_line_width += word_width + space_width
		if current_line:
			lines.append((current_line, current_line_width - space_width))
			total_height += line_height_from_font

		shadow_offset_x, shadow_offset_y = self.active_shadow_offset
		total_expansion = self.active_stroke_width + self.active_stroke_corner_radius
		padding_x = total_expansion + abs(shadow_offset_x)
		padding_y = total_expansion + abs(shadow_offset_y)
		
		img_width = caption_width + padding_x * 2
		img_height = total_height + padding_y * 2 + descent
		
		final_img = Image.new("RGBA", (img_width, img_height), (0, 0, 0, 0))
		draw = ImageDraw.Draw(final_img)

		y_start = padding_y
		for line_words, line_width in lines:
			if self.config.horizontal_align == "center":
				x_start = (img_width - line_width) / 2
			else:
				x_start = padding_x

			text_mask = Image.new("L", final_img.size, 0)
			mask_draw = ImageDraw.Draw(text_mask)
			x_temp_line = x_start
			for word, _, word_width in line_words:
				mask_draw.text((x_temp_line, y_start + ascent), word, font=font, fill=255, anchor="ls")
				x_temp_line += word_width + space_width

			erosion_size = (self.active_stroke_corner_radius * 2) + 1
			eroded_mask = text_mask.filter(ImageFilter.MinFilter(erosion_size))
			expansion_size = ((self.active_stroke_width + self.active_stroke_corner_radius) * 2) + 1
			expanded_mask = eroded_mask.filter(ImageFilter.MaxFilter(expansion_size))

			black_color_layer = Image.new("RGBA", final_img.size, self.config.stroke_color)

			final_img.paste(black_color_layer, self.active_shadow_offset, mask=expanded_mask)

			final_img.paste(black_color_layer, (0, 0), mask=expanded_mask)

			x_temp_line = x_start
			for word, color, word_width in line_words:
				draw.text((x_temp_line, y_start + ascent), word, font=font, fill=color, anchor="ls")
				x_temp_line += word_width + space_width
				
			y_start += line_height_from_font + self.active_line_spacing

		txt_clip = ImageClip(np.array(final_img)).with_duration(duration).with_start(start_time)

		if self.config.use_safe_zones:
			_, y_pos = SafeZone.get_caption_position(
				video_width=self.video.size[0], video_height=self.video.size[1],
				caption_height=img_height, position=self.config.vertical_position,
				padding=self.config.safe_zone_padding
			)
			txt_clip = txt_clip.with_position(('center', y_pos))
		else:
			txt_clip = txt_clip.with_position((self.config.horizontal_align, self.config.vertical_align))
		if self.config.use_zoom_animation:
			txt_clip = utils.apply_zoom_animation(txt_clip,
				start_scale=self.config.zoom_start_scale, end_scale=self.config.zoom_end_scale,
				duration=min(self.config.zoom_duration, duration)
			)
		if self.config.use_fade_and_scale:
			fade_duration = min(self.config.fade_duration, duration * 0.3)
			txt_clip = txt_clip.resized(lambda t: max(0.1, 1 + self.config.scale_effect_intensity * (1 - abs(t - duration / 2) / max(0.1, duration / 2))))
			txt_clip = txt_clip.with_effects([FadeIn(fade_duration), FadeOut(fade_duration)])

		return txt_clip
	
	def generate(self, video_path=None) -> str:
		"""
		Create captions that display words with highlight.
		"""
		logger_config.info("Starting captions with highlight generation...")

		if video_path:
			self.set_video(video_path)

		if self.config.use_dynamic_font_size:
			video_width = self.video.size[0]
			scale_factor = video_width / self.config.standard_video_width

			self.active_font_size = int(self.config.font_size * scale_factor)
			self.active_stroke_width = int(self.config.stroke_width * scale_factor)
			self.active_line_spacing = int(self.config.line_spacing * scale_factor)
			self.active_shadow_offset = (
				int(self.config.shadow_offset[0] * scale_factor),
				int(self.config.shadow_offset[1] * scale_factor)
			)
			self.active_shadow_blur = int(self.config.shadow_blur_radius * scale_factor)
			self.active_stroke_corner_radius = int(self.config.stroke_corner_radius * scale_factor)

			logger_config.info(f"Dynamic sizing enabled (Factor: {scale_factor:.2f}).")
			logger_config.info(f"Font: {self.active_font_size}px, Stroke: {self.active_stroke_width}px, Corner Radius: {self.active_stroke_corner_radius}px")
		else:
			self.active_font_size = self.config.font_size
			self.active_stroke_width = self.config.stroke_width
			self.active_line_spacing = self.config.line_spacing
			self.active_shadow_offset = self.config.shadow_offset
			self.active_stroke_corner_radius = self.config.stroke_corner_radius
			self.active_shadow_blur = self.config.shadow_blur_radius
			logger_config.info(f"Using fixed styling values.")

		if self.config.use_word_grouping:
			video_width, video_height = self.video.size

			if self.config.use_safe_zone_for_width:
				safe_bounds = SafeZone.get_safe_area_bounds(video_width, video_height)
				max_caption_width = safe_bounds['width']
				logger_config.info(f"Using safe zone to set max caption width: {max_caption_width}px")
			else:
				max_caption_width = video_width - self.config.grouping_left_padding - self.config.grouping_right_padding
				logger_config.info(f"Using manual padding to set max caption width: {max_caption_width}px")
			
			caption_groups = utils.group_words_by_time_and_width(
				word_timestamps=self.word_timestamps,
				max_gap_seconds=self.config.grouping_max_gap_seconds,
				max_width_px=max_caption_width,
				font_path=self.font_path,
				font_size=self.active_font_size
			)
			logger_config.success(f"Processed {len(self.word_timestamps)} words into {len(caption_groups)} caption groups.")
		else:
			raise NotImplementedError("The old word-by-word logic needs to be adapted or removed.")

		try:
			text_clips = []
			for i, group in enumerate(caption_groups):
				start_time = group["start"]
				end_time = group["end"]
				if i+1 < len(caption_groups):
					duration = caption_groups[i+1]["start"] - start_time
				else:
					duration = self.video.duration - start_time
				
				if start_time >= self.video.duration or duration <= 0:
					continue
				
				txt_clip = self._create_text_clip(
                    words_data=group["words"],
                    highlight_word_index=-1, 
                    start_time=start_time,
                    duration=duration
                )
				
				text_clips.append(txt_clip)
				
				logger_config.info(f"Processed group {i + 1}/{len(caption_groups)}", overwrite=True)

			final_clip = CompositeVideoClip([self.video] + text_clips)

			parts = self.config.output_path.split('/')
			file_stem = Path(self.video_path).stem
			self.config.output_path = f"{constants.OUTPUT_FOLDER}/{file_stem}_captioned.mp4"

			utils.write_videofile(final_clip, self.config.output_path, fps=self.fps)
			final_clip.close()
			
		finally:
			utils.remove_file(self.cfr_video_path)
			logger_config.debug(f"Cleaned up temporary CFR file")
		
		logger_config.success(f"Video saved to: {self.config.output_path}")
		return self.config.output_path
	
	def close(self) -> None:
		"""Clean up resources."""
		if self.video:
			self.video.close()
	
	def __enter__(self):
		"""Context manager entry."""
		return self
	
	def __exit__(self, exc_type, exc_val, exc_tb):
		"""Context manager exit."""
		self.close()


# Usage example
if __name__ == "__main__":
	"""Main entry point."""
	parser = argparse.ArgumentParser()
	parser.add_argument("--input", required=False, help="Path to the input video")
	parser.add_argument("--config_path", required=False, help="Path to configuration JSON")
	args = parser.parse_args()

	if args.config_path:
		custom_config = Config.from_json(args.config_path)
	else:
		custom_config = Config()

	if args.input:
		with CaptionCreator(None, custom_config) as caption_generator:
			caption_generator.generate(args.input)
	else:
		with CaptionCreator(None, custom_config) as caption_generator:
			files = [file for file in utils.list_files_recursive(constants.INPUT_FOLDER) if file.endswith((".mp4", ".mov", ".avi", ".mkv", ".webm"))]
			for file in files:
				caption_generator.generate(file)

			if len(files) == 0:
				logger_config.warning('No Video files available in the input folder (".mp4", ".mov", ".avi", ".mkv", ".webm")')