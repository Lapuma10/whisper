import tkinter as tk
from tkinter import filedialog, ttk, messagebox
import subprocess
import os
import sys
import threading
import tempfile
import shutil
from pathlib import Path
import logging
import traceback

# Set up paths for bundled app
if getattr(sys, 'frozen', False):
    # Running as bundled app
    bundle_dir = sys._MEIPASS
    os.environ["WHISPER_ASSETS"] = os.path.join(bundle_dir, "whisper", "assets")
    # Log to Documents folder (no permission issues)
    log_file = os.path.join(Path.home(), "Documents", "whisper_transcriber.log")
else:
    # Running in development
    bundle_dir = os.path.dirname(os.path.abspath(__file__))
    log_file = "whisper_transcriber.log"

# Set up comprehensive logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
    handlers=[
        logging.FileHandler(log_file, mode='w'),
        logging.StreamHandler(sys.stdout)
    ]
)

logging.info("="*60)
logging.info("Whisper Video Transcriber Starting")
logging.info(f"Python version: {sys.version}")
logging.info(f"Platform: {sys.platform}")
logging.info(f"Frozen: {getattr(sys, 'frozen', False)}")
logging.info(f"Bundle dir: {bundle_dir}")
logging.info(f"Log file: {log_file}")
logging.info("="*60)

# Log all bundled resource paths for debugging
if getattr(sys, 'frozen', False):
    logging.info("BUNDLED RESOURCES CHECK:")
    
    # Check FFmpeg
    ffmpeg_path = os.path.join(bundle_dir, 'ffmpeg')
    if os.path.exists(ffmpeg_path):
        logging.info(f"  ✓ FFmpeg: {ffmpeg_path}")
        logging.info(f"    - Executable: {os.access(ffmpeg_path, os.X_OK)}")
        
        # CRITICAL: Add bundled ffmpeg to PATH immediately so whisper.audio.load_audio() can find it
        # This ensures the Whisper library's internal ffmpeg calls work
        if bundle_dir not in os.environ.get('PATH', ''):
            original_path = os.environ.get('PATH', '')
            os.environ['PATH'] = bundle_dir + os.pathsep + original_path
            logging.info(f"    - Added bundle_dir to PATH for ffmpeg access")
    else:
        logging.error(f"  ✗ FFmpeg NOT FOUND at: {ffmpeg_path}")
    
    # Check Whisper assets
    whisper_assets = os.path.join(bundle_dir, "whisper", "assets")
    logging.info(f"  Whisper Assets Dir: {whisper_assets}")
    if os.path.exists(whisper_assets):
        assets = os.listdir(whisper_assets)
        logging.info(f"    - Found {len(assets)} asset files:")
        for asset in assets:
            asset_path = os.path.join(whisper_assets, asset)
            size_mb = os.path.getsize(asset_path) / (1024*1024)
            logging.info(f"      • {asset} ({size_mb:.1f} MB)")
    else:
        logging.error(f"  ✗ Whisper assets directory NOT FOUND")
    
    # Check system PATH after modification
    logging.info(f"  Current PATH (first 200 chars): {os.environ.get('PATH', 'NOT SET')[:200]}...")
    
    logging.info("="*60)

# Global variables
whisper_model = None
current_model_name = None
cancel_flag = False
current_temp_dir = None
processing_thread = None

# Whisper model options
MODEL_OPTIONS = {
    "Tiny (fastest, least accurate)": "tiny",
    "Base": "base",
    "Small": "small",
    "Medium": "medium",
    "Large-v2": "large-v2",
    "Large-v3": "large-v3",
    "Large-v3-Turbo (recommended)": "large-v3-turbo"
}

# Words per line options for subtitles
WORDS_PER_LINE_OPTIONS = {
    "2 words (short lines)": 2,
    "4 words (medium)": 4,
    "6 words (long lines)": 6,
    "8 words (very long)": 8,
    "10 words (maximum)": 10
}

