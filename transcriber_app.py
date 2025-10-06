import tkinter as tk
from tkinter import filedialog, ttk, messagebox
import subprocess
import os
import sys
import threading
import tempfile
import shutil
from pathlib import Path

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
    
    # If model is already loaded and it's the right one, return it
    if whisper_model is not None and current_model_name == model_name:
        return whisper_model
    
    # Load new model
    try:
        import whisper
        update_status(f"Loading {model_name} model (first time may take a while)...")
        whisper_model = whisper.load_model(model_name)
        current_model_name = model_name
        return whisper_model
    except Exception as e:
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
    if cancel_flag:
        return False
    
    output_template = os.path.join(output_dir, "segment_%03d.wav")
    try:
        result = subprocess.run([
            'ffmpeg', '-i', video_file, '-ac', '1', '-ar', '44100', 
            '-f', 'segment', '-segment_time', str(segment_length),
            '-c:a', 'pcm_s16le', output_template, '-y'
        ], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
        
        if result.returncode != 0:
            update_status(f"FFmpeg error: {result.stderr[:100]}")
            return False
        return True
    except FileNotFoundError:
        update_status("FFmpeg not found! Please install FFmpeg and add it to PATH.")
        return False
    except Exception as e:
        update_status(f"Error extracting audio: {str(e)}")
        return False

def transcribe_audio_segments(temp_dir, model_name, language_code):
    """Transcribe each audio segment"""
    global cancel_flag
    from whisper.utils import get_writer
    
    if cancel_flag:
        return None
    
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
            srt_writer(result, segment_path, {"max_words_per_line": 6})
            srt_files.append(segment_srt_file)
        except Exception as e:
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

def process_video(video_file, model_name, language_code):
    """Main processing function that runs in a separate thread"""
    global cancel_flag, current_temp_dir
    
    try:
        # Create temporary directory
        current_temp_dir = tempfile.mkdtemp(prefix="whisper_transcribe_")
        
        # Step 1: Extract audio
        update_status("Extracting audio from video...")
        update_progress(5)
        
        if not extract_and_split_audio(video_file, current_temp_dir):
            window.after(0, reset_ui)
            return
        
        if cancel_flag:
            window.after(0, reset_ui)
            return
        
        # Step 2: Transcribe
        lang_text = "Auto-detecting language" if not language_code else f"Language: {language_code.upper()}"
        update_status(f"Loading model and transcribing... {lang_text}")
        update_progress(10)
        
        srt_files = transcribe_audio_segments(current_temp_dir, model_name, language_code)
        
        if not srt_files or cancel_flag:
            window.after(0, reset_ui)
            return
        
        # Step 3: Combine
        update_status("Combining transcription files...")
        update_progress(95)
        
        # Save to desktop
        desktop = Path.home() / "Desktop"
        video_name = Path(video_file).stem
        output_file = desktop / f"{video_name}_transcription.srt"
        
        if combine_srt_files(srt_files, str(output_file)):
            update_progress(100)
            update_status(f"✓ Complete! Saved to: {output_file.name}")
            window.after(0, lambda: enable_open_button(str(output_file)))
        else:
            window.after(0, reset_ui)
        
    except Exception as e:
        update_status(f"Error: {str(e)}")
        window.after(0, reset_ui)
    finally:
        # Clean up temp files
        cleanup_temp_files()

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
        
        # Reset cancel flag and disable controls
        cancel_flag = False
        upload_button.config(state="disabled")
        cancel_button.config(state="normal")
        open_button.config(state="disabled")
        model_dropdown.config(state="disabled")
        language_dropdown.config(state="disabled")
        progress.set(0)
        
        # Start processing in separate thread
        processing_thread = threading.Thread(
            target=process_video, 
            args=(video_file, model_name, language_code), 
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
    progress.set(0)
    cleanup_temp_files()

def enable_open_button(filepath):
    """Enable the open file button"""
    open_button.config(state="normal", command=lambda: open_file(filepath))
    upload_button.config(state="normal")
    cancel_button.config(state="disabled")
    model_dropdown.config(state="readonly")
    language_dropdown.config(state="readonly")

def open_file(filepath):
    """Open the SRT file"""
    if os.path.exists(filepath):
        try:
            if sys.platform == "darwin":  # macOS
                subprocess.call(["open", filepath])
            elif sys.platform == "win32":  # Windows
                os.startfile(filepath)
            elif sys.platform == "linux":  # Linux
                subprocess.call(["xdg-open", filepath])
        except Exception as e:
            messagebox.showerror("Error", f"Could not open file: {e}")
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
