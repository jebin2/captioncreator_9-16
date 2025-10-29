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
from PIL import Image, ImageDraw, ImageFont
import numpy as np
from config import Config
import constants
import subprocess
from aspect_validator import AspectRatioValidator

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
		
		# Set end time to the start time of the next word for continuity
		if word_index < len(self.word_timestamps) - 1:
			end_time = self.word_timestamps[word_index + 1]["start"]
		else:
			end_time = word_data["end"]
		
		# Ensure we don't exceed video duration
		end_time = min(end_time, self.video.duration)
		duration = end_time - start_time
		
		return start_time, end_time, duration
	
	def _create_text_clip(self,
						words_data: List[Dict],
						highlight_word_index: int,
						start_time: float,
						duration: float,
						group_start_index: int = 0) -> ImageClip:
		caption_width = int(self.video.size[0] * self.config.caption_width_ratio)

		caption_parts = []
		word_to_highlight = None
		for j, word_data in enumerate(words_data):
			word = self._clean_word(word_data["word"])
			if group_start_index + j == highlight_word_index:
				caption_parts.append((word, self.config.highlight_text_color))
				word_to_highlight = word
			else:
				caption_parts.append((word, self.config.text_color))

		# Load font
		font = ImageFont.truetype(self.font_path, self.config.font_size)

		# Simulate layout to calculate required height
		dummy_img = Image.new("RGBA", (caption_width, 10), (0, 0, 0, 0))
		draw = ImageDraw.Draw(dummy_img)

		space_width = draw.textlength(" ", font=font)

		# Buffer lines and compute dimensions
		lines = []
		current_line = []
		current_line_width = 0
		max_line_height = 0
		total_height = 0

		for word, color in caption_parts:
			word_width = draw.textlength(word, font=font)

			bbox = draw.textbbox((0, 0), word, font=font)
			word_height = bbox[3] - bbox[1]
			max_line_height = max(max_line_height, word_height)

			if current_line_width + word_width > caption_width:
				if current_line:
					lines.append((current_line, current_line_width - space_width, max_line_height))
					total_height += max_line_height + self.config.line_spacing

				current_line = []
				current_line_width = 0
				max_line_height = word_height

			current_line.append((word, color, word_width))
			current_line_width += word_width + space_width

		if current_line:
			lines.append((current_line, current_line_width - space_width, max_line_height))
			total_height += max_line_height + self.config.line_spacing

		padding = int(self.config.font_size * 0.4)
		total_height += padding

		img = Image.new("RGBA", (caption_width, total_height), (0, 0, 0, 0))
		draw = ImageDraw.Draw(img)

		y = 0
		for line_words, line_width, line_height in lines:
			if self.config.horizontal_align == "center":
				x = (caption_width - line_width) / 2
			elif self.config.horizontal_align == "left":
				x = 0
			else:
				x = caption_width - line_width

			for word, color, word_width in line_words:
				if word_to_highlight == word:
					padding_x, padding_y = self.config.highlight_padding

					text_bbox = draw.textbbox((x, y), word, font=font)
					rect_y0 = text_bbox[1] - padding_y
					rect_y1 = text_bbox[3] + padding_y

					rect_x0 = x - padding_x
					rect_x1 = x + word_width + padding_x

					draw.rounded_rectangle(
						[rect_x0, rect_y0, rect_x1, rect_y1],
						fill=self.config.highlight_bg_color,
						radius=15,
					)

				for dx in range(-self.config.stroke_width, self.config.stroke_width + 1):
					for dy in range(-self.config.stroke_width, self.config.stroke_width + 1):
						draw.text((x + dx, y + dy), word, font=font, fill=self.config.stroke_color)

				draw.text((x, y), word, font=font, fill=color)

				x += word_width + space_width

			y += line_height + self.config.line_spacing

		txt_clip = ImageClip(np.array(img)).with_duration(duration).with_start(start_time)

		if self.config.use_safe_zones:
			from safe_zone import SafeZone
			
			_, y_pos = SafeZone.get_caption_position(
				video_width=self.video.size[0],
				video_height=self.video.size[1],
				caption_height=img.height,
				position=self.config.vertical_position,
				padding=self.config.safe_zone_padding
			)
			txt_clip = txt_clip.with_position((self.config.horizontal_align, y_pos))
		else:
			txt_clip = txt_clip.with_position(
				(self.config.horizontal_align, self.config.vertical_align)
			)

		if self.config.use_zoom_animation:
			txt_clip = utils.apply_zoom_animation(
				txt_clip,
				start_scale=self.config.zoom_start_scale,
				end_scale=self.config.zoom_end_scale,
				duration=min(self.config.zoom_duration, duration)
			)

		if self.config.use_fade_and_scale:
			fade_duration = min(self.config.fade_duration, duration * 0.3)

			# Apply scaling effect
			txt_clip = txt_clip.resized(lambda t: max(0.1, 1 + self.config.scale_effect_intensity * (1 - abs(t - duration / 2) / max(0.1, duration / 2))))

			# Apply fade effects
			txt_clip = txt_clip.with_effects([FadeIn(fade_duration), FadeOut(fade_duration)])

		return txt_clip
	
	def generate(self, video_path=None) -> str:
		"""
		Create captions that display words with highlight.
		"""
		logger_config.info("Starting captions with highlight generation...")

		if video_path:
			self.set_video(video_path)

		caption_width = int(self.video.size[0] * self.config.caption_width_ratio)
		logger_config.info(f"Setting caption width to {caption_width}px")
		
		try:
			text_clips = []
			for i in range(len(self.word_timestamps)):
				group_start_index = (i // self.config.word_count) * self.config.word_count
				group_end_index = min(len(self.word_timestamps), group_start_index + self.config.word_count)
				group_words_data = self.word_timestamps[group_start_index:group_end_index]
				
				start_time, _, duration = self._calculate_word_duration(i)
				
				if start_time >= self.video.duration:
					break
				
				if duration <= 0:
					continue
				
				txt_clip = self._create_text_clip(
					words_data=group_words_data,
					highlight_word_index=i if self.config.highlight_text else -1,
					start_time=start_time,
					duration=duration,
					group_start_index=group_start_index
				)
				
				text_clips.append(txt_clip)
				
				logger_config.info(f"Processed word {i + 1}/{len(self.word_timestamps)}", overwrite=True)

			final_clip = CompositeVideoClip([self.video] + text_clips)
			utils.write_videofile(final_clip, self.config.output_path, fps=self.fps)
			final_clip.close()
			
		finally:
			# Remove temporary CFR file
			if hasattr(self, 'cfr_video_path') and os.path.exists(self.cfr_video_path):
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
			files = utils.list_files_recursive(constants.INPUT_FOLDER)
			for file in files:
				if file.endswith((".mp4", ".mov", ".avi", ".mkv", ".webm")
):
					caption_generator.generate(file)

			if len(files) == 0:
				logger_config.warning('No Video files available in the input folder (".mp4", ".mov", ".avi", ".mkv", ".webm")')