# Language options based on Whisper supported languages
LANGUAGE_OPTIONS = {
    "Auto Detect": None,
    "Norwegian": "no",
    "English": "en",
    "Spanish": "es",
    "French": "fr",
    "German": "de",
    "Italian": "it",
    "Portuguese": "pt",
    "Dutch": "nl",
    "Russian": "ru",
    "Chinese": "zh",
    "Japanese": "ja",
    "Korean": "ko",
    "Arabic": "ar",
    "Turkish": "tr",
    "Polish": "pl",
    "Swedish": "sv",
    "Danish": "da",
    "Finnish": "fi",
    "Greek": "el",
    "Hebrew": "he",
    "Hindi": "hi",
    "Czech": "cs",
    "Romanian": "ro",
    "Ukrainian": "uk",
    "Vietnamese": "vi",
    "Thai": "th",
    "Indonesian": "id",
    "Malay": "ms",
    "Filipino": "tl",
    "Hungarian": "hu",
    "Bulgarian": "bg",
    "Croatian": "hr",
    "Slovak": "sk",
    "Lithuanian": "lt",
    "Slovenian": "sl",
    "Estonian": "et",
    "Latvian": "lv"
}

def load_model_lazy(model_name):
    """Load Whisper model only when needed"""
    global whisper_model, current_model_name
    
    logging.info(f"load_model_lazy called with: {model_name}")
    
    # If model is already loaded and it's the right one, return it
    if whisper_model is not None and current_model_name == model_name:
        logging.info(f"Model {model_name} already loaded, reusing")
        return whisper_model
    
    # Load new model
    try:
        import whisper
        logging.info(f"Importing whisper module...")
        update_status(f"Loading {model_name} model (first time may take a while)...")
        logging.info(f"Loading model: {model_name}")
        
        # Check if running from bundle and model exists locally
        if getattr(sys, 'frozen', False):
            model_path = os.path.join(sys._MEIPASS, "whisper", "assets", f"{model_name}.pt")
            logging.info(f"Looking for bundled model at: {model_path}")
            if os.path.exists(model_path):
                logging.info(f"Found bundled model, loading from: {model_path}")
                # Load directly from bundled path
                import torch
                checkpoint = torch.load(model_path, map_location="cpu")
                dims = whisper.model.ModelDimensions(**checkpoint["dims"])
                whisper_model = whisper.model.Whisper(dims)
                whisper_model.load_state_dict(checkpoint["model_state_dict"])
                whisper_model = whisper_model.cpu()
                current_model_name = model_name
                logging.info(f"Model {model_name} loaded successfully from bundle")
                return whisper_model
            else:
                # CRITICAL ERROR: Bundled model should always be present
                error_msg = (
                    f"CRITICAL: Bundled model not found!\n\n"
                    f"Expected location: {model_path}\n\n"
                    f"This app should not require downloads. The bundle may be "
                    f"corrupted or incomplete.\n\n"
                    f"Please re-download the app or contact support."
                )
                logging.error(f"Bundled model not found at {model_path}")
                logging.error("Bundle appears corrupted - model file missing!")
                update_status("❌ Bundle error: Model file missing!")
                return None
        
        # Development mode: use normal loading
        whisper_model = whisper.load_model(model_name)
        current_model_name = model_name
        logging.info(f"Model {model_name} loaded successfully")
        return whisper_model
    except Exception as e:
        logging.error(f"Error loading model: {str(e)}")
        logging.error(traceback.format_exc())
        update_status(f"Error loading model: {str(e)}")
        return None

def update_status(message):
    """Thread-safe status update"""
    try:
        window.after(0, lambda: result_label.config(text=message))
    except:
        pass

def update_progress(value):
    """Thread-safe progress update"""
    try:
        window.after(0, lambda: progress.set(value))
    except:
        pass

