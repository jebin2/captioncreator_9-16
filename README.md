# Automatic Video Caption Generator

This script automatically generates and adds stylish, word-by-word animated captions to your videos. It uses Faster-Whisper for accurate transcription and MoviePy for video processing.

## Features

*   **Automatic Transcription:** No need to write captions manually.
*   **Word-by-Word Animation:** Highlights words as they are spoken.
*   **Customizable Styles:** Easily change fonts, colors, highlights, and animations via a `config.json` file.
*   **9:16 Aspect Ratio Handling:** Automatically validates and pads videos to the correct vertical format.
*   **Safe Zone Placement:** Ensures captions are not obscured by social media UI elements.

## 1. Setup

**Prerequisites:**
*   Python 3.10.12
*   `ffmpeg` installed and accessible in your system's PATH.

**Installation:**

1.  **Clone the repository:**
    ```bash
    git clone <your-repository-url>
    cd <your-repository-name>
    ```

2.  **Create and activate a Python environment:**
    Using `pyenv` is recommended to manage Python versions.
    ```bash
    pyenv install 3.10.12
    pyenv virtualenv 3.10.12 caption-env
    pyenv local caption-env
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Add Fonts:**
    Place your desired `.ttf` font files inside the `Fonts` folder.

## 2. How to Use

1.  **Place videos** into the `input` folder. The script supports formats like `.mp4`, `.mov`, `.mkv`, etc.

2.  **(Optional) Customize Styles:**
    Modify the `config.json` file to change the appearance of the captions (colors, font size, animations, etc.).

3.  **Run the script:**
    ```bash
    python caption_creator.py
    ```
    The script will process all videos found in the `input` directory.

4.  **Find your videos:**
    The final, captioned videos will be saved in the `output` folder.
