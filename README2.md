# WhisperTranscriber

WhisperTranscriber is a macOS application that transcribes video and audio files into subtitles using OpenAI's Whisper model. This guide provides step-by-step instructions on how to build and package it into a standalone macOS application.

## Prerequisites

Ensure you have the following installed on your macOS system:
- **Python 3.8+** (Recommended to use pyenv to manage Python versions)
- **Homebrew** (for installing dependencies like FFmpeg)
- **FFmpeg** (`brew install ffmpeg`)
- **PyInstaller** (`pip install pyinstaller`)

## Setup Instructions

1. **Clone the Repository:**
   ```sh
   git clone https://github.com/your-repo/whisper-transcriber.git
   cd whisper-transcriber
   ```

2. **Create and Activate a Virtual Environment:**
   ```sh
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install Dependencies:**
   ```sh
   pip install -r requirements.txt
   ```

4. **Ensure Whisper Assets Exist:**
   Verify that Whisper's assets are located at:
   ```sh
   ls whisper/assets
   ```
   If missing, manually download the Whisper assets or reinstall Whisper:
   ```sh
   pip uninstall openai-whisper && pip install openai-whisper
   ```

## Building the macOS App

To compile the application into a `.app` bundle, run:

```sh
pyinstaller --onefile --windowed --name "WhisperTranscriber" \
    --hidden-import=whisper \
    --add-data="$(python -c 'import whisper, os; print(os.path.dirname(whisper.__file__))')/assets:whisper/assets" \
    transcriber_app.py
```

Alternatively, if the above command fails, use the absolute path:

```sh
pyinstaller --onefile --windowed --name "WhisperTranscriber" \
    --hidden-import=whisper \
    --add-data="/Users/your-username/Documents/GitHub/whisper/whisper/assets:whisper/assets" \
    transcriber_app.py
```

After a successful build, the compiled `.app` file will be in the `dist/` folder:

```sh
open dist/WhisperTranscriber.app
```

## Troubleshooting

### 1. **Whisper Assets Not Found**
If you receive errors about missing assets, manually copy them:
```sh
mkdir -p dist/WhisperTranscriber.app/Contents/MacOS/whisper/assets
cp -r whisper/assets/* dist/WhisperTranscriber.app/Contents/MacOS/whisper/assets/
```

### 2. **Missing Libraries in PyInstaller Output**
If PyInstaller reports missing shared libraries, try reinstalling dependencies:
```sh
pip install --upgrade torch torchvision torchaudio
```

### 3. **Application Crashes on Launch**
- Run the app from the terminal to see error logs:
  ```sh
  ./dist/WhisperTranscriber.app/Contents/MacOS/WhisperTranscriber
  ```
- Ensure your FFmpeg installation is working correctly:
  ```sh
  ffmpeg -version
  ```

## License
This project is licensed under the MIT License.