def get_ffmpeg_path():
    """Get FFmpeg path - bundled or system"""
    if getattr(sys, 'frozen', False):
        # Running in PyInstaller bundle
        bundled_ffmpeg = os.path.join(sys._MEIPASS, 'ffmpeg')
        logging.info(f"Looking for bundled ffmpeg at: {bundled_ffmpeg}")
        if os.path.exists(bundled_ffmpeg):
            logging.info(f"Found bundled ffmpeg: {bundled_ffmpeg}")
            return bundled_ffmpeg
        else:
            logging.warning(f"Bundled ffmpeg not found at {bundled_ffmpeg}")
    # Fallback to system ffmpeg
    logging.info("Using system ffmpeg")
    return 'ffmpeg'

def cleanup_temp_files():
    """Clean up temporary audio files"""
    global current_temp_dir
    if current_temp_dir and os.path.exists(current_temp_dir):
        try:
            shutil.rmtree(current_temp_dir)
            current_temp_dir = None
        except Exception as e:
            print(f"Error cleaning up temp files: {e}")

def extract_and_split_audio(video_file, output_dir, segment_length=600):
    """Extract and split audio from video file"""
    logging.info(f"extract_and_split_audio called")
    logging.info(f"  video_file: {video_file}")
    logging.info(f"  output_dir: {output_dir}")
    logging.info(f"  segment_length: {segment_length}")
    
    if cancel_flag:
        logging.info("Cancel flag set, aborting audio extraction")
        return False
    
    output_template = os.path.join(output_dir, "segment_%03d.wav")
    ffmpeg_cmd = get_ffmpeg_path()
    logging.info(f"Using ffmpeg: {ffmpeg_cmd}")
    
    try:
        # Build subprocess args with platform-specific flags
        subprocess_args = {
            'capture_output': True,
            'text': True
        }
        if sys.platform == "win32":
            subprocess_args['creationflags'] = subprocess.CREATE_NO_WINDOW
        
        cmd = [
            ffmpeg_cmd, '-i', video_file, '-ac', '1', '-ar', '44100', 
            '-f', 'segment', '-segment_time', str(segment_length),
            '-c:a', 'pcm_s16le', output_template, '-y'
        ]
        logging.info(f"Running ffmpeg command: {' '.join(cmd)}")
        
        result = subprocess.run(cmd, **subprocess_args)
        
        logging.info(f"FFmpeg return code: {result.returncode}")
        if result.stdout:
            logging.debug(f"FFmpeg stdout: {result.stdout}")
        if result.stderr:
            logging.debug(f"FFmpeg stderr: {result.stderr}")
        
        if result.returncode != 0:
            error_msg = f"FFmpeg error: {result.stderr[:100]}"
            logging.error(error_msg)
            update_status(error_msg)
            return False
        
        # Check output files
        segments = [f for f in os.listdir(output_dir) if f.startswith("segment_") and f.endswith(".wav")]
        logging.info(f"Created {len(segments)} audio segments")
        return True
        
    except FileNotFoundError as e:
        error_msg = "FFmpeg not found! Please install FFmpeg and add it to PATH."
        logging.error(f"{error_msg} - {str(e)}")
        update_status(error_msg)
        return False
    except Exception as e:
        error_msg = f"Error extracting audio: {str(e)}"
        logging.error(error_msg)
        logging.error(traceback.format_exc())
        update_status(error_msg)
        return False

def transcribe_audio_segments(temp_dir, model_name, language_code, max_words_per_line=6):
    """Transcribe each audio segment"""
    global cancel_flag
    from whisper.utils import get_writer
    
    logging.info(f"transcribe_audio_segments called with max_words_per_line={max_words_per_line}")
    
    if cancel_flag:
        return None
    
    # FFmpeg is already in PATH from startup (see lines 54-59)
    # Verify it's available
    logging.info(f"PATH contains bundle_dir: {bundle_dir in os.environ.get('PATH', '')}")
    
    model = load_model_lazy(model_name)
    if model is None:
        return None
    
    segment_files = sorted([f for f in os.listdir(temp_dir) if f.startswith("segment_") and f.endswith(".wav")])
    
    if not segment_files:
        update_status("No audio segments found!")
        return None
    
    srt_files = []
    total_segments = len(segment_files)
    
    for i, segment in enumerate(segment_files):
        if cancel_flag:
            update_status("Transcription cancelled!")
            return None
        
        segment_path = os.path.join(temp_dir, segment)
        update_status(f"Transcribing segment {i+1}/{total_segments}...")
        update_progress(10 + (i / total_segments) * 80)
        
        try:
            # Build transcribe parameters
            transcribe_params = {"word_timestamps": True}
            if language_code:
                transcribe_params["language"] = language_code
            
            result = model.transcribe(segment_path, **transcribe_params)
            segment_srt_file = os.path.join(temp_dir, f"segment_{i:03d}.srt")
            
            # Use Whisper's get_writer to write the SRT file
            srt_writer = get_writer("srt", temp_dir)
            srt_writer(result, segment_path, {"max_words_per_line": max_words_per_line})
            srt_files.append(segment_srt_file)
        except Exception as e:
            logging.error(f"Error transcribing segment {i+1}: {str(e)}")
            update_status(f"Error transcribing segment {i+1}: {str(e)}")
            return None
    
    return srt_files

def combine_srt_files(srt_files, output_file):
    """Combine all SRT files into one"""
    if cancel_flag:
        return False
    
    try:
        with open(output_file, "w", encoding="utf-8") as outfile:
            for srt_file in srt_files:
                with open(srt_file, encoding="utf-8") as infile:
                    outfile.write(infile.read())
                    outfile.write("\n")
        return True
    except Exception as e:
        update_status(f"Error combining SRT files: {str(e)}")
        return False

def process_video(video_file, model_name, language_code, max_words_per_line=6):
    """Main processing function that runs in a separate thread"""
    global cancel_flag, current_temp_dir
    
    logging.info("="*60)
    logging.info("process_video starting")
    logging.info(f"  video_file: {video_file}")
    logging.info(f"  model_name: {model_name}")
    logging.info(f"  language_code: {language_code}")
    logging.info(f"  max_words_per_line: {max_words_per_line}")
    
    try:
        # Check disk space before starting (need ~500 MB for temp files)
        import shutil as disk_check
        stat = disk_check.disk_usage(Path.home())
        free_gb = stat.free / (1024**3)
        logging.info(f"Available disk space: {free_gb:.1f} GB")
        
        if free_gb < 0.5:  # Less than 500 MB
            error_msg = f"Low disk space: {free_gb:.1f} GB free. Need at least 500 MB."
            logging.error(error_msg)
            update_status("❌ Not enough disk space! Free up at least 500 MB.")
            window.after(0, lambda: messagebox.showerror(
                "Insufficient Disk Space",
                f"Not enough free disk space!\n\n"
                f"Available: {free_gb:.2f} GB\n"
                f"Required: At least 0.5 GB\n\n"
                f"Please free up some space and try again."
            ))
            window.after(0, reset_ui)
            return
        
        # Create temporary directory
        try:
            current_temp_dir = tempfile.mkdtemp(prefix="whisper_transcribe_")
            logging.info(f"Created temp dir: {current_temp_dir}")
        except OSError as e:
            error_msg = f"Cannot create temp directory: {str(e)}"
            logging.error(error_msg)
            if "No space left" in str(e) or (hasattr(e, 'errno') and e.errno == 28):
                update_status("❌ Disk full!")
                window.after(0, lambda: messagebox.showerror(
                    "Disk Full",
                    "Cannot create temporary files - disk is full!\n\n"
                    "Please free up some space and try again."
                ))
            else:
                update_status(f"❌ Error: {str(e)}")
                window.after(0, lambda: messagebox.showerror("Error", f"Cannot create temp directory:\n{str(e)}"))
            window.after(0, reset_ui)
            return
        
        # Step 1: Extract audio
        logging.info("STEP 1: Extracting audio")
        update_status("Extracting audio from video...")
        update_progress(5)
        
        if not extract_and_split_audio(video_file, current_temp_dir):
            logging.error("Audio extraction failed")
            window.after(0, reset_ui)
            return
        
        if cancel_flag:
            logging.info("Cancelled after audio extraction")
            window.after(0, reset_ui)
            return
        
        # Step 2: Transcribe
        logging.info("STEP 2: Transcribing")
        lang_text = "Auto-detecting language" if not language_code else f"Language: {language_code.upper()}"
        update_status(f"Loading model and transcribing... {lang_text}")
        update_progress(10)
        
        srt_files = transcribe_audio_segments(current_temp_dir, model_name, language_code, max_words_per_line)
        
        if not srt_files or cancel_flag:
            logging.warning("Transcription returned no files or was cancelled")
            window.after(0, reset_ui)
            return
        
        # Step 3: Combine
        logging.info("STEP 3: Combining SRT files")
        update_status("Combining transcription files...")
        update_progress(95)
        
        # Save to Desktop/Transcriptions folder (with fallback)
        desktop = Path.home() / "Desktop"
        transcriptions_folder = desktop / "Transcriptions"
        
        try:
            transcriptions_folder.mkdir(exist_ok=True)
            logging.info(f"Transcriptions folder: {transcriptions_folder}")
        except (PermissionError, OSError) as e:
            # Fallback to Documents folder if Desktop not writable
            logging.warning(f"Cannot write to Desktop: {e}")
            transcriptions_folder = Path.home() / "Documents" / "Transcriptions"
            try:
                transcriptions_folder.mkdir(exist_ok=True)
                logging.info(f"Using fallback folder: {transcriptions_folder}")
            except Exception as e2:
                logging.error(f"Cannot create transcriptions folder: {e2}")
                update_status(f"❌ Cannot save file: {str(e2)}")
                window.after(0, lambda: messagebox.showerror(
                    "Permission Error",
                    f"Cannot create transcriptions folder!\n\n{str(e2)}\n\n"
                    f"Please check your permissions."
                ))
                window.after(0, reset_ui)
                return
        
        video_name = Path(video_file).stem
        output_file = transcriptions_folder / f"{video_name}_transcription.srt"
        
        # Check if file exists and handle
        if output_file.exists():
            logging.info(f"Output file already exists: {output_file}")
            # Add timestamp to make unique
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = transcriptions_folder / f"{video_name}_transcription_{timestamp}.srt"
            logging.info(f"Using timestamped filename: {output_file}")
        
        logging.info(f"Output file: {output_file}")
        
        if combine_srt_files(srt_files, str(output_file)):
            update_progress(100)
            update_status(f"✓ Complete! Saved to: {output_file.name}")
            logging.info("SUCCESS: Transcription complete!")
            window.after(0, lambda: enable_open_button(str(output_file)))
        else:
            logging.error("Failed to combine SRT files")
            window.after(0, reset_ui)
        
    except Exception as e:
        logging.error(f"FATAL ERROR in process_video: {str(e)}")
        logging.error(traceback.format_exc())
        update_status(f"Error: {str(e)}")
        window.after(0, reset_ui)
    finally:
        # Clean up temp files
        logging.info("Cleaning up temp files")
        cleanup_temp_files()
        logging.info("process_video finished")
        logging.info("="*60)

def upload_video():
    """Handle video upload button click"""
    global cancel_flag, processing_thread
    
    video_file = filedialog.askopenfilename(
        title="Select Video or Audio File",
        filetypes=[
            ("Video/Audio Files", "*.mov *.mp4 *.m4a *.mp3 *.wav *.avi *.mkv *.flac"),
            ("All Files", "*.*")
        ]
    )
    
    if video_file:
        # Get selected model and language
        model_display = model_var.get()
        model_name = MODEL_OPTIONS[model_display]
        
        language_display = language_var.get()
        language_code = LANGUAGE_OPTIONS[language_display]
        
        # Get words per line setting
        words_display = words_per_line_var.get()
        max_words_per_line = WORDS_PER_LINE_OPTIONS[words_display]
        
        # Reset cancel flag and disable controls
        cancel_flag = False
        upload_button.config(state="disabled")
        cancel_button.config(state="normal")
        open_button.config(state="disabled")
        model_dropdown.config(state="disabled")
        language_dropdown.config(state="disabled")
        words_dropdown.config(state="disabled")
        progress.set(0)
        
        # Start processing in separate thread
        processing_thread = threading.Thread(
            target=process_video, 
            args=(video_file, model_name, language_code, max_words_per_line), 
            daemon=True
        )
        processing_thread.start()

def cancel_processing():
    """Cancel the current transcription"""
    global cancel_flag
    cancel_flag = True
    update_status("Cancelling...")
    cancel_button.config(state="disabled")

def reset_ui():
    """Reset UI to initial state"""
    upload_button.config(state="normal")
    cancel_button.config(state="disabled")
    open_button.config(state="disabled")
    model_dropdown.config(state="readonly")
    language_dropdown.config(state="readonly")
    words_dropdown.config(state="readonly")
    progress.set(0)
    cleanup_temp_files()

def enable_open_button(filepath):
    """Enable the open file button"""
    open_button.config(state="normal", command=lambda: open_file(filepath))
    upload_button.config(state="normal")
    cancel_button.config(state="disabled")
    model_dropdown.config(state="readonly")
    language_dropdown.config(state="readonly")
    words_dropdown.config(state="readonly")

def open_file(filepath):
    """Show the SRT file location in Finder/Explorer"""
    if os.path.exists(filepath):
        try:
            if sys.platform == "darwin":  # macOS
                # Show file in Finder (Reveal in Finder)
                subprocess.call(["open", "-R", filepath])
            elif sys.platform == "win32":  # Windows
                subprocess.run(["explorer", "/select,", filepath])
            elif sys.platform == "linux":  # Linux
                subprocess.call(["xdg-open", os.path.dirname(filepath)])
        except Exception as e:
            messagebox.showerror("Error", f"Could not open file location: {e}")
    else:
        messagebox.showerror("Error", "File not found!")

def on_closing():
    """Handle window closing"""
    global cancel_flag
    if processing_thread and processing_thread.is_alive():
        if messagebox.askokcancel("Quit", "Transcription in progress. Cancel and quit?"):
            cancel_flag = True
            cleanup_temp_files()
            window.destroy()
    else:
        cleanup_temp_files()
        window.destroy()

# GUI Setup
window = tk.Tk()
window.title("Whisper Video Transcriber")
window.geometry("700x550")
window.resizable(False, False)
window.protocol("WM_DELETE_WINDOW", on_closing)

# Title
title_label = tk.Label(window, text="🎬 Whisper Video Transcriber", font=("Arial", 18, "bold"))
title_label.pack(pady=15)

# Instructions
instructions = tk.Label(
    window, 
    text="Select a video or audio file to transcribe.\nTranscription will be saved to your Desktop.",
    font=("Arial", 10),
    fg="gray"
)
instructions.pack(pady=5)

# Settings frame
settings_frame = tk.LabelFrame(window, text="Settings", font=("Arial", 10, "bold"), padx=20, pady=15)
settings_frame.pack(pady=15, padx=40, fill=tk.X)

# Model selection
model_frame = tk.Frame(settings_frame)
model_frame.pack(fill=tk.X, pady=5)

model_label = tk.Label(model_frame, text="Model:", font=("Arial", 10), width=12, anchor="w")
model_label.pack(side=tk.LEFT, padx=5)

model_var = tk.StringVar(value="Large-v3")
model_dropdown = ttk.Combobox(
    model_frame, 
    textvariable=model_var, 
    values=list(MODEL_OPTIONS.keys()),
    state="readonly",
    width=35,
    font=("Arial", 9)
)
model_dropdown.pack(side=tk.LEFT, padx=5)

# Language selection
language_frame = tk.Frame(settings_frame)
language_frame.pack(fill=tk.X, pady=5)

language_label = tk.Label(language_frame, text="Language:", font=("Arial", 10), width=12, anchor="w")
language_label.pack(side=tk.LEFT, padx=5)

language_var = tk.StringVar(value="Norwegian")
language_dropdown = ttk.Combobox(
    language_frame, 
    textvariable=language_var, 
    values=list(LANGUAGE_OPTIONS.keys()),
    state="readonly",
    width=35,
    font=("Arial", 9)
)
language_dropdown.pack(side=tk.LEFT, padx=5)

# Words per line selection
words_frame = tk.Frame(settings_frame)
words_frame.pack(fill=tk.X, pady=5)

words_label = tk.Label(words_frame, text="Words/Line:", font=("Arial", 10), width=12, anchor="w")
words_label.pack(side=tk.LEFT, padx=5)

words_per_line_var = tk.StringVar(value="2 words (short lines)")
words_dropdown = ttk.Combobox(
    words_frame, 
    textvariable=words_per_line_var, 
    values=list(WORDS_PER_LINE_OPTIONS.keys()),
    state="readonly",
    width=35,
    font=("Arial", 9)
)
words_dropdown.pack(side=tk.LEFT, padx=5)

# Buttons frame
button_frame = tk.Frame(window)
button_frame.pack(pady=15)

# Upload button
upload_button = tk.Button(
    button_frame, 
    text="📁 Select File", 
    command=upload_video,
    font=("Arial", 12),
    bg="#4CAF50",
    fg="white",
    padx=20,
    pady=10,
    relief=tk.RAISED,
    cursor="hand2"
)
upload_button.grid(row=0, column=0, padx=10)

# Cancel button
cancel_button = tk.Button(
    button_frame,
    text="❌ Cancel",
    command=cancel_processing,
    font=("Arial", 12),
    bg="#f44336",
    fg="white",
    padx=20,
    pady=10,
    state="disabled",
    relief=tk.RAISED,
    cursor="hand2"
)
cancel_button.grid(row=0, column=1, padx=10)

# Progress section
progress_frame = tk.Frame(window)
progress_frame.pack(pady=15, padx=40, fill=tk.X)

progress_label = tk.Label(progress_frame, text="Progress:", font=("Arial", 10))
progress_label.pack(anchor=tk.W)

progress = tk.DoubleVar()
progress_bar = ttk.Progressbar(progress_frame, variable=progress, maximum=100, length=500)
progress_bar.pack(pady=5, fill=tk.X)

# Status label
result_label = tk.Label(
    window, 
    text="Ready to transcribe", 
    wraplength=600,
    font=("Arial", 10),
    fg="#333"
)
result_label.pack(pady=10)

# Open file button
open_button = tk.Button(
    window,
    text="📂 Open Transcription",
    font=("Arial", 11),
    bg="#2196F3",
    fg="white",
    padx=20,
    pady=8,
    state="disabled",
    relief=tk.RAISED,
    cursor="hand2"
)
open_button.pack(pady=10)

# Footer
footer = tk.Label(
    window,
    text="Powered by OpenAI Whisper | Multiple models & languages supported",
    font=("Arial", 8),
    fg="gray"
)
footer.pack(side=tk.BOTTOM, pady=10)

# Run the application
if __name__ == "__main__":
    window.mainloop()
